"""
Runtime fund data fetches.

This module deliberately avoids writing fund detail data to the database. The
database can hold a lightweight AMFI scheme registry for search/navigation, but
NAV history, enriched metadata, returns, holdings, and chart data are fetched on
demand and cached in memory for a short time.
"""
from __future__ import annotations

import logging
import os
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
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.benchmarks.registry import (
    benchmark_for as registry_benchmark_for,
    configure_yfinance_cache,
    fetch_yahoo_history_for_benchmark,
    infer_category as registry_infer_category,
    iter_benchmark_candidates,
)
from apps.core.utils import parse_amfi_date, parse_iso_date
from apps.funds.models import Scheme

logger = logging.getLogger("mfanalysis")

SNAPSHOT_TTL = 60 * 30
NAV_TTL = 60 * 60
YAHOO_TTL = 60 * 60
FINAPI_TTL = 60 * 60 * 6
BENCHMARK_TTL = 60 * 60 * 6


def _normalize_portfolio_weights(holdings: list, sectors: list) -> tuple[list, list]:
    """
    Detect and fix unit bugs in holdings/sector data:
      - Fraction form: 0.0843 (sum <= 1.5) -> multiply by 100 to make 8.43%
      - Double-multiplied: sum >= 300 -> divide by 100
      - Normal percentages: leave as is (DO NOT rescale partial top holdings to 100%)
    """
    def _fix(items, attr="weight_pct"):
        if not items:
            return items
        total = sum(getattr(h, attr, 0) or 0 for h in items)
        if total <= 0:
            return items
        # If weights are given as fractions (e.g. 0.0843 instead of 8.43%), multiply by 100
        if total <= 1.5:
            factor = 100.0
        elif total >= 300:
            factor = 0.01
        else:
            return items  # Already valid percentage values

        corrected = []
        for h in items:
            w = getattr(h, attr, None)
            if w is not None:
                try:
                    object.__setattr__(h, attr, round(w * factor, 4))
                except AttributeError:
                    try:
                        setattr(h, attr, round(w * factor, 4))
                    except Exception:
                        pass
            corrected.append(h)
        return corrected

    return _fix(holdings), _fix(sectors)



def ns(**kwargs):
    return SimpleNamespace(**kwargs)


PORTFOLIO_SNAPSHOT_TTL = 60 * 60 * 4  # 4 hours — portfolio data changes slowly


def get_portfolio_snapshot(scheme: Scheme) -> SimpleNamespace:
    """Lightweight snapshot for portfolio/sector API endpoints.

    Skips the expensive benchmark fetch (which can block for 30-60 s on slow
    indices) so the Portfolio tab renders quickly, even when the full snapshot
    is still being built in the background.
    """
    cache_key = f"fund:portfolio:v3:{scheme.amfi_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Minimal NAV fetch — only need latest_nav to help resolve the Yahoo ticker
    try:
        nav_rows, _ = fetch_nav_and_meta(scheme.amfi_code)
    except Exception:
        nav_rows = []
    nav_series = nav_rows_to_series(nav_rows)
    latest_nav = float(nav_series.iloc[-1]) if not nav_series.empty else _float(scheme.nav_latest)

    yahoo = fetch_yahoo_data(scheme, latest_nav)

    # db_port has the full ingested disclosures — put it first so it wins over Yahoo stub
    db_port = fetch_db_portfolio(scheme)
    mstar = fetch_mstarpy_data(scheme)
    finapi = fetch_finapi_portfolio(scheme)

    db_holdings = db_port.get('holdings', [])
    if db_holdings:
        meta_fb = merge_portfolio_data(mstar, finapi)
        portfolio = {
            'source': db_port.get('source') or meta_fb.get('source'),
            'holdings': db_holdings,
            'sectors':  db_port.get('sectors') or meta_fb.get('sectors', []),
            'asset_alloc': db_port.get('asset_alloc') or meta_fb.get('asset_alloc'),
            'cap_alloc':   db_port.get('cap_alloc')   or meta_fb.get('cap_alloc'),
            'as_of': db_port.get('as_of') or meta_fb.get('as_of'),
        }
    else:
        portfolio = merge_portfolio_data(mstar, merge_portfolio_data(finapi, yahoo))

    raw_holdings = portfolio.get("holdings", [])
    raw_sectors  = portfolio.get("sectors", [])
    holdings_normalized, sectors_normalized = _normalize_portfolio_weights(raw_holdings, raw_sectors)

    result = ns(
        top_holdings=holdings_normalized,
        sector_alloc=sectors_normalized,
        asset_alloc=portfolio.get("asset_alloc"),
        cap_alloc=portfolio.get("cap_alloc"),
        holdings_month=portfolio.get("as_of"),
        portfolio_source=portfolio.get("source", ""),
    )
    ttl = PORTFOLIO_SNAPSHOT_TTL if (result.top_holdings or result.sector_alloc) else 5 * 60
    cache.set(cache_key, result, ttl)
    return result


