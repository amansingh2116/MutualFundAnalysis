"""
Live market index fetcher for the site header.

Uses the verified Yahoo symbols from apps.benchmarks.registry. Results are
cached briefly so every page load does not hit Yahoo Finance.
"""
from __future__ import annotations

import logging

import pandas as pd
from django.core.cache import cache

from apps.benchmarks.registry import MARKET_INDICES, configure_yfinance_cache

logger = logging.getLogger("mfanalysis")

MARKET_CACHE_KEY = "live_market_indices:v2"
MARKET_CACHE_TTL = 15 * 60
INDICES = list(MARKET_INDICES)


def get_live_indices() -> list[dict]:
    cached = cache.get(MARKET_CACHE_KEY)
    if cached:
        return cached

    results = _fetch_from_yfinance()
    if results:
        cache.set(MARKET_CACHE_KEY, results, MARKET_CACHE_TTL)
    return results


def _fetch_from_yfinance() -> list[dict]:
    try:
        import yfinance as yf

        configure_yfinance_cache(yf)
        tickers = " ".join(idx["ticker"] for idx in INDICES)
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        results = []
        for idx in INDICES:
            results.append(_extract_index_result(data, idx))
        return results
    except Exception as exc:
        logger.error("yfinance batch fetch failed: %s", exc)
        return _fetch_individual_fallback()


def _extract_index_result(data, idx: dict) -> dict:
    ticker = idx["ticker"]
    try:
        if data is None or getattr(data, "empty", True):
            return _placeholder(idx)
        if isinstance(data.columns, pd.MultiIndex):
            if ("Close", ticker) not in data.columns:
                return _placeholder(idx)
            closes = data[("Close", ticker)]
        else:
            closes = data["Close"]
        closes = pd.to_numeric(closes, errors="coerce").dropna()
        if len(closes) >= 2:
            value = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            change = value - prev
            change_pct = (change / prev) * 100 if prev else 0.0
        elif len(closes) == 1:
            value = float(closes.iloc[-1])
            change = 0.0
            change_pct = 0.0
        else:
            return _placeholder(idx)
        return _result(idx, value, change, change_pct)
    except Exception as exc:
        logger.warning("Could not extract %s: %s", ticker, exc)
        return _placeholder(idx)


def _fetch_individual_fallback() -> list[dict]:
    import yfinance as yf

    configure_yfinance_cache(yf)
    results = []
    for idx in INDICES:
        try:
            hist = yf.Ticker(idx["ticker"]).history(period="5d", interval="1d", auto_adjust=True, raise_errors=False)
            closes = pd.to_numeric(hist["Close"], errors="coerce").dropna() if hist is not None and not hist.empty else pd.Series(dtype=float)
            if len(closes) >= 2:
                value = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                change = value - prev
                change_pct = (change / prev) * 100 if prev else 0.0
                results.append(_result(idx, value, change, change_pct))
            elif len(closes) == 1:
                results.append(_result(idx, float(closes.iloc[-1]), 0.0, 0.0))
            else:
                results.append(_placeholder(idx))
        except Exception as exc:
            logger.warning("Individual fetch failed for %s: %s", idx["ticker"], exc)
            results.append(_placeholder(idx))
    return results


def _result(idx: dict, value: float, change: float, change_pct: float) -> dict:
    return {
        "key": idx["key"],
        "label": idx["label"],
        "ticker": idx["ticker"],
        "value": round(value, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "direction": "up" if change >= 0 else "down",
        "stale": False,
    }


def _placeholder(idx: dict) -> dict:
    return {
        "key": idx["key"],
        "label": idx["label"],
        "ticker": idx["ticker"],
        "value": None,
        "change": None,
        "change_pct": None,
        "direction": "neutral",
        "stale": True,
    }

