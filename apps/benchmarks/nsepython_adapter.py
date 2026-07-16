"""
nsepython_adapter.py — Fetch NSE index historical data via nsepython/iislliveblob.

This provides a robust fallback for indices not available via:
  - NSE Direct API (which 503s for newer indices)
  - Yahoo Finance (many NSE factor indices aren't listed there)
  - NiftyIndices Backpage endpoint (requires interactive session cookies)

Strategy:
  1. Use the LiveIndicesWatch.json to build a name-to-short-name map
  2. For historical data, try the NSE allIndices + history endpoint via
     nsepython's working session pattern
  3. Fall back to the iislliveblob CDN for what's available
"""
from __future__ import annotations

import logging
import json
import time
from datetime import date, datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger("mfanalysis")

_LIVE_WATCH_URL = "https://iislliveblob.niftyindices.com/jsonfiles/LiveIndicesWatch.json"
_NSE_HISTORY_URL = "https://www.nseindia.com/api/historical/indicesHistory"
_NSE_BASE = "https://www.nseindia.com"

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# Cache of the live name map
_name_map_cache: dict[str, str] | None = None


def _make_nse_session() -> requests.Session:
    """Create a session with NSE cookies (re-usable for multiple calls)."""
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get(_NSE_BASE, timeout=10)
        time.sleep(0.3)
        s.get(f"{_NSE_BASE}/market-data/live-equity-market", timeout=10)
        time.sleep(0.3)
    except Exception as exc:
        logger.debug("NSE session warmup: %s", exc)
    return s


def build_live_index_name_map() -> dict[str, str]:
    """
    Fetch LiveIndicesWatch.json and build a dict mapping:
      - canonical long name (uppercase) -> short NSE name
      - short NSE name (uppercase) -> short NSE name
      - no-spaces variant -> short NSE name

    This lets us translate 'NIFTY500 LOW VOLATILITY 50' -> 'NIFTY500 LOWVOL50'.
    Also builds cross-reference: 'NIFTY500 MOMENTUM 50' -> 'NIFTY500MOMENTM50'
    via the no-space/no-digit variant matching.
    """
    global _name_map_cache
    if _name_map_cache is not None:
        return _name_map_cache

    try:
        resp = requests.get(_LIVE_WATCH_URL, timeout=10, headers={
            "User-Agent": _NSE_HEADERS["User-Agent"]
        })
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
    except Exception as exc:
        logger.warning("nsepython_adapter: Could not fetch LiveIndicesWatch: %s", exc)
        return {}

    import re
    name_map: dict[str, str] = {}
    all_names: list[str] = []

    for item in items:
        name = item.get("indexName", "").strip()
        if not name:
            continue
        all_names.append(name)
        upper = name.upper()
        name_map[upper] = name
        name_map[upper.replace(" ", "")] = name
        # Also strip digits for matching (e.g. 'NIFTY500 LOWVOL' matches 'NIFTY500 LOWVOL50')
        no_digits = re.sub(r'\d+', '', upper).strip()
        if no_digits and no_digits not in name_map:
            name_map[no_digits] = name

    # Cross-reference: build abbreviated tokens for long names
    # e.g. 'NIFTY500 MOMENTUM 50' should map to 'NIFTY500MOMENTM50'
    # Strategy: for each long name, check if dropping vowels or abbreviating matches a short name
    # Simple approach: for each name, also map the first-8-chars-of-each-word variant
    for name in all_names:
        upper = name.upper()
        words = upper.split()
        # Build abbreviated: first token + first 6 chars of each subsequent word
        if len(words) > 1:
            abbrev = words[0] + ''.join(w[:6] for w in words[1:])
            if abbrev not in name_map:
                name_map[abbrev] = name
            # Also try MOMENTM-style (first 6 chars)
            abbrev2 = words[0] + ''.join(w[:7] for w in words[1:])
            if abbrev2 not in name_map:
                name_map[abbrev2] = name

    logger.info("nsepython_adapter: Built live name map with %d entries", len(name_map))
    _name_map_cache = name_map
    return name_map


def resolve_nse_index_name(index_name: str) -> Optional[str]:
    """
    Resolve a user-facing long index name to the short NSE API name.
    e.g. 'NIFTY500 LOW VOLATILITY 50' -> 'NIFTY500 LOWVOL50' 
    or   'NIFTY500 MOMENTUM 50' -> 'NIFTY500MOMENTM50'
    """
    name_map = build_live_index_name_map()
    upper = index_name.upper().strip()

    # Exact match
    if upper in name_map:
        return name_map[upper]

    # Match without spaces
    nospace = upper.replace(" ", "")
    if nospace in name_map:
        return name_map[nospace]

    # Return the original and let NSE figure it out
    return index_name


def fetch_nse_index_history(
    index_name: str,
    start: date,
    end: date,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """
    Fetch daily closing values for an NSE index from nseindia.com.

    Parameters
    ----------
    index_name : str
        Long or short NSE index name.
    start, end : date
        Date range (inclusive).
    session : requests.Session, optional
        Reuse an existing session with NSE cookies.

    Returns
    -------
    list of dicts: [{'date': date, 'close': float}, ...]
    """
    resolved = resolve_nse_index_name(index_name)
    if session is None:
        session = _make_nse_session()

    rows: list[dict] = []
    chunk_start = start

    while chunk_start <= end:
        chunk_end = min(date(chunk_start.year + 1, 1, 1) - timedelta(days=1), end)
        from_str = chunk_start.strftime("%d-%m-%Y")
        to_str = chunk_end.strftime("%d-%m-%Y")

        url = (
            f"{_NSE_HISTORY_URL}"
            f"?indexType={requests.utils.quote(resolved)}"
            f"&from={from_str}&to={to_str}"
        )
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 503:
                logger.debug(
                    "nsepython_adapter: NSE 503 for '%s' %s–%s",
                    resolved, chunk_start, chunk_end,
                )
                break  # Give up NSE for this index

            resp.raise_for_status()
            data = resp.json()
            records = data.get("data", {}).get("indexCloseOnlineRecords", [])
            for rec in records:
                try:
                    dt = datetime.strptime(rec["EOD_TIMESTAMP"], "%d-%b-%Y").date()
                    close = float(str(rec["EOD_CLOSE_INDEX_VAL"]).replace(",", ""))
                    rows.append({"date": dt, "close": close})
                except (KeyError, ValueError, TypeError):
                    continue

            chunk_start = chunk_end + timedelta(days=1)
            time.sleep(0.5)  # Be polite

        except Exception as exc:
            logger.debug(
                "nsepython_adapter: Error fetching '%s' %s–%s: %s",
                resolved, chunk_start, chunk_end, exc,
            )
            break

    return rows


def fetch_all_nse_index_names() -> list[str]:
    """
    Return all index names currently available via NSE.
    Useful for debugging which names to use.
    """
    name_map = build_live_index_name_map()
    return sorted({v for v in name_map.values()})