def get_runtime_snapshot(scheme: Scheme) -> SimpleNamespace:
    cache_key = f"fund:snapshot:v11:{scheme.amfi_code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    db_nav_rows = fetch_db_nav_rows(scheme)
    nav_rows, mfapi_meta = fetch_nav_and_meta(scheme.amfi_code)
    if not nav_rows:
        nav_rows = db_nav_rows
    elif db_nav_rows and len(db_nav_rows) > len(nav_rows):
        nav_rows = db_nav_rows
    nav_series = nav_rows_to_series(nav_rows)

    latest_nav = float(nav_series.iloc[-1]) if not nav_series.empty else _float(scheme.nav_latest)
    latest_date = nav_series.index[-1].date() if not nav_series.empty else scheme.nav_date

    db_meta = scheme_meta_dict(scheme)
    stype_cat = ''
    if scheme.scheme_type:
        m = re.search(r'\((.*?)\)', scheme.scheme_type)
        if m:
            stype_cat = m.group(1).strip()
    category = mfapi_meta.get("scheme_category") or db_meta.get("scheme_category") or scheme.scheme_category or stype_cat or infer_category(scheme.scheme_name)
    benchmark_name = benchmark_for(category, scheme.scheme_name)
    benchmark_result = fetch_benchmark_result(benchmark_name, nav_series) if benchmark_name else empty_benchmark_result()
    benchmark_series = benchmark_result.series

    captnemo = fetch_captnemo_meta(scheme)
    yahoo = fetch_yahoo_data(scheme, latest_nav)

    # db_port has the full ingested disclosures (100+ holdings from ingest_holdings).
    # We put it first so it always wins over Yahoo's 10-holding stub.
    # mstar/finapi are merged in for cap_alloc/asset_alloc metadata they may provide.
    db_port = fetch_db_portfolio(scheme)
    mstar = fetch_mstarpy_data(scheme)
    finapi = fetch_finapi_portfolio(scheme)

    # Merge: db_port holdings win; mstar/finapi contribute metadata (cap/asset alloc) when db_port lacks them
    meta_fallback = merge_portfolio_data(mstar, finapi)
    db_holdings = db_port.get('holdings', [])
    if db_holdings:
        # Use DB holdings; fill in cap_alloc/asset_alloc from mstar/finapi/db if missing in db_port
        portfolio = {
            'source': db_port.get('source') or meta_fallback.get('source'),
            'holdings': db_holdings,
            'sectors':  db_port.get('sectors') or meta_fallback.get('sectors', []),
            'asset_alloc': db_port.get('asset_alloc') or meta_fallback.get('asset_alloc'),
            'cap_alloc':   db_port.get('cap_alloc')   or meta_fallback.get('cap_alloc'),
            'as_of': db_port.get('as_of') or meta_fallback.get('as_of'),
        }
    else:
        # DB is empty — fall back to mstar > finapi > yahoo
        portfolio = merge_portfolio_data(mstar, merge_portfolio_data(finapi, yahoo))

    meta = build_meta(scheme, mfapi_meta, db_meta, captnemo, yahoo, nav_series)
    trailing = compute_trailing_returns(nav_series, benchmark_series) or fetch_db_trailing_returns(scheme)
    calendar = compute_calendar_returns(nav_series, benchmark_series) or fetch_db_calendar_returns(scheme)
    rolling = compute_rolling_returns(nav_series, benchmark_series) or fetch_db_rolling_returns(scheme)
    risk = compute_risk_metrics(nav_series, benchmark_series)
    if not risk or not risk.get("3Y") or risk["3Y"].beta is None:
        db_risk = fetch_db_risk_metrics(scheme)
        if db_risk and db_risk.get("3Y"):
            risk = db_risk
    drawdown = compute_drawdown(nav_series)
    quarterly = compute_quarterly_performance(nav_series, benchmark_series)
    yearly_risk = compute_yearly_risk_metrics(nav_series, benchmark_series)
    crisis_periods = compute_crisis_periods(nav_series)
    market_regimes = compute_market_regimes(nav_series)

    managers = split_manager_names(str(getattr(meta, "fund_manager", "") or ""))
    manager_source = ""
    if captnemo.get("fund_manager"):
        manager_source = "captnemo"
    elif yahoo.get("fund_manager"):
        manager_source = "yahooquery"
    
    # ── Normalize portfolio weights (fix double-multiplication bugs) ───────────
    raw_holdings = portfolio.get("holdings", [])
    raw_sectors  = portfolio.get("sectors", [])
    holdings_normalized, sectors_normalized = _normalize_portfolio_weights(raw_holdings, raw_sectors)

    _top10_weight_raw = sum(
        getattr(h, "weight_pct", 0) or 0 for h in holdings_normalized[:10]
    )
    # Guard: if still implausibly large after normalization, don't display
    _top10_weight = round(_top10_weight_raw, 2) if 0 < _top10_weight_raw <= 100 else None

    snapshot = ns(
        scheme=scheme,
        nav_rows=series_to_rows(nav_series),
        nav_series=nav_series,
        nav_latest=latest_nav,
        nav_date=latest_date,
        category=category,
        benchmark_name=benchmark_name,
        benchmark_display_name=benchmark_result.display_name or benchmark_name,
        benchmark_actual_name=benchmark_result.actual_name,
        benchmark_ticker=benchmark_result.ticker,
        benchmark_source=benchmark_result.source,
        benchmark_fallback_used=benchmark_result.fallback_used,
        benchmark_note=benchmark_result.note,
        benchmark_info=benchmark_result,
        benchmark_series=benchmark_series,
        meta=meta,
        trailing_returns=trailing,
        trailing_map={r.period: r for r in trailing},
        calendar_returns=calendar,
        rolling_returns=rolling,
        risk_3y=risk.get("3Y"),
        risk_5y=risk.get("5Y"),
        drawdown=drawdown,
        quarterly_performance=quarterly,
        yearly_risk=yearly_risk,
        crisis_periods=crisis_periods,
        market_regimes=market_regimes,
        top_holdings=holdings_normalized,
        sector_alloc=sectors_normalized,
        asset_alloc=portfolio.get("asset_alloc"),
        cap_alloc=portfolio.get("cap_alloc"),
        holdings_month=portfolio.get("as_of"),
        top10_weight=_top10_weight,
        total_holdings_count=len(holdings_normalized),

        managers=managers,
        manager_cards=[
            ns(
                name=manager,
                role="Fund Manager",
                fund_house=scheme.fund_house,
                source=manager_source or meta.fetch_source,
            )
            for manager in managers
        ],
        manager_context=ns(
            source=manager_source or meta.fetch_source,
            start_date=meta.start_date,
            aum=meta.aum,
            expense_ratio=meta.expense_ratio,
            fund_rating=meta.fund_rating,
            crisil_rating=meta.crisil_rating,
            portfolio_turnover=meta.portfolio_turnover,
            investment_objective=meta.investment_objective,
            benchmark_name=benchmark_result.display_name or benchmark_name,
            risk_3y=risk.get("3Y"),
            top_holdings_count=len(portfolio.get("holdings", [])),
            sector_count=len(portfolio.get("sectors", [])),
            portfolio_source=portfolio.get("source") or "unavailable",
        ),
        yahoo_ticker=yahoo.get("ticker"),
        sources=ns(
            nav="mfapi.in / AMFI" if nav_rows != db_nav_rows else "database",
            meta=meta.fetch_source,
            portfolio=portfolio.get("source") or "unavailable",
            benchmark=benchmark_result.source if not benchmark_series.empty else "unavailable",
        ),
    )
    has_data = bool(snapshot.nav_rows or snapshot.trailing_returns or snapshot.top_holdings or snapshot.sector_alloc or snapshot.meta.fetch_source != "computed + mfapi.in")
    cache.set(cache_key, snapshot, SNAPSHOT_TTL if has_data else 60)
    return snapshot


def split_manager_names(value: str) -> list[str]:
    """Split manager strings from providers without breaking initials."""
    if not value:
        return []
    parts = re.split(r"\s*(?:;|/|\band\b|\+)\s*", value, flags=re.I)
    managers = []
    for part in parts:
        cleaned = " ".join(str(part).strip(" ,").split())
        if cleaned and cleaned.lower() not in {"na", "n/a", "none", "not available"}:
            managers.append(cleaned)
    return list(dict.fromkeys(managers))


def fetch_db_nav_rows(scheme: Scheme) -> list[dict]:
    try:
        from apps.funds.models import NAVHistory

        return [
            {"date": row.date.isoformat(), "nav": float(row.nav)}
            for row in NAVHistory.objects.filter(scheme=scheme).order_by("date").only("date", "nav")
        ]
    except Exception as exc:
        logger.info("[%s] DB NAV fallback unavailable: %s", scheme.amfi_code, exc)
        return []


def scheme_meta_dict(scheme: Scheme) -> dict:
    try:
        meta = scheme.meta
    except Exception:
        return {}
    keys = [
        "expense_ratio", "expense_ratio_date", "aum", "fund_rating", "fund_rating_date",
        "crisil_rating", "portfolio_turnover", "start_date", "investment_objective",
        "fund_manager", "lump_min", "lump_min_additional", "sip_min", "sip_available",
        "lump_available", "redemption_allowed", "switch_allowed", "stp_flag", "swp_flag",
        "lock_in_period", "tax_period", "returns_1w", "returns_1m", "returns_3m",
        "returns_1y", "returns_3y", "returns_5y", "returns_inception",
        "comparison_peers", "fetch_source",
    ]
    data = {key: getattr(meta, key, None) for key in keys}
    data["scheme_category"] = getattr(meta, "ms_category", "") or scheme.scheme_category
    data["fetch_source"] = data.get("fetch_source") or "database"
    return data


def fetch_db_portfolio(scheme: Scheme) -> dict:
    try:
        from apps.holdings.models import Holding, SectorAllocation, MarketCapAllocation

        latest_holding_month = (
            Holding.objects.filter(scheme=scheme).order_by("-as_of_month").values_list("as_of_month", flat=True).first()
        )
        holdings = []
        if latest_holding_month:
            holdings = [
                ns(
                    security_name=row.security_name,
                    ticker=row.ticker,
                    isin=row.isin,
                    sector=row.sector,
                    weight_pct=float(row.weight_pct),
                    forward_pe=_float(row.forward_pe),
                    holding_type=row.holding_type,
                )
                for row in Holding.objects.filter(scheme=scheme, as_of_month=latest_holding_month).order_by("-weight_pct")
            ]

        latest_sector_month = (
            SectorAllocation.objects.filter(scheme=scheme).order_by("-as_of_month").values_list("as_of_month", flat=True).first()
        )
        sectors = []
        if latest_sector_month:
            sectors = [
                ns(sector=row.sector, weight_pct=float(row.weight_pct))
                for row in SectorAllocation.objects.filter(scheme=scheme, as_of_month=latest_sector_month).order_by("-weight_pct")
            ]
        if not sectors and holdings:
            sec_totals = {}
            for h in holdings:
                s = (getattr(h, "sector", "") or "").strip()
                w = getattr(h, "weight_pct", 0) or 0
                if s and w > 0:
                    sec_totals[s] = sec_totals.get(s, 0.0) + float(w)
            if sec_totals:
                sectors = [
                    ns(sector=k, weight_pct=round(v, 4))
                    for k, v in sorted(sec_totals.items(), key=lambda x: x[1], reverse=True)
                ]

        mcap = MarketCapAllocation.objects.filter(scheme=scheme).order_by("-as_of_month").first()
        asset_alloc = None
        cap_alloc = None
        if mcap:
            asset_rows = []
            if mcap.equity_pct is not None:
                asset_rows.append(ns(label="Equity", weight_pct=float(mcap.equity_pct)))
            if mcap.debt_pct is not None:
                asset_rows.append(ns(label="Debt", weight_pct=float(mcap.debt_pct)))
            if mcap.cash_pct is not None:
                asset_rows.append(ns(label="Cash", weight_pct=float(mcap.cash_pct)))
            asset_alloc = asset_rows or None
            if mcap.large_pct is not None or mcap.mid_pct is not None or mcap.small_pct is not None:
                cap_alloc = ns(
                    large_pct=_float(mcap.large_pct),
                    mid_pct=_float(mcap.mid_pct),
                    small_pct=_float(mcap.small_pct),
                    other_pct=_float(mcap.other_pct),
                    cap_method=mcap.cap_method or "database",
                )

        return {
            "source": "database" if holdings or sectors else None,
            "holdings": holdings,
            "sectors": sectors,
            "asset_alloc": asset_alloc,
            "cap_alloc": cap_alloc,
            "as_of": latest_holding_month or latest_sector_month,
        }
    except Exception as exc:
        logger.info("[%s] DB portfolio fallback unavailable: %s", scheme.amfi_code, exc)
        return {"source": None, "holdings": [], "sectors": [], "asset_alloc": None, "cap_alloc": None, "as_of": None}


