"""
Shared benchmark registry and Yahoo Finance retrieval helpers.

The notebook exploration found yfinance/yahooquery to be the most practical
fallback for benchmark history, but several older ticker guesses no longer
return usable data. Keep the mapping here so page analytics, market headers,
and ingestion use the same verified symbols.
"""
from __future__ import annotations

import logging
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import md5
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

logger = logging.getLogger("mfanalysis")

BENCHMARK_TTL = 60 * 60 * 6
NIFTYINDICES_BASE = "https://www.niftyindices.com"
NIFTYINDICES_ASSET_BASE = "https://iislliveblob.niftyindices.com"


@dataclass(frozen=True)
class BenchmarkDefinition:
    name: str
    yahoo_tickers: tuple[str, ...] = ()
    proxy_tickers: tuple[tuple[str, str], ...] = ()
    fallback: str | None = None
    aliases: tuple[str, ...] = ()
    nse_name: str | None = None
    field: str = "Close"


@dataclass(frozen=True)
class BenchmarkCandidate:
    requested_name: str
    benchmark_name: str
    yahoo_ticker: str
    field: str = "Close"
    is_proxy: bool = False
    is_fallback: bool = False
    note: str = ""
    source: str = "yfinance"


@dataclass(frozen=True)
class BenchmarkResolution:
    requested_name: str
    actual_name: str
    yahoo_tickers: tuple[str, ...]
    fallback_used: bool = False
    note: str = ""

    @property
    def primary_ticker(self) -> str:
        return self.yahoo_tickers[0] if self.yahoo_tickers else ""

    @property
    def display_name(self) -> str:
        if self.fallback_used:
            return f"{self.requested_name} via {self.actual_name}"
        return self.actual_name


BENCHMARK_DEFINITIONS: dict[str, BenchmarkDefinition] = {
    "NIFTY 50": BenchmarkDefinition("NIFTY 50", ("^NSEI",), aliases=("NIFTY50", "NSE NIFTY")),
    "SENSEX": BenchmarkDefinition("SENSEX", ("^BSESN",), aliases=("BSE SENSEX", "S&P BSE SENSEX")),
    "NIFTY BANK": BenchmarkDefinition("NIFTY BANK", ("^NSEBANK",), aliases=("BANK NIFTY", "NIFTY BANK INDEX")),
    "NIFTY 100": BenchmarkDefinition("NIFTY 100", ("^CNX100",), aliases=("NIFTY100",)),
    "NIFTY 200": BenchmarkDefinition(
        "NIFTY 200",
        ("^CNX200",),
        aliases=("NIFTY200", "CNX 200"),
    ),
    "NIFTY 500": BenchmarkDefinition("NIFTY 500", ("^CRSLDX",), aliases=("NIFTY500",)),
    "NIFTY NEXT 50": BenchmarkDefinition("NIFTY NEXT 50", ("^NSMIDCP",), aliases=("NIFTY NEXT50", "NEXT 50")),
    "NIFTY MIDCAP 50": BenchmarkDefinition("NIFTY MIDCAP 50", ("^NSEMDCP50",), aliases=("MIDCAP 50",)),
    "NIFTY MIDCAP 100": BenchmarkDefinition("NIFTY MIDCAP 100", ("NIFTY_MIDCAP_100.NS",)),
    "NIFTY MIDCAP 150": BenchmarkDefinition(
        "NIFTY MIDCAP 150",
        ("NIFTYMIDCAP150.NS", "^CRSMID"),
        aliases=("NIFTY MIDCAP150", "MIDCAP 150"),
    ),
    "NIFTY SMALLCAP 50": BenchmarkDefinition(
        "NIFTY SMALLCAP 50",
        # NIFTYSMLCAP50.NS is delisted on Yahoo — ^CNXSC (Smallcap 100) used as closest proxy
        ("^CNXSC", "NIFTYSMLCAP50.NS"),
        aliases=("NIFTY SMLCAP 50", "SMALLCAP 50"),
        nse_name="NIFTY SMLCAP 50",
    ),
    "NIFTY SMALLCAP 100": BenchmarkDefinition(
        "NIFTY SMALLCAP 100",
        ("^CNXSC",),
        aliases=("NIFTY SMLCAP 100", "SMALLCAP 100"),
        nse_name="NIFTY SMLCAP 100",
    ),
    "NIFTY SMALLCAP 250": BenchmarkDefinition(
        "NIFTY SMALLCAP 250",
        ("NIFTYSMLCAP250.NS",),
        aliases=("NIFTY SMLCAP 250", "SMALLCAP 250"),
        nse_name="NIFTY SMLCAP 250",
    ),
    "NIFTY IT": BenchmarkDefinition("NIFTY IT", ("^CNXIT",)),
    "NIFTY PHARMA": BenchmarkDefinition("NIFTY PHARMA", ("^CNXPHARMA",)),
    "NIFTY FMCG": BenchmarkDefinition("NIFTY FMCG", ("^CNXFMCG",)),
    "S&P 500": BenchmarkDefinition("S&P 500", ("^GSPC",), aliases=("SP500", "SNP 500")),
    "NASDAQ 100": BenchmarkDefinition("NASDAQ 100", ("^NDX",), aliases=("NASDAQ100",)),
    "DOW JONES": BenchmarkDefinition("DOW JONES", ("^DJI",), aliases=("DJIA",)),
    "USD/INR": BenchmarkDefinition("USD/INR", ("USDINR=X",), aliases=("INR/USD", "USDINR")),
}

