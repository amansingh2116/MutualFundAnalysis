"""apps/portfolio/parsers.py — Excel/CSV portfolio transaction parser"""
import logging
from datetime import date, datetime
from typing import IO

import pandas as pd
from rapidfuzz import fuzz, process

from apps.funds.models import Scheme

logger = logging.getLogger('mfanalysis')

EXPECTED_COLUMNS = {
    'scheme_name': ['scheme name', 'fund name', 'fund', 'scheme', 'mutual fund'],
    'tx_date': ['date', 'transaction date', 'nav date', 'value date'],
    'tx_type': ['type', 'transaction type', 'txn type'],
    'units': ['units', 'quantity', 'no of units'],
    'nav': ['nav', 'price', 'nav price'],
    'amount': ['amount', 'value', 'txn amount', 'transaction amount'],
    'folio': ['folio', 'folio no', 'folio number'],
}

TX_TYPE_MAP = {
    'buy': 'BUY', 'purchase': 'BUY', 'switch in': 'SWITCH_IN', 'switch-in': 'SWITCH_IN',
    'sip': 'SIP', 'systematic investment plan': 'SIP',
    'sell': 'SELL', 'redemption': 'REDEEM', 'redeem': 'REDEEM',
    'switch out': 'SWITCH_OUT', 'switch-out': 'SWITCH_OUT',
    'dividend': 'IDCW',
}


def _match_column(header: str, candidates: list[str]) -> bool:
    return header.lower().strip() in candidates


def detect_columns(df: pd.DataFrame) -> dict:
    """Fuzzy-match DataFrame headers to expected column names."""
    col_map = {}
    headers = [c.lower().strip() for c in df.columns]
    for field, candidates in EXPECTED_COLUMNS.items():
        for i, h in enumerate(headers):
            if h in candidates:
                col_map[field] = df.columns[i]
                break
    return col_map


def parse_portfolio_file(file_obj: IO) -> list[dict]:
    """
    Parse an Excel (.xlsx) or CSV file with transaction data.
    Returns list of standardised transaction dicts.
    Raises ValueError on unrecognisable format.
    """
    filename = getattr(file_obj, 'name', '').lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file_obj)
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_obj)
        else:
            # Try CSV first, then Excel
            try:
                df = pd.read_csv(file_obj)
            except Exception:
                file_obj.seek(0)
                df = pd.read_excel(file_obj)
    except Exception as e:
        raise ValueError(f'Could not read file: {e}')

    if df.empty:
        raise ValueError('The uploaded file is empty.')

    col_map = detect_columns(df)
    if 'scheme_name' not in col_map:
        raise ValueError(
            'Could not find a "Scheme Name" or "Fund Name" column. '
            f'Found columns: {list(df.columns)}'
        )

    transactions = []
    for _, row in df.iterrows():
        scheme_name = str(row.get(col_map.get('scheme_name', ''), '')).strip()
        if not scheme_name or scheme_name.lower() in ('nan', 'none', ''):
            continue

        # Parse date
        raw_date = row.get(col_map.get('tx_date', ''))
        tx_date = None
        if pd.notna(raw_date):
            try:
                tx_date = pd.to_datetime(raw_date).date()
            except Exception:
                tx_date = date.today()

        # Parse type
        raw_type = str(row.get(col_map.get('tx_type', ''), 'BUY')).lower().strip()
        tx_type = TX_TYPE_MAP.get(raw_type, 'BUY')

        # Parse numeric fields
        def safe_float(val, default=None):
            try:
                return float(str(val).replace(',', '').strip())
            except Exception:
                return default

        units = safe_float(row.get(col_map.get('units', ''), 0), 0)
        nav = safe_float(row.get(col_map.get('nav', '')), None)
        amount = safe_float(row.get(col_map.get('amount', '')), None)
        folio = str(row.get(col_map.get('folio', ''), '')).strip()

        if amount is None and units and nav:
            amount = units * nav

        transactions.append({
            'scheme_name': scheme_name,
            'tx_date': tx_date,
            'tx_type': tx_type,
            'units': units or 0,
            'nav': nav,
            'amount': amount or 0,
            'folio': folio,
            'matched_scheme': None,  # will be filled by fuzzy match
        })

    if not transactions:
        raise ValueError('No valid transactions found in the file.')

    # Fuzzy match scheme names to DB
    _fuzzy_match_schemes(transactions)
    return transactions


def _fuzzy_match_schemes(transactions: list[dict]) -> None:
    """In-place fuzzy match scheme names to Scheme objects."""
    all_schemes = list(Scheme.objects.filter(is_active=True).values('id', 'amfi_code', 'scheme_name', 'is_direct', 'plan'))
    scheme_names = [s['scheme_name'] for s in all_schemes]

    for tx in transactions:
        raw_name = tx['scheme_name']
        # rapidfuzz best match
        result = process.extractOne(
            raw_name, scheme_names,
            scorer=fuzz.WRatio,
            score_cutoff=75
        )
        if result:
            matched_name, score, idx = result
            tx['matched_scheme'] = all_schemes[idx]
            tx['match_score'] = score
            logger.debug(f"Matched '{raw_name}' → '{matched_name}' (score {score})")
        else:
            tx['match_score'] = 0
            logger.warning(f"No match for '{raw_name}' (below threshold)")