def fetch_db_trailing_returns(scheme: Scheme) -> list[SimpleNamespace]:
    try:
        from apps.analytics.models import TrailingReturn

        latest = TrailingReturn.objects.filter(scheme=scheme).order_by("-as_of").values_list("as_of", flat=True).first()
        if not latest:
            return []
        return [
            ns(
                period=row.period,
                years=float(row.years) if row.years is not None else None,
                cagr_pct=float(row.cagr_pct) if row.cagr_pct is not None else None,
                bm_cagr=float(row.bm_cagr) if row.bm_cagr is not None else None,
                excess=float(row.excess) if row.excess is not None else None,
                as_of=row.as_of,
            )
            for row in TrailingReturn.objects.filter(scheme=scheme, as_of=latest).order_by("years")
        ]
    except Exception as exc:
        logger.info("[%s] DB trailing fallback unavailable: %s", scheme.amfi_code, exc)
        return []


def fetch_db_calendar_returns(scheme: Scheme) -> list[SimpleNamespace]:
    try:
        from apps.analytics.models import CalendarReturn

        return [
            ns(
                year=row.year,
                return_pct=float(row.return_pct) if row.return_pct is not None else None,
                bm_return=float(row.bm_return) if row.bm_return is not None else None,
                outperformed=row.outperformed,
            )
            for row in CalendarReturn.objects.filter(scheme=scheme).order_by("-year")[:15]
        ]
    except Exception as exc:
        logger.info("[%s] DB calendar fallback unavailable: %s", scheme.amfi_code, exc)
        return []


def fetch_db_rolling_returns(scheme: Scheme) -> dict[str, SimpleNamespace]:
    try:
        from apps.analytics.models import RollingReturn

        rows = RollingReturn.objects.filter(scheme=scheme).order_by("window", "-as_of")
        result = {}
        for row in rows:
            if row.window in result:
                continue
            result[row.window] = ns(
                window=row.window,
                window_days=row.window_days,
                min_pct=float(row.min_pct) if row.min_pct is not None else None,
                max_pct=float(row.max_pct) if row.max_pct is not None else None,
                mean_pct=float(row.mean_pct) if row.mean_pct is not None else None,
                std_dev=float(row.std_dev) if row.std_dev is not None else None,
                win_rate_0=float(row.win_rate_0) if row.win_rate_0 is not None else None,
                win_rate_12=float(row.win_rate_12) if row.win_rate_12 is not None else None,
                as_of=row.as_of,
            )
        return result
    except Exception as exc:
        logger.info("[%s] DB rolling fallback unavailable: %s", scheme.amfi_code, exc)
        return {}


def fetch_db_risk_metrics(scheme: Scheme) -> dict[str, SimpleNamespace]:
    try:
        from apps.analytics.models import RiskMetrics

        rows = RiskMetrics.objects.filter(scheme=scheme).order_by("period", "-as_of")
        result = {}
        for row in rows:
            if row.period in result:
                continue
            result[row.period] = ns(
                period=row.period,
                period_days=row.period_days,
                std_dev_ann=float(row.std_dev_ann) if row.std_dev_ann is not None else None,
                sharpe_ratio=float(row.sharpe_ratio) if row.sharpe_ratio is not None else None,
                sortino_ratio=float(row.sortino_ratio) if row.sortino_ratio is not None else None,
                max_drawdown=float(row.max_drawdown) if row.max_drawdown is not None else None,
                beta=float(row.beta) if row.beta is not None else None,
                alpha_ann=float(row.alpha_ann) if row.alpha_ann is not None else None,
                r_squared=float(row.r_squared) if row.r_squared is not None else None,
                upside_capture=float(row.upside_capture) if row.upside_capture is not None else None,
                downside_capture=float(row.downside_capture) if row.downside_capture is not None else None,
                tracking_error=float(row.tracking_error) if row.tracking_error is not None else None,
                info_ratio=float(row.info_ratio) if row.info_ratio is not None else None,
                rf_rate_used=float(row.rf_rate_used) if row.rf_rate_used is not None else None,
                rf_rate_pct=float(row.rf_rate_used) * 100 if row.rf_rate_used is not None else None,
                benchmark=row.benchmark,
                as_of=row.as_of,
            )
        return result
    except Exception as exc:
        logger.info("[%s] DB risk fallback unavailable: %s", scheme.amfi_code, exc)
        return {}


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


def fetch_finapi_portfolio(scheme: Scheme) -> dict:
    """Fetch full mutual fund portfolio rows by AMFI scheme code."""
    code = str(scheme.amfi_code or "").strip()
    if not code:
        return {}
    cache_key = f"fund:finapi-portfolio:v1:{code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {}
    try:
        response = requests.get(
            f"https://finapi.upvaly.com/api/mf/scheme-code/{code}",
            params={"fields": "schemeCode,schemeName,latestNavDate,portfolio,holdings,sectors"},
            headers={
                "Accept": "application/json",
                "User-Agent": "MFAnalysis/1.0 (+https://github.com)",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}

        portfolio = data.get("portfolio") if isinstance(data.get("portfolio"), dict) else {}
        holdings = finapi_holdings(data.get("holdings"))
        sectors = finapi_sectors(data.get("sectors"))
        asset_alloc = finapi_asset_alloc(portfolio.get("assetAllocation"))
        cap_alloc = finapi_cap_alloc(portfolio.get("marketCapWeightage"))
        as_of = _parse_yahoo_date(
            data.get("portfolioDate")
            or portfolio.get("portfolioDate")
            or data.get("latestNavDate")
            or data.get("navDate")
        )
        if holdings or sectors or asset_alloc or cap_alloc:
            result = {
                "source": "finapi.upvaly",
                "holdings": holdings,
                "sectors": sectors,
                "asset_alloc": asset_alloc,
                "cap_alloc": cap_alloc,
                "as_of": as_of,
            }
    except Exception as exc:
        logger.info("[%s] finapi portfolio unavailable: %s", code, exc)

    cache.set(cache_key, result, FINAPI_TTL if result else 15 * 60)
    return result


def finapi_holdings(raw: Any) -> list[SimpleNamespace]:
    if not isinstance(raw, list):
        return []
    rows: list[SimpleNamespace] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("securityName") or row.get("holdingName") or "").strip()
        weight = _float(row.get("weightage") or row.get("weight") or row.get("holdingPercent"))
        if not name or weight is None or weight <= 0:
            continue
        sector = str(row.get("sector") or row.get("industry") or "").strip()
        rows.append(ns(
            security_name=name,
            ticker=str(row.get("ticker") or row.get("symbol") or ""),
            isin=str(row.get("isin") or row.get("isinCode") or ""),
            sector=sector,
            weight_pct=weight,
            forward_pe=_float(row.get("forwardPE") or row.get("forward_pe") or row.get("pe")),
            holding_type=finapi_holding_type(name, sector),
        ))
    return sorted(rows, key=lambda item: item.weight_pct, reverse=True)


def finapi_sectors(raw: Any) -> list[SimpleNamespace]:
    if not isinstance(raw, list):
        return []
    rows: list[SimpleNamespace] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("sector") or row.get("name") or "").strip()
        weight = _float(row.get("weightage") or row.get("weight"))
        if name and weight is not None and weight > 0:
            rows.append(ns(sector=name, weight_pct=weight * 100 if weight <= 1 else weight))
    return sorted(rows, key=lambda item: item.weight_pct, reverse=True)


