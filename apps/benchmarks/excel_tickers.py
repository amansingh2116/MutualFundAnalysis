"""
excel_tickers.py — Load Yahoo Finance tickers from the user-maintained Excel file.

File path: documentation/index_benchmark_tickers_available.xlsx
Columns  : 'Index / Benchmark Name', 'Ticker'

This module is used by ingest_benchmarks to dynamically resolve yahoo_tickers
for benchmark indices without requiring code changes to registry.py.

To add new indices: just add rows to the Excel file and re-run ingest_benchmarks.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mfanalysis")

# Path to the Excel file relative to Django project root (BASE_DIR)
_EXCEL_RELATIVE_PATH = "documentation/index_benchmark_tickers_available.xlsx"


def _normalise(name: str) -> str:
    """Normalise an index name for matching: uppercase, collapse spaces, strip punctuation."""
    s = name.upper().strip()
    # Remove common suffixes that differ between Excel and DB names
    for suffix in (" TRI", " TOTAL RETURN INDEX", " INDEX"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s)
    return s


def load_excel_ticker_map(base_dir: Optional[Path] = None) -> dict[str, str]:
    """
    Load the Excel ticker file and return a dict keyed by *normalised* index name.

    Returns
    -------
    dict[str, str]
        { normalised_name → yahoo_ticker }
        Also includes original (un-normalised, uppercased) name as a secondary key.

    Returns empty dict if file is not found or openpyxl is unavailable.
    """
    if base_dir is None:
        # Infer from this file's location: go up to project root
        base_dir = Path(__file__).resolve().parents[4]  # apps/benchmarks/ → project root

    xlsx_path = base_dir / _EXCEL_RELATIVE_PATH
    if not xlsx_path.exists():
        logger.warning("excel_tickers: Excel file not found at %s — skipping", xlsx_path)
        return {}

    try:
        import openpyxl
    except ImportError:
        logger.warning("excel_tickers: openpyxl not installed — cannot read Excel ticker file")
        return {}

    try:
        wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        logger.warning("excel_tickers: Failed to read Excel file: %s", exc)
        return {}

    if not rows:
        return {}

    # Skip header row
    ticker_map: dict[str, str] = {}
    loaded = 0
    for row in rows[1:]:
        if not row or len(row) < 2:
            continue
        raw_name = row[0]
        raw_ticker = row[1]
        if not raw_name or not raw_ticker:
            continue
        name = str(raw_name).strip()
        ticker = str(raw_ticker).strip()
        if not name or not ticker:
            continue

        # Store under normalised key (TRI stripped etc.)
        norm = _normalise(name)
        ticker_map[norm] = ticker
        # Also store under original uppercased name in case exact match is needed
        ticker_map[name.upper()] = ticker
        loaded += 1

    logger.info("excel_tickers: Loaded %d ticker mappings from %s", loaded, xlsx_path.name)
    return ticker_map


def resolve_ticker_from_excel(
    index_name: str,
    ticker_map: dict[str, str],
) -> str:
    """
    Given an index name and the pre-loaded ticker map, return the best-matching ticker.

    Matching order:
    1. Exact match (normalised)
    2. Original uppercase match
    3. Empty string if no match
    """
    if not index_name or not ticker_map:
        return ""

    # Try normalised match (strips TRI etc.)
    norm = _normalise(index_name)
    if norm in ticker_map:
        return ticker_map[norm]

    # Try uppercased exact match
    upper = index_name.upper().strip()
    if upper in ticker_map:
        return ticker_map[upper]

    return ""
