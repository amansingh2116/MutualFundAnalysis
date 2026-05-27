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

# ── Benchmark ticker mapping table ─────────────────────────────────────────────
# Format: 'Index Name': (yahoo_ticker, 'Close')
# NSE index names must match what NSE API returns in 'index' field.
BENCHMARK_TICKERS: dict[str, tuple[str, str]] = {
    'NIFTY 50':              ('^NSEI',             'Close'),
    'NIFTY NEXT 50':         ('^NSMIDCP',           'Close'),
    'NIFTY 100':             ('^CNX100',             'Close'),
    'NIFTY 200':             ('NIFTY200.NS',         'Close'),
    'NIFTY 500':             ('^CRSLDX',             'Close'),
    'NIFTY MIDCAP 50':       ('NIFMID50.NS',         'Close'),
    'NIFTY MIDCAP 100':      ('NIFMIDCAP100.NS',     'Close'),
    'NIFTY MIDCAP 150':      ('NIFMID150.NS',        'Close'),
    'NIFTY SMALLCAP 50':     ('NIFSMCP50.NS',        'Close'),
    'NIFTY SMALLCAP 100':    ('NIFSMCP100.NS',       'Close'),
    'NIFTY SMALLCAP 250':    ('NIFSMCP250.NS',       'Close'),
    'NIFTY BANK':            ('^NSEBANK',            'Close'),
    'NIFTY IT':              ('^CNXIT',              'Close'),
    'NIFTY PHARMA':          ('^CNXPHARMA',          'Close'),
    'NIFTY FMCG':            ('NIFTYFMCG.NS',        'Close'),
    'S&P 500':               ('^GSPC',               'Close'),
    'NASDAQ 100':            ('^NDX',                'Close'),
    'DOW JONES':             ('^DJI',                'Close'),
}

# ── SEBI category → benchmark mapping ──────────────────────────────────────────
# Used by analytics engine to select the right benchmark for each scheme.
# None means no equity benchmark (debt/liquid funds).
CATEGORY_BENCHMARK_MAP: dict[str, Optional[str]] = {
    'Equity Scheme - Large Cap Fund':           'NIFTY 100',
    'Equity Scheme - Mid Cap Fund':             'NIFTY MIDCAP 150',
    'Equity Scheme - Small Cap Fund':           'NIFTY SMALLCAP 250',
    'Equity Scheme - Flexi Cap Fund':           'NIFTY 500',
    'Equity Scheme - Multi Cap Fund':           'NIFTY 500',
    'Equity Scheme - ELSS':                     'NIFTY 500',
    'Equity Scheme - Large & Mid Cap Fund':     'NIFTY 200',
    'Equity Scheme - Value Fund':               'NIFTY 500',
    'Equity Scheme - Contra Fund':              'NIFTY 500',
    'Equity Scheme - Focused Fund':             'NIFTY 500',
    'Equity Scheme - Dividend Yield Fund':      'NIFTY 500',
    'Equity Scheme - Index Funds':              'NIFTY 50',   # overridden per-fund
    'Equity Scheme - ETFs':                     'NIFTY 50',
    'Hybrid Scheme - Aggressive Hybrid Fund':   'NIFTY 500',
    'Hybrid Scheme - Balanced Hybrid Fund':     'NIFTY 500',
    'Hybrid Scheme - Conservative Hybrid Fund': 'NIFTY 50',
    'Hybrid Scheme - Dynamic Asset Allocation': 'NIFTY 500',
    'Hybrid Scheme - Multi Asset Allocation':   'NIFTY 500',
    'Hybrid Scheme - Arbitrage Fund':           None,
    'Debt Scheme - Liquid Fund':                None,
    'Debt Scheme - Ultra Short Duration Fund':  None,
    'Debt Scheme - Low Duration Fund':          None,
    'Debt Scheme - Short Duration Fund':        None,
    'Debt Scheme - Medium Duration Fund':       None,
    'Debt Scheme - Long Duration Fund':         None,
    'Debt Scheme - Dynamic Bond':               None,
    'Debt Scheme - Corporate Bond Fund':        None,
    'Debt Scheme - Credit Risk Fund':           None,
    'Debt Scheme - Gilt Fund':                  None,
    'Debt Scheme - Overnight Fund':             None,
    'Debt Scheme - Money Market Fund':          None,
    'Solution Oriented Scheme - Retirement Fund': 'NIFTY 500',
    'Solution Oriented Scheme - Childrens Fund':  'NIFTY 500',
    'Other Scheme - FoF Domestic':              None,
    'Other Scheme - FoF Overseas':              None,
}


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
        """
        import yfinance as yf
        time.sleep(2)   # avoid rate limit — confirmed necessary in notebook
        try:
            ticker = yf.Ticker(yahoo_ticker)
            if from_date:
                hist = ticker.history(start=from_date.isoformat())
            else:
                hist = ticker.history(period='max')

            if hist is None or hist.empty:
                return []

            # Remove timezone info from index
            if hasattr(hist.index, 'tz') and hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            results = []
            for ts, row in hist.iterrows():
                results.append({
                    'date':  ts.date() if hasattr(ts, 'date') else ts,
                    'close': float(row['Close']),
                })
            logger.debug(f"[yfinance] {yahoo_ticker}: {len(results)} rows")
            return results
        except Exception as e:
            logger.warning(f"[yfinance] fetch failed for {yahoo_ticker}: {e}")
            return []