def finapi_asset_alloc(raw: Any):
    if not isinstance(raw, dict):
        return None
    label_map = {
        "equity": "Equity",
        "stock": "Equity",
        "debt": "Debt",
        "bond": "Debt",
        "cash": "Cash",
        "money": "Cash",
        "other": "Other",
        "commod": "Other",
    }
    rows = []
    for key, value in raw.items():
        weight = _float(value)
        if weight is None:
            continue
        lower = str(key).lower()
        label = next((name for marker, name in label_map.items() if marker in lower), humanize_key(key))
        rows.append(ns(label=label, weight_pct=weight * 100 if weight <= 1 else weight))
    deduped: dict[str, float] = {}
    for row in rows:
        deduped[row.label] = deduped.get(row.label, 0.0) + row.weight_pct
    return [ns(label=label, weight_pct=weight) for label, weight in deduped.items()] or None


def finapi_cap_alloc(raw: Any):
    if not isinstance(raw, dict):
        return None
    large = _float(raw.get("largeCap") or raw.get("large_cap") or raw.get("large"))
    mid = _float(raw.get("midCap") or raw.get("mid_cap") or raw.get("mid"))
    small = _float(raw.get("smallCap") or raw.get("small_cap") or raw.get("small"))
    other = _float(raw.get("others") or raw.get("other") or raw.get("otherCap"))
    if large is None and mid is None and small is None:
        return None
    # Normalize if values were returned as fractions (<= 1)
    if (large or 0) <= 1 and (mid or 0) <= 1 and (small or 0) <= 1 and (other or 0) <= 1 and ((large or 0) + (mid or 0) + (small or 0) > 0):
        if large is not None: large *= 100
        if mid is not None: mid *= 100
        if small is not None: small *= 100
        if other is not None: other *= 100
    return ns(
        large_pct=large,
        mid_pct=mid,
        small_pct=small,
        other_pct=other,
        cap_method="disclosure",
    )


def finapi_holding_type(name: str, sector: str) -> str:
    text = f"{name} {sector}".lower()
    if any(marker in text for marker in ["cash", "treasury", "clearing corporation", "ccil", "tri party", "t-bill"]):
        return "cash"
    if any(marker in text for marker in ["bond", "debenture", "government securities", "g-sec", "securit"]):
        return "debt"
    if any(marker in text for marker in ["gold", "silver", "platinum", "commodity", "bullion"]):
        return "other"
    return "equity"


_MSTAR_RESOLVE_NEG_TTL = 60 * 60 * 24  # 24h negative-result cache — don't retry unindexed ISINs too often


