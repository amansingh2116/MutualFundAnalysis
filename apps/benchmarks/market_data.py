"""
apps/benchmarks/market_data.py — Live Market Index Fetcher
============================================================
Fetches live index values (Nifty 50, Sensex, etc.) using yfinance.
Results are cached for 15 minutes to avoid hammering Yahoo Finance.

Indices:
  ^NSEI        → Nifty 50
  ^BSESN       → BSE Sensex
  ^NSEMDCP150  → Nifty Midcap 150
  ^NSESMCP250  → Nifty Smallcap 250
  USDINR=X     → USD/INR exchange rate
"""
import logging
from django.core.cache import cache

logger = logging.getLogger('mfanalysis')

MARKET_CACHE_KEY = 'live_market_indices'
MARKET_CACHE_TTL = 15 * 60   # 15 minutes

INDICES = [
    {'key': 'nifty50',  'ticker': '^NSEI',       'label': 'NIFTY 50'},
    {'key': 'sensex',   'ticker': '^BSESN',       'label': 'SENSEX'},
    {'key': 'midcap',   'ticker': '^NSEMDCP150',  'label': 'NIFTY MIDCAP 150'},
    {'key': 'smallcap', 'ticker': '^NSESMCP250',  'label': 'NIFTY SMALLCAP 250'},
    {'key': 'usdinr',   'ticker': 'USDINR=X',     'label': '₹/USD'},
]


def get_live_indices() -> list[dict]:
    """
    Returns list of dicts:
      [{'key': 'nifty50', 'label': 'NIFTY 50', 'value': 22450.50,
        'change': 123.4, 'change_pct': 0.55, 'direction': 'up'}, ...]

    Cached 15 minutes. Returns stale data with 'stale': True on error.
    """
    cached = cache.get(MARKET_CACHE_KEY)
    if cached:
        return cached

    results = _fetch_from_yfinance()
    if results:
        cache.set(MARKET_CACHE_KEY, results, MARKET_CACHE_TTL)
    return results


def _fetch_from_yfinance() -> list[dict]:
    """Fetch all index values from Yahoo Finance in a single batch call."""
    try:
        import yfinance as yf
        tickers = ' '.join(i['ticker'] for i in INDICES)
        data = yf.download(
            tickers,
            period='2d',
            interval='1d',
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        results = []
        for idx in INDICES:
            ticker = idx['ticker']
            try:
                close_col = ('Close', ticker) if isinstance(data.columns, type(data.columns)) and hasattr(data.columns, 'levels') else 'Close'
                closes = data['Close'][ticker] if 'Close' in data.columns.get_level_values(0) else data['Close']
                closes = closes.dropna()
                if len(closes) >= 2:
                    today_val  = float(closes.iloc[-1])
                    prev_val   = float(closes.iloc[-2])
                    change     = today_val - prev_val
                    change_pct = (change / prev_val) * 100
                elif len(closes) == 1:
                    today_val  = float(closes.iloc[-1])
                    change     = 0.0
                    change_pct = 0.0
                else:
                    today_val = change = change_pct = None

                results.append({
                    'key':        idx['key'],
                    'label':      idx['label'],
                    'ticker':     ticker,
                    'value':      round(today_val, 2) if today_val else None,
                    'change':     round(change, 2) if change is not None else None,
                    'change_pct': round(change_pct, 2) if change_pct is not None else None,
                    'direction':  'up' if (change or 0) >= 0 else 'down',
                    'stale':      False,
                })
            except Exception as e:
                logger.warning(f"Could not extract {ticker}: {e}")
                results.append(_placeholder(idx))

        return results

    except Exception as e:
        logger.error(f"yfinance batch fetch failed: {e}")
        # Try individual fetches as fallback
        return _fetch_individual_fallback()


def _fetch_individual_fallback() -> list[dict]:
    """Fetch each index one by one using fast_info (more reliable, rate-limited)."""
    import yfinance as yf
    results = []
    for idx in INDICES:
        try:
            ticker_obj = yf.Ticker(idx['ticker'])
            info = ticker_obj.fast_info
            value      = float(info.last_price)
            prev_close = float(info.previous_close) if hasattr(info, 'previous_close') else value
            change     = value - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            results.append({
                'key':        idx['key'],
                'label':      idx['label'],
                'ticker':     idx['ticker'],
                'value':      round(value, 2),
                'change':     round(change, 2),
                'change_pct': round(change_pct, 2),
                'direction':  'up' if change >= 0 else 'down',
                'stale':      False,
            })
        except Exception as e:
            logger.warning(f"Individual fetch failed for {idx['ticker']}: {e}")
            results.append(_placeholder(idx))
    return results


def _placeholder(idx: dict) -> dict:
    return {
        'key':        idx['key'],
        'label':      idx['label'],
        'ticker':     idx['ticker'],
        'value':      None,
        'change':     None,
        'change_pct': None,
        'direction':  'neutral',
        'stale':      True,
    }