BENCHMARKS = BENCHMARK_DEFINITIONS


CATEGORY_BENCHMARK_MAP: dict[str, str | None] = {
    "Equity Scheme - Large Cap Fund": "NIFTY 100",
    "Equity Scheme - Mid Cap Fund": "NIFTY MIDCAP 150",
    "Equity Scheme - Small Cap Fund": "NIFTY SMALLCAP 250",
    "Equity Scheme - Flexi Cap Fund": "NIFTY 500",
    "Equity Scheme - Multi Cap Fund": "NIFTY 500",
    "Equity Scheme - ELSS": "NIFTY 50",
    "Equity Scheme - Large & Mid Cap Fund": "NIFTY 200",
    "Equity Scheme - Value Fund": "NIFTY 500",
    "Equity Scheme - Contra Fund": "NIFTY 500",
    "Equity Scheme - Focused Fund": "NIFTY 500",
    "Equity Scheme - Dividend Yield Fund": "NIFTY 500",
    "Equity Scheme - Index Funds": "NIFTY 50",
    "Equity Scheme - ETFs": "NIFTY 50",
    "Hybrid Scheme - Aggressive Hybrid Fund": "NIFTY 500",
    "Hybrid Scheme - Balanced Hybrid Fund": "NIFTY 500",
    "Hybrid Scheme - Conservative Hybrid Fund": "NIFTY 50",
    "Hybrid Scheme - Dynamic Asset Allocation": "NIFTY 500",
    "Hybrid Scheme - Multi Asset Allocation": "NIFTY 500",
    "Hybrid Scheme - Arbitrage Fund": None,
    "Debt Scheme - Liquid Fund": None,
    "Debt Scheme - Ultra Short Duration Fund": None,
    "Debt Scheme - Low Duration Fund": None,
    "Debt Scheme - Short Duration Fund": None,
    "Debt Scheme - Medium Duration Fund": None,
    "Debt Scheme - Long Duration Fund": None,
    "Debt Scheme - Dynamic Bond": None,
    "Debt Scheme - Corporate Bond Fund": None,
    "Debt Scheme - Credit Risk Fund": None,
    "Debt Scheme - Gilt Fund": None,
    "Debt Scheme - Overnight Fund": None,
    "Debt Scheme - Money Market Fund": None,
    "Solution Oriented Scheme - Retirement Fund": "NIFTY 500",
    "Solution Oriented Scheme - Childrens Fund": "NIFTY 500",
    "Other Scheme - FoF Domestic": None,
    "Other Scheme - FoF Overseas": None,
}