def _load_static_secid_map() -> dict[str, str]:
    """Load precomputed ISIN -> Morningstar SecId mapping (data/morningstar_secids.json)."""
    candidates = [
        os.path.join(str(getattr(settings, "BASE_DIR", "")), "data", "morningstar_secids.json"),
        os.path.join(os.getcwd(), "data", "morningstar_secids.json"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
    return {}


_STATIC_SECID_MAP: dict[str, str] = _load_static_secid_map()


def _resolve_morningstar_id_live(scheme: Scheme) -> str:
    """Resolve Scheme.morningstar_id via ISIN on-the-fly for the live fund detail page.

    1. Checks precomputed static mapping from data/morningstar_secids.json (instant).
    2. Falls back to pure-HTTP discovery:
       - ISIN as path parameter to the Morningstar holdings endpoint.
       - Name-based token search.

    Results are cached (both hits and misses) so each AMFI code is only attempted
    once per 24 hours. On success the SecId is persisted to Scheme.morningstar_id.
    """
    isin = str(scheme.isin_growth or "").strip().upper()
    if not isin:
        return ""

    # Strategy 0: Static precomputed mapping (O(1), zero network overhead)
    if isin in _STATIC_SECID_MAP:
        sec_id = _STATIC_SECID_MAP[isin]
        try:
            scheme.morningstar_id = sec_id
            Scheme.objects.filter(pk=scheme.pk).update(morningstar_id=sec_id)
        except Exception:
            pass
        return sec_id

    neg_cache_key = f"fund:mstar_resolve:neg:v1:{scheme.amfi_code}"
    if cache.get(neg_cache_key):
        return ""  # Previously failed — wait 24h before retrying

    api_key = "lstzFDEOhfFNMLikKa0am9mgEKLBl49T"
    headers = {
        "apikey":     api_key,
        "Accept":     "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    # Strategy 1: ISIN as holdings path param — API may return secId in body
    try:
        h_url = (f"https://api-global.morningstar.com/sal-service/v1/fund"
                 f"/portfolio/holding/v2/{isin}/data")
        resp = requests.get(
            h_url, headers=headers,
            params={"clientId": "MDC", "version": "4.71.0",
                    "premiumNum": 10000, "freeNum": 10000},
            timeout=10,
        )
        if resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:
                body = {}
            if isinstance(body, dict):
                sec_id = str(body.get("secId") or body.get("masterPortfolioId") or "").strip()
                if sec_id:
                    return sec_id
    except Exception:
        pass

    # Strategy 2: Name-based token search
    try:
        name = str(scheme.scheme_name or "").strip()
        for suffix in [" - Direct Plan Growth Option", " Direct Growth", " - Direct Plan",
                       " Direct Plan Growth", "- Direct Plan Growth", " Growth Option",
                       " - Growth Option"]:
            name = name.replace(suffix, "")
        search_term = " ".join(name.split()[:6]).strip()
        if search_term:
            r = requests.get(
                "https://api-global.morningstar.com/sal-service/v1/fund/token/search",
                headers=headers,
                params={"term": search_term, "limit": 5, "clientId": "MDC",
                        "currency": "INR", "universeIds": "FOIND$$ALL|ETFIND$$ALL"},
                timeout=10,
            )
            if r.status_code == 200:
                results = r.json()
                if isinstance(results, dict):
                    results = results.get("hits") or results.get("results") or []
                for item in results:
                    sec_id   = str(item.get("SecId") or item.get("secId") or item.get("id") or "").strip()
                    item_isin = str(item.get("Isin") or item.get("isin") or "").strip().upper()
                    if sec_id and (item_isin == isin.upper() or not item_isin):
                        return sec_id
    except Exception:
        pass

    # Cache the negative result to avoid hammering the API on every page load
    cache.set(neg_cache_key, True, _MSTAR_RESOLVE_NEG_TTL)
    return ""


def fetch_mstarpy_data(scheme: Scheme) -> dict:
    # Only attempt mstarpy when a Morningstar SecId is available (or resolvable).
    if not scheme.morningstar_id and not scheme.isin_growth:
        return {}

    sec_id = str(scheme.morningstar_id or "").strip()

    # On-the-fly resolve: if no SecId stored, try to discover it from the ISIN.
    # This lets the live fund detail page show full Morningstar holdings for funds
    # that were added to AMFI after the last ingest_holdings run.
    if not sec_id and scheme.isin_growth:
        sec_id = _resolve_morningstar_id_live(scheme)
        if sec_id:
            # Persist so subsequent page loads skip resolution entirely
            try:
                Scheme.objects.filter(pk=scheme.pk).update(morningstar_id=sec_id)
                scheme.morningstar_id = sec_id  # update in-memory too
            except Exception:
                pass

    if not sec_id:
        return {}

    terms = [sec_id]
    cache_key = f"fund:mstarpy:v1:{scheme.amfi_code}:{md5(sec_id.encode('utf-8')).hexdigest()}"
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
    """Fetch holdings, sectors, and asset allocation directly from Morningstar REST APIs."""
    api_key = "lstzFDEOhfFNMLikKa0am9mgEKLBl49T"
    headers = {
        "apikey": api_key,
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    params_holdings = {"clientId": "MDC", "version": "4.71.0", "premiumNum": 10000, "freeNum": 10000}
    params_default  = {"clientId": "MDC", "version": "4.71.0"}

    for term in terms:
        sec_id = str(term or "").strip()
        # The Morningstar REST API accepts all SecId formats:
        # F0xxxx (funds), 0Pxxxx (ETFs), FOUSAxxxxx (older US-listed), F0GBRxxxx (UK-listed), etc.
        # Do NOT filter by prefix — let the HTTP response determine validity.
        if not sec_id:
            continue
        try:
            # 1. Holdings
            h_url = f"https://api-global.morningstar.com/sal-service/v1/fund/portfolio/holding/v2/{sec_id}/data"
            h_resp = requests.get(h_url, headers=headers, params=params_holdings, timeout=12)
            if h_resp.status_code != 200:
                continue
            h_json = h_resp.json()
            if not isinstance(h_json, dict):
                continue

            eq_list = h_json.get("equityHoldingPage", {}).get("holdingList", []) or []
            bd_list = h_json.get("boldHoldingPage", {}).get("holdingList", []) or []
            ot_list = h_json.get("otherHoldingPage", {}).get("holdingList", []) or []
            all_raw = eq_list + bd_list + ot_list
            if not all_raw:
                continue

            holdings_raw = []
            for row in all_raw:
                holdings_raw.append({
                    "securityName":  row.get("securityName", ""),
                    "weighting":     row.get("weighting"),
                    "sector":        row.get("sector") or row.get("superSectorName") or "",
                    "isin":          row.get("isin", ""),
                    "ticker":        row.get("ticker", ""),
                    "holdingType":   row.get("holdingType", "equity"),
                    "holdingTypeId": row.get("holdingTypeId", ""),
                    "forwardPERatio": row.get("forwardPERatio"),
                    "marketValue":   row.get("marketValue"),
                    "country":       row.get("country", ""),
                })

            # 2. Sectors (best-effort)
            sector_raw = {}
            try:
                s_url = f"https://api-global.morningstar.com/sal-service/v1/fund/portfolio/v2/sector/{sec_id}/data"
                s_resp = requests.get(s_url, headers=headers, params=params_default, timeout=8)
                if s_resp.status_code == 200:
                    sector_raw = s_resp.json() or {}
            except Exception:
                pass

            # 3. Asset Allocation (best-effort)
            allocation_raw = {}
            try:
                a_url = f"https://api-global.morningstar.com/sal-service/v1/fund/process/asset/{sec_id}/data"
                a_resp = requests.get(a_url, headers=headers, params=params_default, timeout=8)
                if a_resp.status_code == 200:
                    allocation_raw = a_resp.json() or {}
            except Exception:
                pass

            payload = {
                "meta": {"secId": sec_id},
                "holdings": holdings_raw,
                "sector":   sector_raw,
                "allocation": allocation_raw,
            }
            return payload

        except Exception as exc:
            logger.debug("[morningstar_rest] sec_id=%s error: %s", sec_id, exc)
            continue

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
        "cap_alloc": (primary.get("cap_alloc") if primary else None) or secondary.get("cap_alloc"),
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

        configure_yfinance_cache(yf)

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
        records = holdings_df.to_dict("records")
    rows = []
    for row in records:
        name = row.get("securityName") or row.get("holdingName")
        weight = _float(row.get("weighting") or row.get("weight") or row.get("holdingPercent"))
        if not name or weight is None or weight <= 0:
            continue
        sector = str(row.get("sector") or row.get("globalSectorName") or row.get("superSectorName") or "")
        # Morningstar holdingType: 'Equity', 'Bond', 'Other' (capitalized)
        # holdingTypeId: GS/B=bond, CP/CD/CR/CA/TB=cash, FO=fund, DD=commodity
        htype_raw = str(row.get("holdingType") or row.get("assetType") or "").lower()
        htype_id  = str(row.get("holdingTypeId") or "").upper()
        if htype_raw == "bond":
            htype = "debt"
        elif htype_raw == "equity":
            htype = "equity"
        elif htype_id in ("GS", "B", "NCD"):
            htype = "debt"
        elif htype_id in ("CP", "CD", "CR", "CA", "TB"):
            htype = "cash"
        else:
            htype = finapi_holding_type(str(name), sector)
        rows.append(ns(
            security_name=str(name),
            ticker=str(row.get("ticker") or row.get("symbol") or ""),
            isin=str(row.get("isin") or ""),
            sector=sector,
            weight_pct=weight * 100 if weight <= 1 else weight,
            forward_pe=_float(row.get("forwardPERatio") or row.get("forwardPE")),
            holding_type=htype,
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
    for row in holdings:
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


def build_meta(scheme: Scheme, mfapi_meta: dict, db_meta: dict, captnemo: dict, yahoo: dict, nav_series: pd.Series) -> SimpleNamespace:
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
    data.update({k: v for k, v in db_meta.items() if v not in (None, "", [])})
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
    for period, attr in {"1W": "returns_1w", "1M": "returns_1m", "3M": "returns_3m", "1Y": "returns_1y", "3Y": "returns_3y", "5Y": "returns_5y", "SI": "returns_inception"}.items():
        if data.get(attr) is None:
            match = next((r for r in trailing_from_nav if r.period == period), None)
            if match:
                data[attr] = match.cagr_pct
    data["lock_in_label"] = format_lock_in(data.get("lock_in_period"))
    return ns(**data)


def compute_trailing_returns(nav: pd.Series, bm: pd.Series) -> list[SimpleNamespace]:
    if nav.empty:
        return []
    specs = [("1W", 7), ("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365), ("2Y", 730), ("3Y", 1095), ("5Y", 1826), ("7Y", 2557), ("10Y", 3652), ("SI", None)]
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
    window = series[(series.index >= start_date) & (series.index <= end_date)]
    if len(window) < 2:
        return None
    start = float(window.iloc[0])
    end = float(window.iloc[-1])
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


def compute_rolling_returns(nav: pd.Series, bm: pd.Series | None = None) -> dict[str, SimpleNamespace]:
    result = {}
    if nav.empty or not isinstance(nav.index, pd.DatetimeIndex):
        return result
    daily = nav.resample("B").ffill().dropna()
    # Align benchmark if provided
    bm_daily = bm.resample("B").ffill().dropna() if bm is not None and not bm.empty else pd.Series(dtype=float)

    for window, days in [("1Y", 252), ("2Y", 504), ("3Y", 756), ("5Y", 1260), ("7Y", 1764), ("10Y", 2520)]:
        if len(daily) <= days:
            continue
        rolling = ((daily / daily.shift(days)) ** (252 / days) - 1) * 100
        rolling = rolling.dropna()
        if rolling.empty:
            continue

        # Benchmark rolling stats
        bm_min = bm_max = bm_mean = bm_median = outperformance_rate = None
        if len(bm_daily) > days:
            bm_rolling = ((bm_daily / bm_daily.shift(days)) ** (252 / days) - 1) * 100
            bm_rolling = bm_rolling.dropna()
            if not bm_rolling.empty:
                aligned = pd.concat([rolling.rename("fund"), bm_rolling.rename("bm")], axis=1, join="inner").dropna()
                if not aligned.empty:
                    bm_min = float(aligned["bm"].min())
                    bm_max = float(aligned["bm"].max())
                    bm_mean = float(aligned["bm"].mean())
                    bm_median = float(aligned["bm"].median())
                    outperformance_rate = float((aligned["fund"] > aligned["bm"]).mean() * 100)

        result[window] = ns(
            window=window,
            window_days=days,
            min_pct=float(rolling.min()),
            max_pct=float(rolling.max()),
            mean_pct=float(rolling.mean()),
            median_pct=float(rolling.median()),
            std_dev=float(rolling.std()),
            win_rate_0=float((rolling > 0).mean() * 100),
            win_rate_8=float((rolling > 8).mean() * 100),
            win_rate_12=float((rolling > 12).mean() * 100),
            bm_min=bm_min,
            bm_max=bm_max,
            bm_mean=bm_mean,
            bm_median=bm_median,
            outperformance_rate=outperformance_rate,
            as_of=nav.index[-1].date(),
        )
    return result


def compute_yearly_risk_metrics(nav: pd.Series, bm: pd.Series | None = None) -> list[SimpleNamespace]:
    """Per-calendar-year fund vs benchmark risk breakdown.

    Returns a list of SimpleNamespace (one per year), sorted newest-first.
    Partial first year is included and labelled with `is_partial=True`.
    """
    if nav.empty or not isinstance(nav.index, pd.DatetimeIndex):
        return []
    rf = float(getattr(settings, "RF_ANNUAL_RATE", 0.065))
    bm_daily = bm.resample("B").ffill().dropna() if bm is not None and not bm.empty else pd.Series(dtype=float)

    start_year = nav.index[0].year
    end_year = nav.index[-1].year
    rows = []

    for year in range(end_year, start_year - 1, -1):
        y_start = pd.Timestamp(f"{year}-01-01")
        y_end = pd.Timestamp(f"{year}-12-31")
        s = nav[(nav.index >= y_start) & (nav.index <= y_end)]
        if len(s) < 20:
            continue
        is_partial = (year == start_year and nav.index[0].month > 1)

        ret = s.pct_change().dropna()
        std = float(ret.std() * np.sqrt(252) * 100) if len(ret) > 5 else None
        fund_cagr = cagr_for_window(s, s.index[0], s.index[-1])
        ann_ret = fund_cagr or 0
        downside = ret[ret < 0].std() * np.sqrt(252) * 100 if len(ret) > 5 else None
        sharpe = ((ann_ret - rf * 100) / std) if std else None
        sortino = ((ann_ret - rf * 100) / downside) if downside else None
        dd_list = compute_drawdown(s)
        max_dd = min((d.drawdown for d in dd_list), default=None)

        bm_cagr = alpha = beta = upside_cap = downside_cap = bm_std = None
        if not bm_daily.empty:
            b = bm_daily[(bm_daily.index >= y_start) & (bm_daily.index <= y_end)]
            if len(b) > 20:
                bm_cagr = cagr_for_window(b, b.index[0], b.index[-1])
                bm_ret = b.pct_change().dropna()
                bm_std = float(bm_ret.std() * np.sqrt(252) * 100)
                aligned_prices = pd.concat(
                    [s.resample("B").ffill().rename("fund"), b.resample("B").ffill().rename("bm")],
                    axis=1, join="inner",
                ).dropna()
                aligned = aligned_prices.pct_change().dropna()
                if len(aligned) > 10:
                    var = aligned["bm"].var()
                    if var:
                        cov = aligned.cov().loc["fund", "bm"]
                        beta = cov / var
                        bm_ann = ((1 + aligned["bm"]).prod() ** (252 / len(aligned)) - 1) * 100
                        alpha = ann_ret - (rf * 100 + beta * (bm_ann - rf * 100))
                    up = aligned[aligned["bm"] > 0]
                    down = aligned[aligned["bm"] < 0]
                    upside_cap = (up["fund"].mean() / up["bm"].mean() * 100) if len(up) and up["bm"].mean() else None
                    downside_cap = (down["fund"].mean() / down["bm"].mean() * 100) if len(down) and down["bm"].mean() else None

        rows.append(ns(
            year=year,
            is_partial=is_partial,
            days=len(s),
            fund_cagr=fund_cagr,
            bm_cagr=bm_cagr,
            alpha=alpha,
            beta=beta,
            std_dev=std,
            bm_std=bm_std,
            sharpe=sharpe,
            sortino=sortino,
            max_drawdown=max_dd,
            upside_capture=upside_cap,
            downside_capture=downside_cap,
            beat_benchmark=(fund_cagr > bm_cagr) if fund_cagr is not None and bm_cagr is not None else None,
        ))

    return rows


def compute_risk_metrics(nav: pd.Series, bm: pd.Series) -> dict[str, SimpleNamespace]:
    result = {}
    if nav.empty or not isinstance(nav.index, pd.DatetimeIndex):
        return result
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
            aligned_prices = pd.concat(
                [
                    s.resample("B").ffill().rename("fund"),
                    b.resample("B").ffill().rename("benchmark"),
                ],
                axis=1,
                join="inner",
            ).dropna()
            aligned = aligned_prices.pct_change().dropna()
            if len(aligned) > 30:
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

def compute_quarterly_performance(nav: pd.Series, bm: pd.Series) -> dict[str, list[dict]]:
    results = {"upside": [], "downside": []}
    if nav.empty:
        return results
        
    nav_q = nav.resample("QS").last().dropna()
    bm_q = bm.resample("QS").last().dropna() if not bm.empty else pd.Series(dtype=float)
    
    if len(nav_q) < 2:
        return results
        
    for i in range(1, len(nav_q)):
        sv = float(nav_q.iloc[i - 1])
        ev = float(nav_q.iloc[i])
        if sv <= 0:
            continue
        ret = (ev / sv - 1) * 100
        
        qstart = nav_q.index[i - 1]
        
        bm_ret = None
        if not bm_q.empty and qstart in bm_q.index and nav_q.index[i] in bm_q.index:
            try:
                bm_sv = float(bm_q.loc[qstart])
                bm_ev = float(bm_q.loc[nav_q.index[i]])
                if bm_sv > 0:
                    bm_ret = (bm_ev / bm_sv - 1) * 100
            except KeyError:
                pass
                
        quarter_data = {
            "quarter": f"Q{(qstart.month - 1) // 3 + 1} {qstart.year}",
            "fund_return": round(ret, 2),
            "benchmark_return": round(bm_ret, 2) if bm_ret is not None else None,
        }
        
        if ret > 0:
            results["upside"].append(quarter_data)
        elif ret < 0:
            results["downside"].append(quarter_data)
            
    results["upside"].sort(key=lambda x: x["fund_return"], reverse=True)
    results["downside"].sort(key=lambda x: x["fund_return"])
    
    return results



# ── Historical Crisis Periods ────────────────────────────────────────────────
_CRISIS_PERIODS = [
    # (label, crash_start, crash_end, recovery_end_approx, description)
    # crash_start/crash_end: the peak-to-trough window
    # recovery_end_approx: approximate date of full recovery to prior peak
    {
        "label": "COVID-19 Crash",
        "short": "COVID-19",
        "crash_start": "2020-01-17",
        "crash_end": "2020-03-23",
        "recovery_end": "2020-08-01",
        "description": "Sharp global sell-off as COVID-19 spread; Nifty fell ~38% in 6 weeks, recovered by Aug 2020.",
    },
    {
        "label": "2022 Rate Hike Cycle",
        "short": "2022 Rate Hike",
        "crash_start": "2022-01-18",
        "crash_end": "2022-06-17",
        "recovery_end": "2022-12-01",
        "description": "RBI and global central bank rate hikes crushed growth stocks; Nifty fell ~17% peak-to-trough.",
    },
    {
        "label": "2018 IL&FS Crisis",
        "short": "2018 IL&FS",
        "crash_start": "2018-08-28",
        "crash_end": "2018-10-26",
        "recovery_end": "2019-05-01",
        "description": "IL&FS default triggered credit market fears; Nifty fell ~15%, small/midcap much harder hit.",
    },
    {
        "label": "2024–25 Tariff Shock",
        "short": "2024-25 Tariff",
        "crash_start": "2024-09-27",
        "crash_end": "2025-04-07",
        "recovery_end": None,   # ongoing / TBD
        "description": "Global tariff escalation and FII outflows drove a prolonged correction in Indian equities.",
    },
    {
        "label": "2015–16 China Slowdown",
        "short": "2015-16 China",
        "crash_start": "2015-03-04",
        "crash_end": "2016-02-11",
        "recovery_end": "2016-11-01",
        "description": "China growth fears and commodity price crash dragged EMs; Nifty fell ~23% over 11 months.",
    },
    {
        "label": "2008 Global Financial Crisis",
        "short": "2008 GFC",
        "crash_start": "2008-01-08",
        "crash_end": "2009-03-09",
        "recovery_end": "2010-11-01",
        "description": "Subprime mortgage collapse caused the worst global recession in decades; Nifty fell ~65%.",
    },
]


def compute_crisis_periods(nav: pd.Series) -> list[SimpleNamespace]:
    """
    For each historical crisis window, compute:
    - crash_return: NAV return during the crash window (crash_start → crash_end)
    - recovery_months: calendar months from trough to recovery (if applicable)
    - available: True if the fund existed during this period
    Returns a list of SimpleNamespace objects sorted by crash_start desc.
    """
    if nav.empty or not isinstance(nav.index, pd.DatetimeIndex):
        return []

    results = []
    fund_start = nav.index[0]
    fund_end = nav.index[-1]

    for cp in _CRISIS_PERIODS:
        cs = pd.Timestamp(cp["crash_start"])
        ce = pd.Timestamp(cp["crash_end"])
        re_date = pd.Timestamp(cp["recovery_end"]) if cp["recovery_end"] else None

        # Check if fund existed during crash
        fund_existed = fund_start <= ce  # fund launched before crash trough
        pre_inception = fund_start > cs  # fund didn't exist at crash start

        crash_return = None
        recovery_months = None
        trough_recovery_label = None

        if fund_existed:
            # Align to fund's actual range
            actual_start = max(cs, fund_start)
            actual_end = min(ce, fund_end)

            try:
                s_slice = nav.loc[actual_start:actual_end]
                if not s_slice.empty and len(s_slice) >= 2:
                    sv = float(s_slice.iloc[0])
                    ev = float(s_slice.iloc[-1])
                    if sv > 0:
                        crash_return = round((ev / sv - 1) * 100, 1)
            except Exception:
                pass

            # Recovery: how many months from trough to re_date
            if re_date and ce <= fund_end:
                if re_date <= fund_end:
                    recovery_months = round(
                        (re_date - ce).days / 30.44
                    )
                    trough_recovery_label = f"Rec: {re_date.strftime('%b %Y')} ({recovery_months} mo)"
                else:
                    # Still not recovered by fund's last nav
                    trough_recovery_label = "Not yet recovered"
            elif re_date is None:
                trough_recovery_label = "Recovery TBD"

        results.append(ns(
            label=cp["label"],
            short=cp["short"],
            crash_start=cs.strftime("%b %Y"),
            crash_end=ce.strftime("%b %Y"),
            crash_return=crash_return,
            recovery_months=recovery_months,
            recovery_label=trough_recovery_label,
            description=cp["description"],
            available=fund_existed,
            pre_inception=pre_inception,
        ))

    # Most recent first
    results.sort(key=lambda x: x.crash_end, reverse=True)
    return results


# ── Market Regime Analysis ───────────────────────────────────────────────────
_MARKET_REGIMES = [
    {
        "label": "Bull Market",
        "icon": "📈",
        "color": "#10b981",
        "description": "Strong sustained uptrend (>20% from lows)",
        "windows": [
            ("2014-02-01", "2015-03-04"),
            ("2016-02-11", "2018-01-29"),
            ("2020-03-23", "2021-10-19"),
            ("2023-03-28", "2024-09-27"),
        ],
    },
    {
        "label": "Bear Market",
        "icon": "📉",
        "color": "#ef4444",
        "description": "Sustained decline >20% from recent highs",
        "windows": [
            ("2008-01-08", "2009-03-09"),
            ("2015-03-04", "2016-02-11"),
            ("2018-08-28", "2018-10-26"),
            ("2020-01-17", "2020-03-23"),
            ("2024-09-27", "2025-04-07"),
        ],
    },
    {
        "label": "Sideways / Consolidation",
        "icon": "↔️",
        "color": "#f59e0b",
        "description": "Range-bound market, low trend conviction",
        "windows": [
            ("2010-11-01", "2013-09-01"),
            ("2021-10-19", "2023-03-28"),
        ],
    },
    {
        "label": "High Inflation Period",
        "icon": "🔥",
        "color": "#f97316",
        "description": "CPI/WPI elevated >6%; RBI tightening",
        "windows": [
            ("2010-01-01", "2013-12-31"),
            ("2022-01-01", "2023-02-28"),
        ],
    },
    {
        "label": "Rate Cut Cycle",
        "icon": "✂️",
        "color": "#6366f1",
        "description": "RBI cutting repo rate; liquidity supportive",
        "windows": [
            ("2019-02-07", "2019-10-04"),
            ("2020-03-27", "2022-04-08"),
            ("2025-02-07", "2025-06-06"),
        ],
    },
]


def compute_market_regimes(nav: pd.Series) -> list[SimpleNamespace]:
    """
    For each regime type, aggregate the fund's annualised return across
    all regime windows where the fund existed, and count total months.
    """
    if nav.empty or not isinstance(nav.index, pd.DatetimeIndex):
        return []

    fund_start = nav.index[0]
    fund_end = nav.index[-1]
    results = []

    for regime in _MARKET_REGIMES:
        total_days = 0
        weighted_cagr_sum = 0.0
        covered_windows = 0
        windows_detail = []

        for w_start_str, w_end_str in regime["windows"]:
            ws = pd.Timestamp(w_start_str)
            we = pd.Timestamp(w_end_str)
            actual_s = max(ws, fund_start)
            actual_e = min(we, fund_end)

            if actual_s >= actual_e:
                continue  # fund didn't exist in this window

            try:
                s_slice = nav.loc[actual_s:actual_e]
                if len(s_slice) < 10:
                    continue
                sv = float(s_slice.iloc[0])
                ev = float(s_slice.iloc[-1])
                if sv <= 0:
                    continue
                days = (actual_e - actual_s).days
                if days < 10:
                    continue
                ann_ret = ((ev / sv) ** (365 / days) - 1) * 100
                total_days += days
                weighted_cagr_sum += ann_ret * days
                covered_windows += 1
                windows_detail.append(ns(
                    start=actual_s.strftime("%b %Y"),
                    end=actual_e.strftime("%b %Y"),
                    months=round(days / 30.44),
                    cagr=round(ann_ret, 1),
                ))
            except Exception:
                continue

        avg_cagr = round(weighted_cagr_sum / total_days, 1) if total_days > 0 else None
        total_months = round(total_days / 30.44)

        results.append(ns(
            label=regime["label"],
            icon=regime["icon"],
            color=regime["color"],
            description=regime["description"],
            avg_cagr=avg_cagr,
            total_months=total_months,
            covered_windows=covered_windows,
            windows=windows_detail,
        ))

    return results


def empty_benchmark_result(name: str | None = None) -> SimpleNamespace:

    return ns(
        requested_name=name,
        actual_name=None,
        display_name=name,
        ticker="",
        tickers=(),
        source="unavailable",
        fallback_used=False,
        note="",
        series=pd.Series(dtype=float),
    )


def fetch_benchmark_result(name: str | None, nav: pd.Series) -> SimpleNamespace:
    if not name or nav.empty:
        return empty_benchmark_result(name)

    start = nav.index[0] - pd.Timedelta(days=10)
    yahoo_candidates = list(iter_benchmark_candidates(name))
    db_fallback_candidates = [candidate.benchmark_name for candidate in yahoo_candidates if candidate.is_fallback]

    for candidate_name in [name]:
        series = fetch_db_benchmark_series(candidate_name, start)
        if len(series) >= 2:
            return ns(
                requested_name=name,
                actual_name=candidate_name,
                display_name=candidate_name,
                ticker="database",
                tickers=(),
                source="database",
                fallback_used=False,
                note="",
                series=series,
            )

    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(fetch_yahoo_history_for_benchmark, name, start_date=start.date(), min_rows=2)
            series, candidate = future.result(timeout=12)
    except concurrent.futures.TimeoutError:
        logger.info("Benchmark fetch timed out for %s (>12s)", name)
        series, candidate = pd.Series(dtype=float), None
    except Exception as exc:
        logger.info("Benchmark fetch error for %s: %s", name, exc)
        series, candidate = pd.Series(dtype=float), None
    # Minimum useful rows: 1 year of data (252 trading days).
    # Yahoo sometimes returns a tiny partial result for certain tickers/regions.
    # In that case we fall through to the DB fallback which usually has more data.
    YAHOO_MIN_ROWS = 252
    if candidate is not None and len(series) >= 2:
        # Check if DB has significantly more data — prefer DB when Yahoo is tiny
        is_tiny_yahoo = len(series) < YAHOO_MIN_ROWS
        if is_tiny_yahoo:
            # Try the DB fallback first; if DB has >=252 rows, use that instead.
            # Also try NIFTY 50 as ultimate fallback if db_fallback_candidates is empty
            # (e.g., an index with a direct but broken Yahoo ticker like ^CNX100)
            fallback_names = list(dict.fromkeys(db_fallback_candidates)) or ['NIFTY 50']
            for fb_name in fallback_names:
                fb_series = fetch_db_benchmark_series(fb_name, None)  # no date filter for full history
                if len(fb_series) >= YAHOO_MIN_ROWS:
                    logger.info(
                        "Yahoo returned tiny result (%d rows) for %s; preferring DB fallback %s (%d rows)",
                        len(series), name, fb_name, len(fb_series),
                    )
                    is_n50_proxy = (fb_name == 'NIFTY 50' and fb_name != name)
                    return ns(
                        requested_name=name,
                        actual_name=fb_name,
                        display_name=f"NIFTY 50 (proxy for {name})" if is_n50_proxy else f"{name} via {fb_name}",
                        ticker="database",
                        tickers=tuple(c.yahoo_ticker for c in yahoo_candidates),
                        source="database fallback",
                        fallback_used=True,
                        note=(
                            f"No confirmed Yahoo Finance ticker for '{name}'. "
                            "NIFTY 50 is used as a proxy - comparisons are approximate."
                        ) if is_n50_proxy else f"{name} has no stored history; using {fb_name} as fallback.",
                        series=fb_series,
                    )
        fallback_used = candidate.is_fallback or candidate.is_proxy
        if candidate.is_proxy:
            display_name = f"{candidate.benchmark_name} proxy"
            source = f"{candidate.source} proxy"
        elif candidate.is_fallback:
            if candidate.benchmark_name == "NIFTY 50":
                display_name = f"NIFTY 50 (proxy for {name})"
                note = candidate.note or (
                    f"No confirmed Yahoo Finance ticker for '{name}'. "
                    "NIFTY 50 is used as a proxy — comparisons are approximate."
                )
            else:
                display_name = f"{name} via {candidate.benchmark_name}"
                note = candidate.note
            source = f"{candidate.source} fallback"
        else:
            display_name = candidate.benchmark_name
            source = candidate.source
        return ns(
            requested_name=name,
            actual_name=candidate.benchmark_name,
            display_name=display_name,
            ticker=candidate.yahoo_ticker,
            tickers=tuple(c.yahoo_ticker for c in yahoo_candidates),
            source=source,
            fallback_used=fallback_used,
            note=candidate.note,
            series=series,
        )

    for candidate_name in dict.fromkeys(db_fallback_candidates):
        # Use no start_date filter to get all available DB history for the fallback index
        series = fetch_db_benchmark_series(candidate_name, None)
        if len(series) >= 2:
            return ns(
                requested_name=name,
                actual_name=candidate_name,
                display_name=f"{name} via {candidate_name}",
                ticker="database",
                tickers=tuple(c.yahoo_ticker for c in yahoo_candidates),
                source="database fallback",
                fallback_used=True,
                note=f"{name} has no stored or Yahoo-compatible history; using {candidate_name} as fallback.",
                series=series,
            )

    logger.info(
        "Benchmark unavailable for %s; tried %s",
        name,
        ", ".join(candidate.yahoo_ticker for candidate in yahoo_candidates) or "no Yahoo ticker",
    )
    result = empty_benchmark_result(name)
    result.actual_name = yahoo_candidates[0].benchmark_name if yahoo_candidates else None
    result.display_name = name
    result.tickers = tuple(candidate.yahoo_ticker for candidate in yahoo_candidates)
    result.fallback_used = any(candidate.is_fallback or candidate.is_proxy for candidate in yahoo_candidates)
    result.note = next((candidate.note for candidate in yahoo_candidates if candidate.note), "")
    return result


def fetch_benchmark_series(name: str, nav: pd.Series) -> pd.Series:
    return fetch_benchmark_result(name, nav).series


def fetch_db_benchmark_series(name: str, start_date: pd.Timestamp | None = None) -> pd.Series:
    try:
        from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV

        index = BenchmarkIndex.objects.filter(name__iexact=name).first()
        if not index:
            return pd.Series(dtype=float)
        qs = BenchmarkNAV.objects.filter(index=index)
        if start_date is not None:
            qs = qs.filter(date__gte=start_date.date())
        rows = list(qs.order_by("date").values("date", "close"))
        if not rows:
            return pd.Series(dtype=float)
        series = pd.Series({pd.Timestamp(row["date"]): float(row["close"]) for row in rows})
        series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
        return series.sort_index()
    except Exception as exc:
        logger.info("DB benchmark fetch failed for %s: %s", name, exc)
        return pd.Series(dtype=float)


def fetch_yfinance_benchmark_series(ticker: str) -> pd.Series:
    cache_key = f"benchmark:yf:v3:{ticker}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        import yfinance as yf

        configure_yfinance_cache(yf)

        hist = yf.Ticker(ticker).history(period="max", auto_adjust=False, raise_errors=False)
        if hist is None or hist.empty or "Close" not in hist:
            return pd.Series(dtype=float)
        series = hist["Close"].dropna()
        series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
        series = series[~series.index.duplicated(keep="last")].sort_index()
        cache.set(cache_key, series, BENCHMARK_TTL)
        return series
    except Exception as exc:
        logger.info("Benchmark fetch failed for %s: %s", ticker, exc)
        return pd.Series(dtype=float)


def benchmark_for(category: str, name: str = "") -> str | None:
    return registry_benchmark_for(category, name)


def infer_category(name: str) -> str:
    return registry_infer_category(name)


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


# ── SEBI category keywords extracted from AMFI scheme names ──────────────────
# Maps keyword tokens (lowercase, in order of specificity) that appear in the
# fund name to a canonical category label used for grouping.
_SEBI_KEYWORD_MAP: list[tuple[tuple[str, ...], str]] = [
    # Thematic / Sectoral — check before generic equity
    (("banking", "financial", "psu", "financi"), "Thematic-Banking&Financial"),
    (("technology", "tech", "information technology", "it fund"), "Thematic-Technology"),
    (("pharma", "healthcare", "health care"), "Thematic-Pharma"),
    (("infrastructure", "infra"), "Thematic-Infrastructure"),
    (("consumption", "consumer"), "Thematic-Consumption"),
    (("energy", "power", "utilities"), "Thematic-Energy"),
    (("mnc",), "Thematic-MNC"),
    (("esg",), "Thematic-ESG"),
    (("dividend",), "Thematic-Dividend"),
    (("transportation", "logistics"), "Thematic-Transportation"),
    (("realty", "real estate"), "Thematic-Realty"),
    (("manufacturing",), "Thematic-Manufacturing"),
    (("business cycle",), "Thematic-BusinessCycle"),
    (("quant",), "Thematic-Quant"),
    # Index / ETF / FoF
    (("index", "nifty", "sensex", "bse"), "Index"),
    (("etf",), "ETF"),
    (("fund of fund", "fof", "overseas", "international", "global"), "FoF"),
    # Hybrid
    (("balanced advantage", "dynamic asset allocation"), "Hybrid-BalancedAdvantage"),
    (("aggressive hybrid", "equity hybrid"), "Hybrid-Aggressive"),
    (("conservative hybrid",), "Hybrid-Conservative"),
    (("multi asset", "multi-asset"), "Hybrid-MultiAsset"),
    (("arbitrage",), "Hybrid-Arbitrage"),
    (("equity savings",), "Hybrid-EquitySavings"),
    (("balanced hybrid",), "Hybrid-Balanced"),
    # Equity categories — check after thematic
    (("elss", "tax saver", "tax saving"), "Equity-ELSS"),
    (("flexi cap", "flexicap", "multi cap", "multicap"), "Equity-FlexiCap"),
    (("large and mid", "large & mid"), "Equity-LargeMidCap"),
    (("large cap", "largecap", "bluechip", "blue chip"), "Equity-LargeCap"),
    (("mid cap", "midcap", "mid-cap"), "Equity-MidCap"),
    (("small cap", "smallcap", "small-cap"), "Equity-SmallCap"),
    (("value fund", "value and contra", "contra fund"), "Equity-Value"),
    (("focused fund", "focus fund"), "Equity-Focused"),
    # Debt categories
    (("overnight",), "Debt-Overnight"),
    (("liquid fund", "liquid plan"), "Debt-Liquid"),
    (("ultra short", "ultrashort"), "Debt-UltraShort"),
    (("low duration",), "Debt-LowDuration"),
    (("money market",), "Debt-MoneyMarket"),
    (("short duration", "short term"), "Debt-Short"),
    (("medium duration",), "Debt-Medium"),
    (("medium to long", "medium and long"), "Debt-MediumLong"),
    (("long duration", "long term"), "Debt-Long"),
    (("dynamic bond", "dynamic debt"), "Debt-Dynamic"),
    (("corporate bond", "corp bond"), "Debt-Corporate"),
    (("credit risk", "credit fund"), "Debt-CreditRisk"),
    (("banking and psu", "banking & psu"), "Debt-BankingPSU"),
    (("gilt", "g-sec", "gsec"), "Debt-Gilt"),
    (("floater",), "Debt-Floater"),
    # Solution-oriented
    (("retirement",), "Solution-Retirement"),
    (("children", "child"), "Solution-Children"),
]


def _extract_category_from_name(name: str) -> str:
    """Extract a normalised SEBI-like category label from a fund scheme name.

    Returns a string such as 'Equity-FlexiCap', 'Debt-Liquid', etc., or '' if
    no category keyword is found.
    """
    name_lower = name.lower()
    for keywords, category in _SEBI_KEYWORD_MAP:
        if any(kw in name_lower for kw in keywords):
            return category
    return ""


def find_peer_funds(scheme: Scheme, max_peers: int = 5) -> list[Scheme]:
    """Return peer Schemes using the scored India peer engine.

    Kept as a compatibility wrapper for callers that only need scheme objects.
    Use ``apps.funds.peers.get_peer_matches`` when score/reason metadata is
    needed.
    """
    from apps.funds.peers import get_peer_matches

    return [match.scheme for match in get_peer_matches(scheme, max_peers=max_peers)]


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
