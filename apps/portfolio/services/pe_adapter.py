"""
apps/portfolio/services/pe_adapter.py
======================================
PE / PB / DivYield data fetcher for the backtester v2 trigger system.

Primary source: NSE India (niftyindices.com) POST API
  Endpoint: https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString
  Payload:  {"name": "NIFTY 50", "startDate": "01-Jan-2015", "endDate": "31-Dec-2024"}
  Response: JSON with an array of {TIMESTAMP, pe, pb, divYield}

Key fixes vs old implementation (nsepython wrapper):
  1. Direct HTTP session with proper headers + cookie pre-fetch (avoids JSONDecodeError).
  2. Date format: "%d-%b-%Y" (e.g. "01-Jan-2015"), not "%d-%m-%Y".
  3. Retry with exponential back-off (up to 3 attempts).
  4. SQLite-backed persistent cache (survives server restarts within a single day).
  5. Separate get_pb_series() and get_div_yield_series() functions.

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

import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger("mfanalysis")

# ── Constants ─────────────────────────────────────────────────────────────────
_NIFTY_INDICES_URL = (
    "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
)
_HOME_URL = "https://www.niftyindices.com"
_REQUEST_TIMEOUT = 30  # seconds
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds (exponential back-off: 2, 4, 8)

# SQLite cache stored next to this file (survives Django restarts)
_CACHE_DB_PATH = Path(__file__).parent / ".pe_cache.db"

# In-process memory cache: (index_name, column, from_str, to_str) → pd.Series
_MEM_CACHE: dict = {}


class PEDataUnavailableError(ValueError):
    """Raised when PE/PB/DivYield data cannot be fetched."""
    pass


# ── Public API ────────────────────────────────────────────────────────────────

def get_pe_series(
    index_name: str,
    from_date: date,
    to_date: date,
) -> pd.Series:
    """
    Fetch historical PE ratio series for NIFTY 50 (only index guaranteed to work).
    Returns pd.Series indexed by pd.Timestamp.
    """
    return _get_metric_series(index_name, "pe", from_date, to_date)


def get_pb_series(
    index_name: str,
    from_date: date,
    to_date: date,
) -> pd.Series:
    """Fetch historical Price-to-Book ratio series for the given index."""
    return _get_metric_series(index_name, "pb", from_date, to_date)


def get_div_yield_series(
    index_name: str,
    from_date: date,
    to_date: date,
) -> pd.Series:
    """Fetch historical Dividend Yield series for the given index."""
    return _get_metric_series(index_name, "divYield", from_date, to_date)


def get_pe_on_date(
    index_name: str,
    on_date: date,
    from_date: date,
    to_date: date,
) -> Optional[float]:
    """Get PE ratio for a single date. Returns None if unavailable."""
    try:
        series = get_pe_series(index_name, from_date, to_date)
        val = series.asof(pd.Timestamp(on_date))
        return float(val) if val is not None and not pd.isna(val) else None
    except PEDataUnavailableError:
        return None


def clear_cache() -> None:
    """Clear both in-process memory cache and SQLite cache."""
    _MEM_CACHE.clear()
    try:
        conn = _get_db()
        conn.execute("DELETE FROM pe_cache")
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Core fetch ────────────────────────────────────────────────────────────────

def _get_metric_series(
    index_name: str,
    column: str,  # "pe", "pb", or "divYield"
    from_date: date,
    to_date: date,
) -> pd.Series:
    """
    Core logic: check mem cache → SQLite cache → fetch from API.
    """
    # Normalise dates — API works best in full-month chunks
    from_str = from_date.strftime("%d-%b-%Y")   # e.g. "01-Jan-2015"
    to_str = to_date.strftime("%d-%b-%Y")
    mem_key = (index_name, column, from_str, to_str)

    # 1. In-process memory cache
    if mem_key in _MEM_CACHE:
        logger.debug("[pe_adapter] Mem-cache hit: %s %s %s→%s", index_name, column, from_str, to_str)
        return _MEM_CACHE[mem_key]

    # 2. SQLite cache (valid for today)
    cached_df = _sqlite_get(index_name, column, from_str, to_str)
    if cached_df is not None:
        logger.debug("[pe_adapter] SQLite cache hit: %s %s", index_name, column)
        s = _df_to_series(cached_df, column)
        _MEM_CACHE[mem_key] = s
        return s

    # 3. Fetch from niftyindices.com API
    logger.info("[pe_adapter] Fetching %s %s %s→%s from niftyindices.com", index_name, column, from_str, to_str)
    raw_df = _fetch_from_api(index_name, from_str, to_str)

    # Persist to SQLite (save all columns)
    _sqlite_put(index_name, from_str, to_str, raw_df)

    s = _df_to_series(raw_df, column)
    _MEM_CACHE[mem_key] = s
    return s


def _fetch_from_api(index_name: str, from_str: str, to_str: str) -> pd.DataFrame:
    """
    Call niftyindices.com POST API with session cookie + proper headers.
    Returns a DataFrame with columns: TIMESTAMP, pe, pb, divYield.
    Raises PEDataUnavailableError on any failure.
    """
    session = requests.Session()

    # Step 1: Hit homepage to get session cookies (required to avoid 403/JSON errors)
    try:
        session.get(
            _HOME_URL,
            headers=_base_headers(),
            timeout=_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except Exception as e:
        logger.warning("[pe_adapter] Cookie pre-fetch failed: %s — continuing anyway", e)

    # Step 2: POST to the data API with retries
    payload = {
        "name": index_name,
        "startDate": from_str,
        "endDate": to_str,
    }
    headers = {
        **_base_headers(),
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": _HOME_URL + "/",
        "Origin": _HOME_URL,
    }

    last_exc: Exception = RuntimeError("Unknown error")
    for attempt in range(_MAX_RETRIES):
        try:
            resp = session.post(
                _NIFTY_INDICES_URL,
                json=payload,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()

            # Response is JSON with .d field containing a JSON string
            outer = resp.json()
            inner_json = outer.get("d", outer)
            if isinstance(inner_json, str):
                records = json.loads(inner_json)
            elif isinstance(inner_json, list):
                records = inner_json
            else:
                raise PEDataUnavailableError(
                    f"Unexpected API response format for '{index_name}': {type(inner_json)}"
                )

            if not records:
                raise PEDataUnavailableError(
                    f"No PE/PB data returned for '{index_name}' "
                    f"({from_str} → {to_str}). The index may not have historical data."
                )

            df = pd.DataFrame(records)
            logger.info("[pe_adapter] Fetched %d rows for '%s'", len(df), index_name)
            return df

        except PEDataUnavailableError:
            raise
        except requests.exceptions.HTTPError as e:
            last_exc = e
            logger.warning("[pe_adapter] HTTP %s on attempt %d for '%s'", e.response.status_code, attempt + 1, index_name)
        except json.JSONDecodeError as e:
            last_exc = PEDataUnavailableError(
                f"niftyindices.com returned non-JSON response for '{index_name}'. "
                "The site may be blocking server-side requests. "
                f"(attempt {attempt + 1}) Error: {e}"
            )
            logger.warning("[pe_adapter] JSONDecodeError attempt %d: %s", attempt + 1, e)
        except Exception as e:
            last_exc = e
            logger.warning("[pe_adapter] Fetch error attempt %d: %s", attempt + 1, e)

        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.info("[pe_adapter] Retrying in %.1fs…", delay)
            time.sleep(delay)

    raise PEDataUnavailableError(
        f"Failed to fetch PE data for '{index_name}' after {_MAX_RETRIES} attempts. "
        f"Last error: {last_exc}"
    )


def _df_to_series(df: pd.DataFrame, column: str) -> pd.Series:
    """
    Convert the raw API DataFrame to a clean pd.Series indexed by pd.Timestamp.
    Handles multiple date column and value column naming conventions.
    """
    # Find date column
    date_col = None
    for candidate in ("TIMESTAMP", "HistoricalDate", "timestamp", "date", "Date"):
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        raise PEDataUnavailableError(
            f"Could not find date column. Available columns: {list(df.columns)}"
        )

    # Find value column — allow case-insensitive matching
    col_lower = column.lower()
    val_col = None
    for c in df.columns:
        if c.lower() == col_lower:
            val_col = c
            break
    # Fallback: 'divYield' → look for 'divy' substring
    if val_col is None and col_lower in ("divyield",):
        for c in df.columns:
            if "div" in c.lower():
                val_col = c
                break

    if val_col is None:
        raise PEDataUnavailableError(
            f"Could not find '{column}' column. Available: {list(df.columns)}"
        )

    df2 = df[[date_col, val_col]].copy()

    # Parse date — niftyindices uses "01-Jan-2015" format
    df2[date_col] = pd.to_datetime(df2[date_col], format="%d-%b-%Y", errors="coerce")
    # Fallback: try without format spec
    mask = df2[date_col].isna()
    if mask.any():
        df2.loc[mask, date_col] = pd.to_datetime(df2.loc[mask, date_col], errors="coerce")

    df2 = df2.dropna(subset=[date_col])
    df2[val_col] = pd.to_numeric(df2[val_col], errors="coerce")
    df2 = df2.dropna(subset=[val_col])

    if df2.empty:
        raise PEDataUnavailableError(
            f"Series is empty after parsing for column '{column}'."
        )

    s = df2.set_index(date_col)[val_col].sort_index()
    s = s[~s.index.duplicated(keep="last")]

    # Reindex to daily and forward-fill (weekends/holidays)
    full_idx = pd.date_range(start=s.index.min(), end=s.index.max(), freq="D")
    s = s.reindex(full_idx).ffill()

    return s


def _base_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


# ── SQLite cache ──────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    _CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pe_cache (
            index_name TEXT,
            from_str   TEXT,
            to_str     TEXT,
            cached_date TEXT,
            payload    TEXT,
            PRIMARY KEY (index_name, from_str, to_str)
        )
    """)
    conn.commit()
    return conn


def _sqlite_get(
    index_name: str, column: str, from_str: str, to_str: str
) -> Optional[pd.DataFrame]:
    """Return cached DataFrame if it was fetched today, else None."""
    try:
        conn = _get_db()
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT payload FROM pe_cache WHERE index_name=? AND from_str=? AND to_str=? AND cached_date=?",
            (index_name, from_str, to_str, today),
        ).fetchone()
        conn.close()
        if row:
            records = json.loads(row[0])
            return pd.DataFrame(records)
    except Exception as e:
        logger.debug("[pe_adapter] SQLite get error: %s", e)
    return None


def _sqlite_put(
    index_name: str, from_str: str, to_str: str, df: pd.DataFrame
) -> None:
    """Persist the raw DataFrame to SQLite for today."""
    try:
        conn = _get_db()
        today = date.today().isoformat()
        payload = df.to_json(orient="records")
        conn.execute(
            """INSERT OR REPLACE INTO pe_cache
               (index_name, from_str, to_str, cached_date, payload)
               VALUES (?, ?, ?, ?, ?)""",
            (index_name, from_str, to_str, today, payload),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("[pe_adapter] SQLite put error: %s", e)