CATEGORY_BENCHMARK_RULES: tuple[tuple[str, str | None], ...] = (
    ("large & mid", "NIFTY 200"),
    ("small cap", "NIFTY SMALLCAP 250"),
    ("smallcap", "NIFTY SMALLCAP 250"),
    ("mid cap", "NIFTY MIDCAP 150"),
    ("midcap", "NIFTY MIDCAP 150"),
    ("large cap", "NIFTY 100"),
    ("flexi cap", "NIFTY 500"),
    ("multi cap", "NIFTY 500"),
    ("elss", "NIFTY 50"),
    ("tax saver", "NIFTY 50"),
    ("value", "NIFTY 500"),
    ("contra", "NIFTY 500"),
    ("focused", "NIFTY 500"),
    ("dividend yield", "NIFTY 500"),
    ("index", "NIFTY 50"),
    ("etf", "NIFTY 50"),
    ("aggressive hybrid", "NIFTY 500"),
    ("balanced hybrid", "NIFTY 500"),
)

EXPLICIT_INDEX_RULES: tuple[tuple[str, str], ...] = (
    (r"\bnifty\s+small\s*cap\s+250\b|\bsmall\s*cap\s+250\b", "NIFTY SMALLCAP 250"),
    (r"\bnifty\s+small\s*cap\s+100\b|\bsmall\s*cap\s+100\b", "NIFTY SMALLCAP 100"),
    (r"\bnifty\s+small\s*cap\s+50\b|\bsmall\s*cap\s+50\b", "NIFTY SMALLCAP 50"),
    (r"\bnifty\s+mid\s*cap\s+150\b|\bmid\s*cap\s+150\b", "NIFTY MIDCAP 150"),
    (r"\bnifty\s+mid\s*cap\s+100\b|\bmid\s*cap\s+100\b", "NIFTY MIDCAP 100"),
    (r"\bnifty\s+next\s+50\b|\bnext\s+50\b", "NIFTY NEXT 50"),
    (r"\bnifty\s+bank\b|\bbank\s+nifty\b", "NIFTY BANK"),
    (r"\bsensex\b", "SENSEX"),
    (r"\bnifty\s+500\b", "NIFTY 500"),
    (r"\bnifty\s+200\b", "NIFTY 200"),
    (r"\bnifty\s+100\b", "NIFTY 100"),
    (r"\bnifty\s+50\b", "NIFTY 50"),
)

MARKET_INDICES: tuple[dict[str, str], ...] = (
    {"key": "nifty50", "ticker": "^NSEI", "label": "NIFTY 50"},
    {"key": "sensex", "ticker": "^BSESN", "label": "SENSEX"},
    {"key": "nifty200", "ticker": "^CNX200", "label": "NIFTY 200"},
    {"key": "midcap", "ticker": "^CRSMID", "label": "NIFTY MIDCAP 150"},
    {"key": "smallcap", "ticker": "NIFTYSMLCAP250.NS", "label": "NIFTY SMLCAP 250"},
    {"key": "usdinr", "ticker": "USDINR=X", "label": "USD/INR"},
)


def configure_yfinance_cache(yf_module=None) -> None:
    try:
        cache_dir = Path(tempfile.gettempdir()) / "mfanalysis-yfinance-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if yf_module is not None and hasattr(yf_module, "set_tz_cache_location"):
            yf_module.set_tz_cache_location(str(cache_dir))
        try:
            import yfinance.cache as yf_cache

            yf_cache.set_cache_location(str(cache_dir))
        except Exception:
            pass
    except Exception as exc:
        logger.info("Could not configure yfinance cache directory: %s", exc)


def normalize_benchmark_name(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip().upper())
    if cleaned in BENCHMARK_DEFINITIONS:
        return cleaned
    for name, definition in BENCHMARK_DEFINITIONS.items():
        aliases = (definition.name, *definition.aliases)
        if cleaned in {re.sub(r"\s+", " ", alias.upper()) for alias in aliases}:
            return name
    return cleaned if cleaned in BENCHMARK_DEFINITIONS else None


