"""
Benchmark Adapter
==================
Primary source: NSE Direct API (no auth, no rate limit, covers all 139 NSE indices)
Fallback: yfinance (rate-limited; sleep 2s before each call)

⚠️ CONFIRMED IN NOTEBOOK — NSE API quirks:
  1. Requires session warmup: 2 GET requests before any API call
  2. Historical dates in response: 'EOD_TIMESTAMP' → 'DD-MMM-YYYY' format
  3. Historical close value: 'EOD_CLOSE_INDEX_VAL'
  4. Input date format: DD-MM-YYYY (different from response format)
  5. 'indexType' query param must be URL-encoded

BENCHMARK_TICKERS and CATEGORY_BENCHMARK_MAP are defined here
and imported by analytics/engine.py for benchmark selection.
"""
import datetime
import logging
import time
import urllib.parse
from typing import Optional

import requests

from apps.benchmarks.registry import (
    BENCHMARK_TICKERS as REGISTRY_BENCHMARK_TICKERS,
    CATEGORY_BENCHMARK_MAP as REGISTRY_CATEGORY_BENCHMARK_MAP,
    configure_yfinance_cache,
)

from .base import BaseAdapter, AdapterError

logger = logging.getLogger('adapters.benchmark')

NSE_BASE    = 'https://www.nseindia.com'
NSE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept':          'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer':         'https://www.nseindia.com/',
}

BENCHMARK_TICKERS = REGISTRY_BENCHMARK_TICKERS
CATEGORY_BENCHMARK_MAP = REGISTRY_CATEGORY_BENCHMARK_MAP


