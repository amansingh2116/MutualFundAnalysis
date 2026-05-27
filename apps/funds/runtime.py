"""
Runtime fund data fetches.

This module deliberately avoids writing fund detail data to the database. The
database can hold a lightweight AMFI scheme registry for search/navigation, but
NAV history, enriched metadata, returns, holdings, and chart data are fetched on
demand and cached in memory for a short time.
"""
from __future__ import annotations

import logging
import re
import json
import subprocess
import sys
from hashlib import md5
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core.utils import parse_amfi_date, parse_iso_date
from apps.funds.models import Scheme

logger = logging.getLogger("mfanalysis")

SNAPSHOT_TTL = 60 * 30
NAV_TTL = 60 * 60
YAHOO_TTL = 60 * 60
BENCHMARK_TTL = 60 * 60 * 6

BENCHMARK_TICKERS = {
    "NIFTY 50": "^NSEI",
    "NIFTY 100": "^CNX100",
    "NIFTY 500": "^CRSLDX",
    "NIFTY MIDCAP 150": "^CRSMID",
    "NIFTY SMALLCAP 250": "^CNXSC",
    "NIFTY BANK": "^NSEBANK",
}

CATEGORY_BENCHMARK_RULES = [
    ("large & mid", "NIFTY 200"),
    ("small cap", "NIFTY SMALLCAP 250"),
    ("mid cap", "NIFTY MIDCAP 150"),
    ("large cap", "NIFTY 100"),
    ("flexi cap", "NIFTY 500"),
    ("multi cap", "NIFTY 500"),
    ("elss", "NIFTY 500"),
    ("value", "NIFTY 500"),
    ("focused", "NIFTY 500"),
    ("index", "NIFTY 50"),
    ("aggressive hybrid", "NIFTY 500"),
    ("balanced hybrid", "NIFTY 500"),
]


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def get_runtime_snapshot(scheme: Scheme) -> SimpleNamespace:
    cache_key = f"fund:snapshot:v3:{scheme.amfi_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    nav_rows, mfapi_meta = fetch_nav_and_meta(scheme.amfi_code)
    nav_series = nav_rows_to_series(nav_rows)

    latest_nav = float(nav_series.iloc[-1]) if not nav_series.empty else _float(scheme.nav_latest)
    latest_date = nav_series.index[-1].date() if not nav_series.empty else scheme.nav_date

    category = mfapi_meta.get("scheme_category") or scheme.scheme_category or infer_category(scheme.scheme_name)
    benchmark_name = benchmark_for(category, scheme.scheme_name)
    benchmark_series = fetch_benchmark_series(benchmark_name, nav_series) if benchmark_name else pd.Series(dtype=float)

    captnemo = fetch_captnemo_meta(scheme)
    mstar = fetch_mstarpy_data(scheme)
    yahoo = fetch_yahoo_data(scheme, latest_nav)
    portfolio = merge_portfolio_data(mstar, yahoo)

    meta = build_meta(scheme, mfapi_meta, captnemo, yahoo, nav_series)
    trailing = compute_trailing_returns(nav_series, benchmark_series)
    calendar = compute_calendar_returns(nav_series, benchmark_series)
    rolling = compute_rolling_returns(nav_series)
    risk = compute_risk_metrics(nav_series, benchmark_series)
    drawdown = compute_drawdown(nav_series)

    snapshot = ns(
        scheme=scheme,
        nav_rows=series_to_rows(nav_series),
        nav_series=nav_series,
        nav_latest=latest_nav,
        nav_date=latest_date,
        category=category,
        benchmark_name=benchmark_name,
        benchmark_series=benchmark_series,
        meta=meta,
        trailing_returns=trailing,
        trailing_map={r.period: r for r in trailing},
        calendar_returns=calendar,
        rolling_returns=rolling,
        risk_3y=risk.get("3Y"),
        risk_5y=risk.get("5Y"),
        drawdown=drawdown,
        top_holdings=portfolio.get("holdings", []),
        sector_alloc=portfolio.get("sectors", []),
        asset_alloc=portfolio.get("asset_alloc"),
        holdings_month=portfolio.get("as_of"),
        managers=[m.strip() for m in str(getattr(meta, "fund_manager", "") or "").split(";") if m.strip()],
        yahoo_ticker=yahoo.get("ticker"),
        sources=ns(
            nav="mfapi.in / AMFI",
            meta=meta.fetch_source,
            portfolio=portfolio.get("source") or "unavailable",
            benchmark="yfinance" if not benchmark_series.empty else "unavailable",
        ),
    )
    cache.set(cache_key, snapshot, SNAPSHOT_TTL)
    return snapshot


