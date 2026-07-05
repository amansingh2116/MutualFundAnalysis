"""
apps/portfolio/services/pe_adapter.py
======================================
PE Ratio data fetcher for the backtester v2 trigger system.

Primary source: nsepython.index_pe_pb_div → niftyindices.com POST API
  - Returns a historical DataFrame with columns: index_name, TIMESTAMP, pe, pb, divYield
  - TIMESTAMP format: 'DD-MM-YYYY'
  - Covers all NSE indices tracked by niftyindices.com

Session cache: in-process dict so repeated re-runs within the same
Django request cycle (or same Python process) don't re-hit the API.
Cache is keyed by (index_name, from_date_str, to_date_str).

Usage:
    from apps.portfolio.services.pe_adapter import get_pe_series, PEDataUnavailableError
    try:
        series = get_pe_series("NIFTY 50", date(2015, 1, 1), date(2024, 12, 31))
        pe_on_date = series.asof(pd.Timestamp("2020-03-23"))
    except PEDataUnavailableError as e:
        # Surface as inline UI warning
        raise
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger("mfanalysis")

# ── In-process session cache ──────────────────────────────────────────────────
# Key: (index_name, from_str, to_str) → pd.Series
_PE_CACHE: dict = {}


class PEDataUnavailableError(ValueError):
    """Raised when PE data cannot be fetched for the requested index/date range."""
    pass


# PE-tracked NSE indices (subset most likely to have data on niftyindices.com)
# The full 68-index list is available in the UI dropdown; the ones below are
# confirmed to have PE data. Others will surface a PEDataUnavailableError which
# is caught and shown as an inline warning.
PE_SUPPORTED_INDICES = [
    "NIFTY 50",
    "NIFTY 100",
    "NIFTY 200",
    "NIFTY 500",
    "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 50",
    "NIFTY SMALLCAP 100",
    "NIFTY SMALLCAP 250",
    "NIFTY NEXT 50",
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY PHARMA",
    "NIFTY AUTO",
    "NIFTY FMCG",
    "NIFTY REALTY",
    "NIFTY METAL",
    "NIFTY ENERGY",
    "NIFTY INFRA",
    "NIFTY PSE",
    "NIFTY PSU BANK",
    "NIFTY FINANCIAL SERVICES",
]


def get_pe_series(
    index_name: str,
    from_date: date,
    to_date: date,
) -> pd.Series:
    """
    Fetch historical PE ratio series for a NSE index.

    Args:
        index_name: NSE index name as used on niftyindices.com
                    e.g. "NIFTY 50", "NIFTY MIDCAP 150"
        from_date:  Start date (inclusive)
        to_date:    End date (inclusive)

    Returns:
        pd.Series indexed by pd.Timestamp, values = PE ratio (float).
        The series uses forward-fill so every date in the window has a value.

    Raises:
        PEDataUnavailableError: If the index has no PE data or fetch fails.
    """
    from_str = from_date.strftime("%d-%m-%Y")
    to_str = to_date.strftime("%d-%m-%Y")
    cache_key = (index_name, from_str, to_str)

    if cache_key in _PE_CACHE:
        logger.debug(f"[pe_adapter] Cache hit for {index_name} {from_str}→{to_str}")
        return _PE_CACHE[cache_key]

    logger.info(f"[pe_adapter] Fetching PE for '{index_name}' {from_str}→{to_str}")

    try:
        from nsepython import index_pe_pb_div  # type: ignore
        df = index_pe_pb_div(index_name, from_str, to_str)
    except ImportError:
        raise PEDataUnavailableError(
            "nsepython is not installed. Cannot fetch PE data."
        )
    except Exception as e:
        raise PEDataUnavailableError(
            f"Failed to fetch PE data for '{index_name}': {e}"
        )

    if df is None or (hasattr(df, "empty") and df.empty):
        raise PEDataUnavailableError(
            f"No PE data returned for '{index_name}'. "
            "This index may not have PE data on niftyindices.com."
        )

    # Normalise the DataFrame
    # nsepython returns columns like: index_name, TIMESTAMP, pe, pb, divYield
    # Detect PE column (may vary by version)
    pe_col = _find_pe_column(df)
    if pe_col is None:
        raise PEDataUnavailableError(
            f"Could not identify PE column in response for '{index_name}'. "
            f"Available columns: {list(df.columns)}"
        )

    date_col = _find_date_column(df)
    if date_col is None:
        raise PEDataUnavailableError(
            f"Could not identify date column in response for '{index_name}'."
        )

    try:
        df = df[[date_col, pe_col]].copy()
        df[date_col] = pd.to_datetime(df[date_col], format="%d-%m-%Y", errors="coerce")
        df = df.dropna(subset=[date_col])
        df[pe_col] = pd.to_numeric(df[pe_col], errors="coerce")
        df = df.dropna(subset=[pe_col])
        s = df.set_index(date_col)[pe_col].sort_index()
        s = s[~s.index.duplicated(keep="last")]
    except Exception as e:
        raise PEDataUnavailableError(
            f"Failed to parse PE data for '{index_name}': {e}"
        )

    if s.empty:
        raise PEDataUnavailableError(
            f"PE series is empty after parsing for '{index_name}'."
        )

    # Reindex to daily frequency and forward-fill gaps (weekends/holidays)
    full_idx = pd.date_range(start=s.index.min(), end=s.index.max(), freq="D")
    s = s.reindex(full_idx).ffill()

    _PE_CACHE[cache_key] = s
    logger.info(f"[pe_adapter] Cached PE series for '{index_name}': {len(s)} days")
    return s


def get_pe_on_date(
    index_name: str,
    on_date: date,
    from_date: date,
    to_date: date,
) -> Optional[float]:
    """
    Get PE ratio for a single date. Returns None if unavailable.
    Fetches the full series (cached) and does a .asof() lookup.
    """
    try:
        series = get_pe_series(index_name, from_date, to_date)
        val = series.asof(pd.Timestamp(on_date))
        return float(val) if val is not None and not pd.isna(val) else None
    except PEDataUnavailableError:
        return None


def clear_cache() -> None:
    """Clear the in-process PE cache (useful for testing)."""
    _PE_CACHE.clear()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _find_pe_column(df: pd.DataFrame) -> Optional[str]:
    """Find the PE ratio column by checking common names."""
    candidates = ["pe", "PE", "P/E", "pe_ratio", "peRatio", "indexPE"]
    for c in candidates:
        if c in df.columns:
            return c
    # Fuzzy: any column with 'pe' in lowercase name
    for c in df.columns:
        if "pe" in c.lower() and "pb" not in c.lower():
            return c
    return None


def _find_date_column(df: pd.DataFrame) -> Optional[str]:
    """Find the date column by checking common names."""
    candidates = ["TIMESTAMP", "timestamp", "date", "Date", "DATE", "HistoricalDate"]
    for c in candidates:
        if c in df.columns:
            return c
    return None