def benchmark_for(category: str | None, scheme_name: str = "") -> str | None:
    text = f"{category or ''} {scheme_name or ''}".lower()
    for pattern, benchmark in EXPLICIT_INDEX_RULES:
        if re.search(pattern, text):
            return benchmark
    if category and category in CATEGORY_BENCHMARK_MAP:
        return CATEGORY_BENCHMARK_MAP[category]
    for marker, benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in text:
            return benchmark
    return None


def infer_category(name: str) -> str:
    lower = (name or "").lower()
    for marker, _benchmark in CATEGORY_BENCHMARK_RULES:
        if marker in lower:
            return marker.title()
    return ""


def iter_benchmark_candidates(name: str | None) -> Iterable[BenchmarkCandidate]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return []
    return list(_iter_benchmark_candidates(canonical, canonical, set(), False))


def _iter_benchmark_candidates(
    requested_name: str,
    current_name: str,
    seen: set[str],
    is_fallback: bool,
) -> Iterable[BenchmarkCandidate]:
    if current_name in seen:
        return
    seen.add(current_name)
    definition = BENCHMARK_DEFINITIONS.get(current_name)
    if not definition:
        return
    for ticker in definition.yahoo_tickers:
        note = ""
        if is_fallback:
            note = f"{requested_name} has no reliable Yahoo history; using {current_name} as fallback."
        yield BenchmarkCandidate(requested_name, current_name, ticker, definition.field, False, is_fallback, note)
    for ticker, note in definition.proxy_tickers:
        yield BenchmarkCandidate(requested_name, current_name, ticker, definition.field, True, is_fallback, note)
    if definition.fallback:
        fallback = normalize_benchmark_name(definition.fallback)
        if fallback:
            yield from _iter_benchmark_candidates(requested_name, fallback, seen, True)


def primary_yahoo_ticker(name: str | None) -> str:
    for candidate in iter_benchmark_candidates(name):
        return candidate.yahoo_ticker
    return ""


def benchmark_ticker_map() -> dict[str, tuple[str, str]]:
    return {
        name: (ticker, definition.field)
        for name, definition in BENCHMARK_DEFINITIONS.items()
        if (ticker := primary_yahoo_ticker(name))
    }


def resolve_benchmark(name: str | None) -> BenchmarkResolution | None:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return None
    candidates = list(iter_benchmark_candidates(canonical))
    if candidates:
        first = candidates[0]
        tickers = tuple(candidate.yahoo_ticker for candidate in candidates if candidate.benchmark_name == first.benchmark_name)
        fallback_used = first.is_fallback or first.benchmark_name != canonical
        note = first.note
        if fallback_used and not note:
            note = f"{canonical} has no reliable Yahoo history; using {first.benchmark_name} as fallback."
        return BenchmarkResolution(canonical, first.benchmark_name, tickers, fallback_used, note)

    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if definition and definition.fallback:
        fallback = normalize_benchmark_name(definition.fallback)
        fallback_candidates = list(iter_benchmark_candidates(fallback))
        if fallback and fallback_candidates:
            tickers = tuple(candidate.yahoo_ticker for candidate in fallback_candidates)
            return BenchmarkResolution(
                canonical,
                fallback,
                tickers,
                True,
                f"{canonical} has no reliable Yahoo history; using {fallback} as fallback.",
            )
    return BenchmarkResolution(canonical, canonical, ())


def yahoo_ticker_map() -> dict[str, tuple[str, str]]:
    return benchmark_ticker_map()


def market_strip_indices() -> list[dict[str, str]]:
    items = []
    for item in MARKET_INDICES:
        benchmark = "USD/INR" if item["ticker"] == "USDINR=X" else item["label"]
        items.append({
            "key": item["key"],
            "benchmark": benchmark,
            "label": item["label"],
            "ticker": item["ticker"],
        })
    return items