def fetch_nav_and_meta(amfi_code: str) -> tuple[list[dict], dict]:
    cache_key = f"fund:nav-mfapi:v2:{amfi_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        from adapters.amfi_adapter import AMFIAdapter

        adapter = AMFIAdapter()
        meta = adapter.fetch_scheme_meta(amfi_code) or {}
        nav_rows = adapter.fetch_nav_history(amfi_code) or adapter.fetch_nav_history_mftool(amfi_code)
        result = (nav_rows or [], meta)
        cache.set(cache_key, result, NAV_TTL)
        return result
    except Exception as exc:
        logger.warning("[%s] runtime NAV/meta fetch failed: %s", amfi_code, exc)
        return [], {}


def nav_rows_to_series(nav_rows: list[dict]) -> pd.Series:
    rows = []
    for row in nav_rows:
        try:
            dt = parse_amfi_date(row.get("date", ""))
            nav = float(row.get("nav"))
        except (TypeError, ValueError):
            continue
        if dt and nav > 0:
            rows.append((pd.Timestamp(dt), nav))
    if not rows:
        return pd.Series(dtype=float)
    series = pd.Series(dict(rows)).sort_index()
    return series[~series.index.duplicated(keep="last")]


def series_to_rows(series: pd.Series) -> list[dict]:
    return [{"date": idx.date().isoformat(), "nav": float(val)} for idx, val in series.items()]


def fetch_captnemo_meta(scheme: Scheme) -> dict:
    if not scheme.isin_growth:
        return {}
    cache_key = f"fund:captnemo:v2:{scheme.isin_growth}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from adapters.captnemo_adapter import CaptnemoAdapter

        adapter = CaptnemoAdapter()
        info = None
        fallback_plan = False
        for candidate in captnemo_candidate_schemes(scheme):
            if not candidate.isin_growth:
                continue
            info = adapter.fetch_fund_info(candidate.isin_growth)
            fallback_plan = candidate.pk != scheme.pk
            if info:
                break
        if not info:
            cache.set(cache_key, {}, YAHOO_TTL)
            return {}
        data = normalise_captnemo_fields(info)
        if fallback_plan:
            data["reference_expense_ratio"] = data.get("expense_ratio")
            data["reference_expense_label"] = "Same fund direct plan"
            data["_plan_fallback"] = True
            data["fetch_source"] = "captnemo (same fund, direct plan fallback)"
        cache.set(cache_key, data, YAHOO_TTL)
        return data
    except Exception as exc:
        logger.info("[%s] captnemo runtime metadata unavailable: %s", scheme.amfi_code, exc)
        cache.set(cache_key, {}, 60 * 10)
        return {}


def captnemo_candidate_schemes(scheme: Scheme) -> list[Scheme]:
    """Try current plan first, then same-fund growth-plan siblings."""
    family = fund_family_key(scheme.scheme_name)
    if not family:
        return [scheme]
    amc = (scheme.fund_house or "").strip()
    qs = Scheme.objects.filter(fund_house=amc, plan="GROWTH") if amc else Scheme.objects.filter(plan="GROWTH")
    siblings = [
        candidate
        for candidate in qs.order_by("-is_direct", "scheme_name")
        if candidate.pk != scheme.pk and fund_family_key(candidate.scheme_name) == family
    ]
    return [scheme, *siblings]


def normalise_captnemo_fields(info: dict) -> dict:
    returns = info.get("returns") if isinstance(info.get("returns"), dict) else {}
    purchase = info.get("purchase") if isinstance(info.get("purchase"), dict) else {}
    sip = info.get("sip") if isinstance(info.get("sip"), dict) else {}
    return {
        "expense_ratio": _float(info.get("expense_ratio")),
        "expense_ratio_date": parse_iso_date(str(info.get("expense_ratio_date") or "")),
        "reference_expense_ratio": None,
        "reference_expense_label": "",
        "aum": _aum_cr(info.get("aum")),
        "fund_rating": _int(info.get("fund_rating")),
        "fund_rating_date": parse_iso_date(str(info.get("fund_rating_date") or "")),
        "crisil_rating": str(info.get("crisil_rating") or ""),
        "portfolio_turnover": _float(info.get("portfolio_turnover")),
        "start_date": parse_iso_date(str(info.get("start_date") or "")),
        "investment_objective": str(info.get("investment_objective") or ""),
        "fund_manager": str(info.get("fund_manager") or ""),
        "lump_min": _float(info.get("lump_min") or purchase.get("min_initial")),
        "lump_min_additional": _float(info.get("lump_min_additional") or purchase.get("min_additional")),
        "sip_min": _float(info.get("sip_min") or sip.get("min_installment_amount")),
        "sip_available": _bool(info.get("sip_available", info.get("sip_flag"))),
        "lump_available": _bool(info.get("lump_available", info.get("purchase_allowed"))),
        "redemption_allowed": _bool(info.get("redemption_allowed"), default=True),
        "switch_allowed": _bool(info.get("switch_allowed"), default=True),
        "stp_flag": _bool(info.get("stp_flag")),
        "swp_flag": _bool(info.get("swp_flag")),
        "lock_in_period": _int(info.get("lock_in_period") or info.get("lock_in")) or 0,
        "tax_period": _int(info.get("tax_period")) or 0,
        "returns_1w": _float(returns.get("week_1") or returns.get("1week")),
        "returns_1m": _float(returns.get("month_1") or returns.get("1month")),
        "returns_3m": _float(returns.get("month_3") or returns.get("3month")),
        "returns_1y": _float(returns.get("year_1") or returns.get("1year")),
        "returns_3y": _float(returns.get("year_3") or returns.get("3year")),
        "returns_5y": _float(returns.get("year_5") or returns.get("5year")),
        "returns_inception": _float(returns.get("inception")),
        "comparison_peers": info.get("comparison") or [],
        "fetch_source": "captnemo",
    }