class BenchmarkAdapter(BaseAdapter):
    """
    Adapter for NSE Direct API (primary) and yfinance (fallback).
    
    NSE API session must be warmed up before each batch of requests.
    Use _make_nse_session() which performs the required warm-up GETs.
    """
    SOURCE_NAME      = 'nse_direct'
    RATE_LIMIT_DELAY = 1.0

    def _make_nse_session(self) -> requests.Session:
        """
        Create and warm up an NSE session.

        NSE requires cookies set by the homepage before accepting API requests.
        ⚠️ CONFIRMED IN NOTEBOOK: 2 warm-up GETs are required.
        """
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        try:
            s.get(f'{NSE_BASE}/', timeout=10)
            time.sleep(0.5)
            s.get(f'{NSE_BASE}/market-data/live-equity-market', timeout=10)
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"NSE session warmup warning: {e}")
        return s

    # ── Live indices ───────────────────────────────────────────────────────────

    def fetch_all_indices_live(self) -> list[dict]:
        """
        Fetch all 139 NSE indices with live values.

        Returns:
            List of dicts: [{'index': 'NIFTY 50', 'last': 23913.7, ...}]
        """
        s = self._make_nse_session()
        url = f'{NSE_BASE}/api/allIndices'
        try:
            r = s.get(url, timeout=15)
            r.raise_for_status()
            return r.json().get('data', [])
        except Exception as e:
            logger.error(f"[nse] fetch_all_indices_live failed: {e}")
            return []

    # ── Historical data ────────────────────────────────────────────────────────

    def fetch_index_history(
        self,
        index_name: str,
        from_date: datetime.date,
        to_date: datetime.date,
    ) -> list[dict]:
        """
        Fetch historical daily close for a NSE index.

        Args:
            index_name: Plain string e.g. 'NIFTY 50' (URL-encoded internally)
            from_date:  Start date (inclusive)
            to_date:    End date (inclusive)

        Returns:
            List of {'date': datetime.date, 'close': float}

        Response date format:
            EOD_TIMESTAMP: 'DD-MMM-YYYY' e.g. '01-Jan-2024'
        Response close field:
            EOD_CLOSE_INDEX_VAL: float
        """
        s = self._make_nse_session()
        url = (
            f'{NSE_BASE}/api/historical/indicesHistory'
            f'?indexType={urllib.parse.quote(index_name)}'
            f'&from={from_date.strftime("%d-%m-%Y")}'
            f'&to={to_date.strftime("%d-%m-%Y")}'
        )
        try:
            r = s.get(url, headers=NSE_HEADERS, timeout=20)
            r.raise_for_status()
            raw_rows = r.json().get('data', {}).get('indexCloseOnlineRecords', [])
        except Exception as e:
            logger.warning(f"[nse] Historical fetch failed for '{index_name}': {e}")
            raise AdapterError(str(e)) from e

        results = []
        for row in raw_rows:
            try:
                # ⚠️ Date format: 'DD-MMM-YYYY' e.g. '01-Jan-2024'
                parsed_date = datetime.datetime.strptime(
                    row['EOD_TIMESTAMP'], '%d-%b-%Y'
                ).date()
                parsed_close = float(row['EOD_CLOSE_INDEX_VAL'])
                results.append({'date': parsed_date, 'close': parsed_close})
            except (KeyError, ValueError, TypeError):
                continue

        logger.debug(f"[nse] '{index_name}' {from_date}→{to_date}: {len(results)} rows")
        return results

    def fetch_index_history_chunked(
        self,
        index_name: str,
        from_date: datetime.date,
        to_date: datetime.date,
        chunk_days: int = 365,
    ) -> list[dict]:
        """
        Fetch historical data in chunks (NSE API has date range limits).
        Automatically chunks long date ranges into yearly batches.
        """
        from datetime import timedelta
        results = []
        chunk_start = from_date

        while chunk_start < to_date:
            chunk_end = min(chunk_start + timedelta(days=chunk_days), to_date)
            try:
                chunk = self.fetch_index_history(index_name, chunk_start, chunk_end)
                results.extend(chunk)
                time.sleep(self.RATE_LIMIT_DELAY)
            except AdapterError as e:
                logger.warning(f"[nse] Chunk {chunk_start}→{chunk_end} failed: {e}")
            chunk_start = chunk_end + timedelta(days=1)

        # Sort by date ascending and deduplicate
        seen = set()
        deduped = []
        for r in sorted(results, key=lambda x: x['date']):
            if r['date'] not in seen:
                seen.add(r['date'])
                deduped.append(r)
        return deduped

    # ── yfinance fallback ──────────────────────────────────────────────────────

    def fetch_yfinance_history(
        self,
        yahoo_ticker: str,
        from_date: Optional[datetime.date] = None,
    ) -> list[dict]:
        """
        Fallback: fetch benchmark history from yfinance.

        ⚠️ yfinance is rate-limited — sleep 2s before each call.
        Returns same format as fetch_index_history: [{'date': date, 'close': float}]

        Note: Some tickers (e.g. BSE .BO tickers) don't support period='max'.
        We try period='max' first and fall back to a date-range query.
        """
        import yfinance as yf
        import datetime as _dt

        configure_yfinance_cache(yf)
        time.sleep(2)   # avoid rate limit — confirmed necessary in notebook

        effective_start = from_date or _dt.date(2000, 1, 1)
        end_date = _dt.date.today()

        def _normalise(hist):
            if hist is None or hist.empty:
                return []
            if hasattr(hist.index, 'tz') and hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            results = []
            for ts, row in hist.iterrows():
                d = ts.date() if hasattr(ts, 'date') else ts
                if d >= effective_start:
                    results.append({'date': d, 'close': float(row['Close'])})
            return results

        try:
            ticker = yf.Ticker(yahoo_ticker)

            # First try period='max' (works for most tickers)
            try:
                hist = ticker.history(period='max')
                rows = _normalise(hist)
                if rows:
                    logger.debug(f"[yfinance] {yahoo_ticker}: {len(rows)} rows (period=max)")
                    return rows
            except Exception as e_max:
                logger.debug(f"[yfinance] {yahoo_ticker}: period=max failed ({e_max}), trying date range")

            # Fallback: explicit date range (required for some BSE .BO tickers)
            hist = ticker.history(start=str(effective_start), end=str(end_date))
            rows = _normalise(hist)
            if rows:
                logger.debug(f"[yfinance] {yahoo_ticker}: {len(rows)} rows (date range)")
            return rows

        except Exception as e:
            logger.warning(f"[yfinance] fetch failed for {yahoo_ticker}: {e}")
            return []