BENCHMARK_TICKERS = benchmark_ticker_map()


def fetch_yahoo_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    period: str = "max",
    min_rows: int = 2,
    deadline: "float | None" = None,
) -> "tuple[pd.Series, BenchmarkCandidate | None]":
    import time
    if deadline is None:
        deadline = time.monotonic() + 10  # 10-second hard cap on the whole benchmark fetch

    for candidate in iter_benchmark_candidates(name):
        series = fetch_yahoo_history_for_candidate(candidate, start_date=start_date, end_date=end_date, period=period, min_rows=min_rows)
        if not series.empty:
            series.attrs["benchmark_candidate"] = candidate
            return series, candidate

    import time as _time
    if _time.monotonic() >= deadline:
        logger.info("Benchmark fetch deadline exceeded for %s (skipping niftyindices+nse)", name)
        return pd.Series(dtype=float), None

    series, candidate = fetch_niftyindices_history_for_benchmark(name, start_date=start_date, end_date=end_date, min_rows=min_rows, deadline=deadline)
    if not series.empty:
        series.attrs["benchmark_candidate"] = candidate
        return series, candidate

    if _time.monotonic() >= deadline:
        logger.info("Benchmark fetch deadline exceeded for %s (skipping nse)", name)
        return pd.Series(dtype=float), None

    series, candidate = fetch_nse_history_for_benchmark(name, start_date=start_date, end_date=end_date, min_rows=min_rows)
    if not series.empty:
        series.attrs["benchmark_candidate"] = candidate
        return series, candidate
    return pd.Series(dtype=float), None



def fetch_yahoo_history_for_candidate(
    candidate: BenchmarkCandidate,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    period: str = "max",
    min_rows: int = 2,
) -> pd.Series:
    cache_key = _cache_key("benchmark:yahoo:v6", candidate.yahoo_ticker, start_date or period, end_date or "")
    try:
        from django.core.cache import cache

        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        cache = None

    try:
        import yfinance as yf

        configure_yfinance_cache(yf)
        ticker = yf.Ticker(candidate.yahoo_ticker)
        kwargs = {"auto_adjust": False}
        if start_date:
            kwargs["start"] = start_date.isoformat() if hasattr(start_date, "isoformat") else str(start_date)
            if end_date:
                parsed_end = pd.Timestamp(end_date).date()
                kwargs["end"] = (parsed_end + timedelta(days=1)).isoformat()
        else:
            kwargs["period"] = period
        try:
            hist = ticker.history(**kwargs, raise_errors=False)
        except TypeError:
            hist = ticker.history(**kwargs)
        field = "Adj Close" if candidate.is_proxy and hist is not None and "Adj Close" in hist else candidate.field
        series = _extract_close_series(hist, field)
        if len(series) < min_rows:
            continue_msg = "only %s rows" % len(series)
            logger.info("Benchmark candidate %s/%s skipped: %s", candidate.benchmark_name, candidate.yahoo_ticker, continue_msg)
            return pd.Series(dtype=float)
        series.attrs["benchmark_candidate"] = candidate
        try:
            cache.set(cache_key, series, BENCHMARK_TTL)
        except Exception:
            pass
        return series
    except Exception as exc:
        logger.info("Benchmark candidate fetch failed for %s/%s: %s", candidate.benchmark_name, candidate.yahoo_ticker, exc)
        return pd.Series(dtype=float)