def fetch_mstarpy_data(scheme: Scheme) -> dict:
    terms = [scheme.isin_growth, scheme.morningstar_id, clean_fund_name(scheme.scheme_name)]
    terms = [term for term in dict.fromkeys(str(t).strip() for t in terms if t)]
    if not terms:
        return {}
    cache_key = f"fund:mstarpy:v1:{scheme.amfi_code}:{md5('|'.join(terms).encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {}
    payload = fetch_mstarpy_payload(scheme, terms)
    if payload:
        meta = payload.get("meta") or {}
        result = {
            "source": "mstarpy",
            "term": payload.get("term"),
            "sec_id": meta.get("secId"),
            "holdings": mstarpy_holdings(payload.get("holdings")),
            "sectors": mstarpy_sectors(payload.get("sector")),
            "asset_alloc": mstarpy_asset_alloc(payload.get("allocation")),
            "as_of": mstarpy_portfolio_date(payload.get("allocation"), payload.get("sector"), payload.get("holdings")),
        }

    cache.set(cache_key, result, YAHOO_TTL)
    return result


def fetch_mstarpy_payload(scheme: Scheme, terms: list[str]) -> dict:
    request = {
        "terms": terms,
        "expected_isin": scheme.isin_growth or "",
        "family": fund_family_key(scheme.scheme_name),
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "apps.funds.mstarpy_fetch", json.dumps(request)],
            cwd=str(settings.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if completed.returncode != 0:
            logger.info("[%s] mstarpy subprocess unavailable: %s", scheme.amfi_code, completed.stderr or completed.stdout)
            return {}
        response = json.loads(completed.stdout.strip().splitlines()[-1])
        if response.get("ok"):
            payload = response.get("payload") or {}
            payload["term"] = response.get("term")
            return payload
    except Exception as exc:
        logger.info("[%s] mstarpy subprocess failed: %s", scheme.amfi_code, exc)
    return {}


def merge_portfolio_data(primary: dict, secondary: dict) -> dict:
    source = primary.get("source") if primary else None
    if not source and secondary:
        source = secondary.get("source")
    return {
        "source": source,
        "holdings": (primary.get("holdings") if primary else None) or secondary.get("holdings", []),
        "sectors": (primary.get("sectors") if primary else None) or secondary.get("sectors", []),
        "asset_alloc": (primary.get("asset_alloc") if primary else None) or secondary.get("asset_alloc"),
        "as_of": (primary.get("as_of") if primary else None) or secondary.get("as_of"),
    }


def fetch_yahoo_data(scheme: Scheme, latest_nav: float | None) -> dict:
    ticker = resolve_yahoo_ticker(scheme, latest_nav)
    if not ticker:
        return {}
    cache_key = f"fund:yahoo:v2:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {"ticker": ticker, "source": "yahooquery"}
    try:
        from yahooquery import Ticker

        yq = Ticker(ticker)
        summary = _by_symbol(yq.summary_detail, ticker)
        holding_info = _by_symbol(yq.fund_holding_info, ticker)
        performance = _by_symbol(yq.fund_performance, ticker)
        profile = _by_symbol(yq.fund_profile, ticker)
        key_stats = _by_symbol(yq.key_stats, ticker)

        total_assets = _float(key_stats.get("totalAssets") or summary.get("totalAssets"))
        if total_assets:
            result["aum"] = total_assets / 10_000_000

        fees = profile.get("feesExpensesInvestment") if isinstance(profile.get("feesExpensesInvestment"), dict) else {}
        result["expense_ratio"] = _positive_float(
            fees.get("netExpRatio")
            or fees.get("grossExpRatio")
            or fees.get("annualReportExpenseRatio")
            or key_stats.get("annualReportExpenseRatio")
        )
        result["lump_min"] = _float(profile.get("initInvestment"))
        result["sip_min"] = _float(profile.get("initAipInvestment"))
        result["lump_min_additional"] = _float(profile.get("subseqInvestment"))
        result["portfolio_turnover"] = _percent_value(key_stats.get("annualHoldingsTurnover"))
        result["fund_rating"] = _int(key_stats.get("morningStarOverallRating"))
        result["start_date"] = _parse_yahoo_date(key_stats.get("fundInceptionDate"))
        management = profile.get("managementInfo") if isinstance(profile.get("managementInfo"), dict) else {}
        result["fund_manager"] = str(management.get("managerName") or "")
        result["holdings"] = yahoo_holdings(yq, ticker, holding_info)
        result["sectors"] = yahoo_sectors(yq, ticker)
        result["asset_alloc"] = yahoo_asset_alloc(holding_info)
        result["performance"] = performance
        result["as_of"] = _parse_yahoo_date(
            performance.get("performanceOverview", {}).get("asOfDate")
            or performance.get("trailingReturns", {}).get("asOfDate")
        )
    except Exception as exc:
        logger.info("[%s] yahooquery runtime data unavailable for %s: %s", scheme.amfi_code, ticker, exc)

    cache.set(cache_key, result, YAHOO_TTL)
    return result


def resolve_yahoo_ticker(scheme: Scheme, latest_nav: float | None) -> str:
    if scheme.yahoo_ticker:
        return scheme.yahoo_ticker
    cache_key = f"fund:yahoo-ticker:v2:{scheme.amfi_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        import yfinance as yf
        from yahooquery import Ticker

        quote_by_symbol = {}
        for query in yahoo_search_queries(scheme):
            for quote in yf.Search(query, max_results=10).quotes:
                symbol = quote.get("symbol")
                if symbol and quote.get("quoteType") == "MUTUALFUND" and symbol.endswith(".BO"):
                    quote_by_symbol.setdefault(symbol, quote)
        symbols = list(quote_by_symbol)
        if not symbols:
            return ""
        if latest_nav:
            details = Ticker(" ".join(symbols)).summary_detail
            scored = []
            for symbol in symbols:
                prev = _float(_by_symbol(details, symbol).get("previousClose"))
                if prev:
                    quote = quote_by_symbol.get(symbol, {})
                    scored.append((abs(prev - latest_nav), -yahoo_name_score(scheme, quote), symbol))
            if scored:
                symbol = sorted(scored)[0][2]
                cache.set(cache_key, symbol, 7 * 24 * 3600)
                return symbol
        symbol = sorted(symbols, key=lambda item: -yahoo_name_score(scheme, quote_by_symbol.get(item, {})))[0]
        cache.set(cache_key, symbol, 7 * 24 * 3600)
        return symbol
    except Exception as exc:
        logger.info("[%s] Yahoo ticker lookup failed: %s", scheme.amfi_code, exc)
        return ""


def clean_fund_name(name: str) -> str:
    name = re.sub(r"\b(direct|regular)\s+plan\b", " ", name, flags=re.I)
    name = re.sub(r"\b(growth|idcw)\s+plan\b", " ", name, flags=re.I)
    name = re.sub(r"\b(growth|idcw)\s+option\b", " ", name, flags=re.I)
    name = re.sub(r"\b(growth|idcw|dividend|reinvestment|payout)\b", " ", name, flags=re.I)
    name = re.sub(r"\s*-\s*", " ", name)
    return " ".join(name.split())


def fund_family_key(name: str) -> str:
    cleaned = clean_fund_name(name).lower()
    cleaned = re.sub(r"\b(fund|scheme|plan|option)\b", " ", cleaned)
    return " ".join(cleaned.split())


def yahoo_search_queries(scheme: Scheme) -> list[str]:
    base = clean_fund_name(scheme.scheme_name)
    family = fund_family_key(scheme.scheme_name)
    amc_token = (scheme.fund_house or "").split()[0] if scheme.fund_house else ""
    category = (scheme.scheme_category or "").split(" - ")[-1].replace("Fund", "").strip()
    queries = [base, family]
    queries.extend(alias_queries_for_provider_names(base, family))
    if amc_token and category:
        queries.append(f"{amc_token} {category}")
    if amc_token and family:
        without_amc = re.sub(rf"^{re.escape(amc_token.lower())}\s+", "", family.lower()).strip()
        if without_amc:
            queries.append(f"{amc_token} {without_amc}")
    lower = f"{base} {scheme.scheme_category}".lower()
    if "elss" in lower or "tax saver" in lower:
        fund_house = amc_token or base.split()[0]
        queries.extend([f"{fund_house} ELSS", f"{fund_house} Tax Saver", f"{fund_house} ELSS Tax Saver"])
    return list(dict.fromkeys(q for q in queries if q))


def alias_queries_for_provider_names(base: str, family: str) -> list[str]:
    """Generate generic aliases for provider naming drift and SEBI recategorization."""
    aliases = []
    variants = {base, family}
    replacements = [
        ("flexi cap", "long term equity"),
        ("flexi cap", "multi cap"),
        ("focused", "focused equity"),
        ("tax saver", "elss"),
        ("elss", "tax saver"),
    ]
    for text in variants:
        lower = text.lower()
        for old, new in replacements:
            if old in lower:
                aliases.append(re.sub(old, new, text, flags=re.I))
    return aliases


def yahoo_name_score(scheme: Scheme, quote: dict) -> float:
    target = fund_family_key(scheme.scheme_name)
    candidate = fund_family_key(str(quote.get("longname") or quote.get("shortname") or quote.get("symbol") or ""))
    return SequenceMatcher(None, target, candidate).ratio() if target and candidate else 0


def mstarpy_holdings(holdings_df) -> list[SimpleNamespace]:
    if holdings_df is None:
        return []
    records = holdings_df
    if hasattr(holdings_df, "empty"):
        if holdings_df.empty:
            return []
        records = holdings_df.head(40).to_dict("records")
    rows = []
    for row in records[:40]:
        name = row.get("securityName") or row.get("holdingName")
        weight = _float(row.get("weighting") or row.get("weight") or row.get("holdingPercent"))
        if not name or weight is None or weight <= 0:
            continue
        rows.append(ns(
            security_name=str(name),
            ticker=str(row.get("ticker") or row.get("symbol") or ""),
            isin=str(row.get("isin") or ""),
            sector=str(row.get("sector") or row.get("globalSectorName") or ""),
            weight_pct=weight * 100 if weight <= 1 else weight,
            forward_pe=_float(row.get("forwardPERatio") or row.get("forwardPE")),
            holding_type=str(row.get("holdingType") or row.get("assetType") or "equity").lower(),
        ))
    return rows


def mstarpy_sectors(sector_raw: dict) -> list[SimpleNamespace]:
    if not isinstance(sector_raw, dict):
        return []
    equity = sector_raw.get("EQUITY") if isinstance(sector_raw.get("EQUITY"), dict) else {}
    portfolio = equity.get("fundPortfolio") if isinstance(equity.get("fundPortfolio"), dict) else {}
    ignored = {
        "portfolioDate", "assetType", "fundName", "categoryName", "indexName",
        "currencyId", "cashAndEquivalents", "notClassified",
    }
    rows = []
    for key, value in portfolio.items():
        if key in ignored:
            continue
        weight = _float(value)
        if weight and weight > 0:
            rows.append(ns(sector=humanize_key(key), weight_pct=weight))
    return sorted(rows, key=lambda item: item.weight_pct, reverse=True)


def mstarpy_asset_alloc(allocation_raw: dict):
    if not isinstance(allocation_raw, dict):
        return None
    allocation_map = allocation_raw.get("allocationMap")
    if not isinstance(allocation_map, dict):
        return None
    key_map = [
        ("Equity", ["INDAssetAllocStock", "AssetAllocStock"]),
        ("Debt", ["INDAssetAllocBond", "AssetAllocBond"]),
        ("Cash", ["INDAssetAllocCash", "AssetAllocCash"]),
        ("Other", ["INDAssetAllocOther", "AssetAllocOther", "INDAssetAllocConvertible", "AssetAllocConvertible"]),
    ]
    rows = []
    for label, keys in key_map:
        total = 0.0
        found = False
        for key in keys:
            item = allocation_map.get(key)
            if isinstance(item, dict):
                value = _float(item.get("netAllocation") or item.get("longAllocation"))
                if value is not None:
                    total += value
                    found = True
        if found:
            rows.append(ns(label=label, weight_pct=total))
    return rows or None


def mstarpy_portfolio_date(allocation_raw: dict, sector_raw: dict, holdings_df):
    for source in [allocation_raw]:
        if isinstance(source, dict):
            parsed = _parse_yahoo_date(source.get("portfolioDate"))
            if parsed:
                return parsed
    if isinstance(sector_raw, dict):
        for section in sector_raw.values():
            if isinstance(section, dict) and isinstance(section.get("fundPortfolio"), dict):
                parsed = _parse_yahoo_date(section["fundPortfolio"].get("portfolioDate"))
                if parsed:
                    return parsed
    if isinstance(holdings_df, list) and holdings_df:
        for col in ["portfolioDate", "asOfDate"]:
            parsed = _parse_yahoo_date(holdings_df[0].get(col))
            if parsed:
                return parsed
    if holdings_df is not None and hasattr(holdings_df, "columns"):
        for col in ["portfolioDate", "asOfDate"]:
            if col in holdings_df.columns and not holdings_df[col].dropna().empty:
                parsed = _parse_yahoo_date(holdings_df[col].dropna().iloc[0])
                if parsed:
                    return parsed
    return None


def yahoo_holdings(yq, ticker: str, holding_info: dict) -> list[SimpleNamespace]:
    holdings = holding_info.get("holdings") or []
    if not holdings:
        try:
            top = yq.fund_top_holdings
            if hasattr(top, "reset_index") and not top.empty:
                holdings = top.reset_index().to_dict("records")
        except Exception:
            holdings = []
    rows = []
    for row in holdings[:30]:
        name = row.get("holdingName") or row.get("securityName")
        weight = _float(row.get("holdingPercent") or row.get("weighting"))
        if not name or weight is None:
            continue
        rows.append(ns(
            security_name=name,
            ticker=str(row.get("symbol") or row.get("ticker") or ""),
            isin=str(row.get("isin") or ""),
            sector=str(row.get("sector") or ""),
            weight_pct=weight * 100 if weight <= 1 else weight,
            forward_pe=_float(row.get("forwardPERatio")),
            holding_type=str(row.get("holdingType") or "equity"),
        ))
    return rows


def yahoo_sectors(yq, ticker: str) -> list[SimpleNamespace]:
    try:
        sectors = yq.fund_sector_weightings
        rows = []
        if hasattr(sectors, "to_dict"):
            data = sectors[ticker].dropna().to_dict() if ticker in sectors else {}
        else:
            data = _by_symbol(sectors, ticker)
        for key, value in data.items():
            weight = _float(value)
            if weight and weight > 0:
                rows.append(ns(sector=humanize_key(key), weight_pct=weight * 100 if weight <= 1 else weight))
        return sorted(rows, key=lambda s: s.weight_pct, reverse=True)
    except Exception:
        return []


def yahoo_asset_alloc(holding_info: dict):
    if not holding_info:
        return None
    items = [
        ("Equity", _float(holding_info.get("stockPosition"))),
        ("Debt", _float(holding_info.get("bondPosition"))),
        ("Cash", _float(holding_info.get("cashPosition"))),
        ("Other", _float(holding_info.get("otherPosition"))),
    ]
    rows = [ns(label=label, weight_pct=value * 100 if value and value <= 1 else value) for label, value in items if value is not None]
    return rows or None


def build_meta(scheme: Scheme, mfapi_meta: dict, captnemo: dict, yahoo: dict, nav_series: pd.Series) -> SimpleNamespace:
    first_nav_date = nav_series.index[0].date() if not nav_series.empty else None
    now = timezone.now()
    data = {
        "scheme_category": mfapi_meta.get("scheme_category") or scheme.scheme_category or infer_category(scheme.scheme_name),
        "expense_ratio": None,
        "expense_ratio_date": None,
        "reference_expense_ratio": None,
        "reference_expense_label": "",
        "aum": None,
        "fund_rating": None,
        "fund_rating_date": None,
        "crisil_rating": "",
        "portfolio_turnover": None,
        "start_date": first_nav_date,
        "investment_objective": "",
        "fund_manager": "",
        "lump_min": None,
        "lump_min_additional": None,
        "sip_min": None,
        "sip_available": True,
        "lump_available": True,
        "redemption_allowed": True,
        "switch_allowed": True,
        "stp_flag": False,
        "swp_flag": False,
        "lock_in_period": 0,
        "tax_period": 0,
        "returns_1w": None,
        "returns_1m": None,
        "returns_3m": None,
        "returns_1y": None,
        "returns_3y": None,
        "returns_5y": None,
        "returns_inception": None,
        "comparison_peers": [],
        "fetch_source": "computed + mfapi.in",
        "last_fetched": now,
    }
    data.update({k: v for k, v in captnemo.items() if v not in (None, "", [])})
    if captnemo.get("_plan_fallback"):
        for key in [
            "expense_ratio",
            "expense_ratio_date",
            "returns_1w",
            "returns_1m",
            "returns_3m",
            "returns_1y",
            "returns_3y",
            "returns_5y",
            "returns_inception",
        ]:
            data[key] = None
    for key in ["lump_min", "lump_min_additional", "sip_min", "portfolio_turnover", "fund_rating", "start_date", "fund_manager"]:
        if not data.get(key) and yahoo.get(key):
            data[key] = yahoo[key]
    if data.get("expense_ratio") is None and yahoo.get("expense_ratio"):
        data["expense_ratio"] = yahoo["expense_ratio"]
    if yahoo.get("aum") and not data.get("aum"):
        data["aum"] = yahoo["aum"]
        data["fetch_source"] = (data.get("fetch_source") or "") + " + yahooquery"

    trailing_from_nav = compute_trailing_returns(nav_series, pd.Series(dtype=float))
    for period, attr in {"1M": "returns_1m", "3M": "returns_3m", "1Y": "returns_1y", "3Y": "returns_3y", "5Y": "returns_5y", "SI": "returns_inception"}.items():
        if data.get(attr) is None:
            match = next((r for r in trailing_from_nav if r.period == period), None)
            if match:
                data[attr] = match.cagr_pct
    data["lock_in_label"] = format_lock_in(data.get("lock_in_period"))
    return ns(**data)


def compute_trailing_returns(nav: pd.Series, bm: pd.Series) -> list[SimpleNamespace]:
    if nav.empty:
        return []
    specs = [("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365), ("2Y", 730), ("3Y", 1095), ("5Y", 1826), ("7Y", 2557), ("10Y", 3652), ("SI", None)]
    rows = []
    end_date = nav.index[-1]
    for period, days in specs:
        start_date = nav.index[0] if days is None else end_date - pd.Timedelta(days=days)
        value = cagr_for_window(nav, start_date, end_date)
        if value is None:
            continue
        bm_value = cagr_for_window(bm, start_date, end_date) if not bm.empty else None
        rows.append(ns(
            period=period,
            years=round((end_date - start_date).days / 365.25, 2) if days else round((end_date - nav.index[0]).days / 365.25, 2),
            cagr_pct=value,
            bm_cagr=bm_value,
            excess=value - bm_value if bm_value is not None else None,
            as_of=end_date.date(),
        ))
    return rows


def cagr_for_window(series: pd.Series, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float | None:
    if series.empty:
        return None
    window = series[series.index >= start_date]
    if len(window) < 2:
        return None
    start = float(window.iloc[0])
    end = float(series.iloc[-1])
    years = max((end_date - window.index[0]).days / 365.25, 1 / 365.25)
    if start <= 0:
        return None
    return (((end / start) ** (1 / years)) - 1) * 100


def compute_calendar_returns(nav: pd.Series, bm: pd.Series) -> list[SimpleNamespace]:
    if nav.empty:
        return []
    rows = []
    annual = nav.groupby(nav.index.year).agg(["first", "last"])
    bm_annual = bm.groupby(bm.index.year).agg(["first", "last"]) if not bm.empty else None
    for year, row in annual.iterrows():
        ret = ((row["last"] / row["first"]) - 1) * 100
        bm_ret = None
        if bm_annual is not None and year in bm_annual.index:
            brow = bm_annual.loc[year]
            bm_ret = ((brow["last"] / brow["first"]) - 1) * 100
        rows.append(ns(
            year=int(year),
            return_pct=float(ret) if ret is not None else None,
            bm_return=float(bm_ret) if bm_ret is not None else None,
            outperformed=bool(ret > bm_ret) if bm_ret is not None else None,
        ))
    return sorted(rows, key=lambda r: r.year, reverse=True)


def compute_rolling_returns(nav: pd.Series) -> dict[str, SimpleNamespace]:
    result = {}
    daily = nav.resample("B").ffill().dropna()
    for window, days in [("1Y", 252), ("3Y", 756), ("5Y", 1260)]:
        if len(daily) <= days:
            continue
        rolling = ((daily / daily.shift(days)) ** (252 / days) - 1) * 100
        rolling = rolling.dropna()
        if rolling.empty:
            continue
        result[window] = ns(
            window=window,
            window_days=days,
            min_pct=float(rolling.min()),
            max_pct=float(rolling.max()),
            mean_pct=float(rolling.mean()),
            std_dev=float(rolling.std()),
            win_rate_0=float((rolling > 0).mean() * 100),
            win_rate_12=float((rolling > 12).mean() * 100),
            as_of=nav.index[-1].date(),
        )
    return result


def compute_risk_metrics(nav: pd.Series, bm: pd.Series) -> dict[str, SimpleNamespace]:
    result = {}
    rf = float(getattr(settings, "RF_ANNUAL_RATE", 0.065))
    for period, days in [("3Y", 1095), ("5Y", 1826)]:
        cutoff = nav.index[-1] - pd.Timedelta(days=days) if not nav.empty else pd.Timestamp.today()
        s = nav[nav.index >= cutoff]
        if len(s) < 60:
            continue
        ret = s.pct_change().dropna()
        std = ret.std() * np.sqrt(252) * 100
        ann_ret = cagr_for_window(s, s.index[0], s.index[-1]) or 0
        downside = ret[ret < 0].std() * np.sqrt(252) * 100
        drawdown = compute_drawdown(s)
        max_dd = min((d.drawdown for d in drawdown), default=None)
        beta = alpha = r_squared = tracking_error = info_ratio = upside = downside_capture = None
        if not bm.empty:
            b = bm[bm.index >= s.index[0]]
            aligned = pd.concat([s.pct_change(), b.pct_change()], axis=1, join="inner").dropna()
            if len(aligned) > 30:
                aligned.columns = ["fund", "benchmark"]
                cov = aligned.cov().loc["fund", "benchmark"]
                var = aligned["benchmark"].var()
                if var:
                    beta = cov / var
                    bm_ann = ((1 + aligned["benchmark"]).prod() ** (252 / len(aligned)) - 1) * 100
                    alpha = ann_ret - (rf * 100 + beta * (bm_ann - rf * 100))
                    corr = aligned.corr().loc["fund", "benchmark"]
                    r_squared = corr * corr * 100
                    active = aligned["fund"] - aligned["benchmark"]
                    tracking_error = active.std() * np.sqrt(252) * 100
                    info_ratio = ((ann_ret - bm_ann) / tracking_error) if tracking_error else None
                    up = aligned[aligned["benchmark"] > 0]
                    down = aligned[aligned["benchmark"] < 0]
                    upside = (up["fund"].mean() / up["benchmark"].mean() * 100) if len(up) and up["benchmark"].mean() else None
                    downside_capture = (down["fund"].mean() / down["benchmark"].mean() * 100) if len(down) and down["benchmark"].mean() else None
        result[period] = ns(
            period=period,
            period_days=days,
            std_dev_ann=std,
            sharpe_ratio=((ann_ret - rf * 100) / std) if std else None,
            sortino_ratio=((ann_ret - rf * 100) / downside) if downside else None,
            max_drawdown=max_dd,
            beta=beta,
            alpha_ann=alpha,
            r_squared=r_squared,
            upside_capture=upside,
            downside_capture=downside_capture,
            tracking_error=tracking_error,
            info_ratio=info_ratio,
            rf_rate_used=rf,
            rf_rate_pct=rf * 100,
            benchmark=None,
            as_of=s.index[-1].date(),
        )
    return result


def compute_drawdown(nav: pd.Series) -> list[SimpleNamespace]:
    if nav.empty:
        return []
    running_max = nav.cummax()
    dd = ((nav - running_max) / running_max) * 100
    return [ns(date=idx.date().isoformat(), drawdown=float(value)) for idx, value in dd.resample("W").last().dropna().items()]


def fetch_benchmark_series(name: str, nav: pd.Series) -> pd.Series:
    ticker = BENCHMARK_TICKERS.get(name)
    if not ticker or nav.empty:
        return pd.Series(dtype=float)
    cache_key = f"benchmark:yf:v1:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf

        start = (nav.index[0] - pd.Timedelta(days=10)).date().isoformat()
        hist = yf.Ticker(ticker).history(start=start, auto_adjust=False)
        if hist.empty or "Close" not in hist:
            return pd.Series(dtype=float)
        series = hist["Close"].dropna()
        series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
        cache.set(cache_key, series, BENCHMARK_TTL)
        return series
    except Exception as exc:
        logger.info("Benchmark fetch failed for %s/%s: %s", name, ticker, exc)
        return pd.Series(dtype=float)


def benchmark_for(category: str, name: str = "") -> str | None:
    text = f"{category} {name}".lower()
    for marker, benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in text:
            return benchmark
    return None


def infer_category(name: str) -> str:
    lower = name.lower()
    for marker, _benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in lower:
            return marker.title()
    return ""


def _by_symbol(data: Any, symbol: str) -> dict:
    if isinstance(data, dict):
        return data.get(symbol, data if symbol not in data else {}) or {}
    return {}


def _parse_yahoo_date(value: Any):
    if not value:
        return None
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


def humanize_key(value: str) -> str:
    text = str(value).replace("_", " ").replace("-", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return text.title()


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1"}


def _float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_float(value: Any) -> float | None:
    result = _float(value)
    return result if result and result > 0 else None


def _percent_value(value: Any) -> float | None:
    result = _float(value)
    if result is None:
        return None
    return result * 100 if result <= 5 else result


def _aum_cr(value: Any) -> float | None:
    result = _float(value)
    if result is None:
        return None
    return result / 10 if result > 50_000 else result


def format_lock_in(value: Any) -> str:
    days_or_years = _int(value)
    if not days_or_years:
        return "None"
    if days_or_years <= 10:
        return f"{days_or_years} year{'s' if days_or_years != 1 else ''}"
    if days_or_years % 365 == 0:
        years = days_or_years // 365
        return f"{years} year{'s' if years != 1 else ''}"
    return f"{days_or_years} days"


def _int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