def fetch_nse_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    min_rows: int = 2,
) -> tuple[pd.Series, BenchmarkCandidate | None]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return pd.Series(dtype=float), None
    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if not definition:
        return pd.Series(dtype=float), None
    nse_name = definition.nse_name or definition.name
    candidate = BenchmarkCandidate(canonical, canonical, f"NSE:{nse_name}", definition.field, source="nse")
    cache_key = _cache_key("benchmark:nse:v3", nse_name, start_date or "max", end_date or "")
    try:
        from django.core.cache import cache

        cached = cache.get(cache_key)
        if cached is not None:
            return cached, candidate
    except Exception:
        cache = None

    try:
        start = pd.Timestamp(start_date).date() if start_date else date(2000, 1, 1)
    except Exception:
        start = date(2000, 1, 1)
    try:
        end = pd.Timestamp(end_date).date() if end_date else date.today()
    except Exception:
        end = date.today()
    rows = []
    try:
        session = _make_nse_session()
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=365), end)
            url = (
                "https://www.nseindia.com/api/historical/indicesHistory"
                f"?indexType={requests.utils.quote(nse_name)}"
                f"&from={chunk_start.strftime('%d-%m-%Y')}"
                f"&to={chunk_end.strftime('%d-%m-%Y')}"
            )
            response = session.get(url, timeout=20)
            response.raise_for_status()
            raw = response.json().get("data", {}).get("indexCloseOnlineRecords", [])
            for row in raw:
                try:
                    rows.append((
                        datetime.strptime(row["EOD_TIMESTAMP"], "%d-%b-%Y").date(),
                        float(row["EOD_CLOSE_INDEX_VAL"]),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            chunk_start = chunk_end + timedelta(days=1)
    except Exception as exc:
        logger.info("NSE benchmark fetch failed for %s: %s", nse_name, exc)
        return pd.Series(dtype=float), candidate

    if len(rows) < min_rows:
        logger.info("NSE benchmark %s skipped: only %s rows", nse_name, len(rows))
        return pd.Series(dtype=float), candidate
    series = pd.Series({pd.Timestamp(row_date): close for row_date, close in rows}).sort_index()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    try:
        cache.set(cache_key, series, BENCHMARK_TTL)
    except Exception:
        pass
    return series, candidate


def fetch_niftyindices_history_for_benchmark(
    name: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    min_rows: int = 2,
    deadline: "float | None" = None,
) -> tuple[pd.Series, BenchmarkCandidate | None]:
    canonical = normalize_benchmark_name(name)
    if not canonical:
        return pd.Series(dtype=float), None
    definition = BENCHMARK_DEFINITIONS.get(canonical)
    if not definition:
        return pd.Series(dtype=float), None

    requested_index = definition.nse_name or definition.name
    candidate = BenchmarkCandidate(canonical, canonical, f"NIFTYINDICES:{requested_index}", definition.field, source="niftyindices")
    cache_key = _cache_key("benchmark:niftyindices:v1", requested_index, start_date or "max", end_date or "")
    try:
        from django.core.cache import cache

        cached = cache.get(cache_key)
        if cached is not None:
            return cached, candidate
    except Exception:
        cache = None

    try:
        start = pd.Timestamp(start_date).date() if start_date else date(2000, 1, 1)
    except Exception:
        start = date(2000, 1, 1)
    try:
        end = pd.Timestamp(end_date).date() if end_date else date.today()
    except Exception:
        end = date.today()
    if start > end:
        return pd.Series(dtype=float), candidate

    rows = []
    try:
        import time as _time
        session = _make_niftyindices_session()
        index_name = _niftyindices_trading_name(session, requested_index)
        chunk_start = start
        while chunk_start <= end:
            if deadline is not None and _time.monotonic() >= deadline:
                logger.info("Nifty Indices deadline exceeded for %s, aborting chunk loop", requested_index)
                break
            chunk_end = min(chunk_start + timedelta(days=365), end)
            rows.extend(_fetch_niftyindices_rows(session, index_name, requested_index, chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(days=1)
    except Exception as exc:
        logger.info("Nifty Indices benchmark fetch failed for %s: %s", requested_index, exc)
        return pd.Series(dtype=float), candidate

    if len(rows) < min_rows:
        logger.info("Nifty Indices benchmark %s skipped: only %s rows", requested_index, len(rows))
        return pd.Series(dtype=float), candidate
    latest_row_date = max(row_date for row_date, _close in rows)
    if (end - latest_row_date).days > 45:
        logger.info("Nifty Indices benchmark %s skipped: latest row is %s", requested_index, latest_row_date)
        return pd.Series(dtype=float), candidate
    series = pd.Series({pd.Timestamp(row_date): close for row_date, close in rows}).sort_index()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")]
    try:
        cache.set(cache_key, series, BENCHMARK_TTL)
    except Exception:
        pass
    return series, candidate


def _fetch_niftyindices_rows(
    session: requests.Session,
    index_name: str,
    requested_index: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    try:
        return _fetch_niftyindices_rows_once(session, index_name, requested_index, start, end)
    except Exception as exc:
        span = (end - start).days
        if span <= 92:
            logger.info(
                "Nifty Indices chunk skipped for %s %s..%s: %s",
                requested_index,
                start,
                end,
                exc,
            )
            return []
        mid = start + timedelta(days=span // 2)
        return (
            _fetch_niftyindices_rows(session, index_name, requested_index, start, mid)
            + _fetch_niftyindices_rows(session, index_name, requested_index, mid + timedelta(days=1), end)
        )


def _fetch_niftyindices_rows_once(
    session: requests.Session,
    index_name: str,
    requested_index: str,
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    payload = {
        "cinfo": (
            "{'name':'" + index_name.upper().strip() +
            "','startDate':'" + start.strftime("%d-%b-%Y") +
            "','endDate':'" + end.strftime("%d-%b-%Y") +
            "','indexName':'" + requested_index + "'}"
        )
    }
    last_exc: Exception | None = None
    for timeout in (5, 8):
        try:
            response = session.post(
                f"{NIFTYINDICES_BASE}/Backpage.aspx/getHistoricaldatatabletoString",
                data=json.dumps(payload),
                timeout=timeout,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": NIFTYINDICES_BASE,
                    "Referer": f"{NIFTYINDICES_BASE}/reports/historical-data",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            response.raise_for_status()
            raw = response.json().get("d") or []
            if isinstance(raw, str):
                raw = json.loads(raw)
            rows = []
            for row in raw:
                try:
                    rows.append((
                        datetime.strptime(row["HistoricalDate"], "%d %b %Y").date(),
                        float(str(row["CLOSE"]).replace(",", "")),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            return rows
        except Exception as exc:
            last_exc = exc
    raise last_exc or RuntimeError("Nifty Indices returned no response")


def _make_niftyindices_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        session.get(f"{NIFTYINDICES_BASE}/reports/historical-data", timeout=5)
    except Exception as exc:
        logger.info("Nifty Indices warmup warning: %s", exc)
    return session


def _niftyindices_trading_name(session: requests.Session, index_name: str) -> str:
    try:
        response = session.get(f"{NIFTYINDICES_ASSET_BASE}/assets/json/IndexMapping.json", timeout=15)
        response.raise_for_status()
        data = json.loads(response.content.decode("utf-8-sig"))
        target = _compact_index_name(index_name)
        for row in data:
            long_name = _compact_index_name(row.get("Index_long_name"))
            trading_name = _compact_index_name(row.get("Trading_Index_Name"))
            if target in {long_name, trading_name}:
                return str(row.get("Trading_Index_Name") or index_name)
    except Exception as exc:
        logger.info("Nifty Indices mapping fetch failed for %s: %s", index_name, exc)
    return index_name


def _compact_index_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def _make_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com/", timeout=10)
        session.get("https://www.nseindia.com/market-data/live-equity-market", timeout=10)
    except Exception as exc:
        logger.info("NSE warmup warning: %s", exc)
    return session


def _cache_key(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}:{md5(raw.encode('utf-8')).hexdigest()}"


def _extract_close_series(hist, field: str) -> pd.Series:
    if hist is None or getattr(hist, "empty", True):
        return pd.Series(dtype=float)
    close_field = field if field in hist else "Close"
    if close_field not in hist:
        return pd.Series(dtype=float)
    series = pd.to_numeric(hist[close_field], errors="coerce").dropna()
    if series.empty:
        return pd.Series(dtype=float)
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    series = series[~series.index.duplicated(keep="last")]
    return series.sort_index()
