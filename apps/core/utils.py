"""
Utility functions shared across all apps.
"""
from decimal import Decimal
from datetime import date


def format_inr(value, compact=False) -> str:
    """
    Format a number as Indian Rupees.
    compact=True → '₹12.3 Cr' | compact=False → '₹1,23,45,678'
    """
    if value is None:
        return '—'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '—'

    if compact:
        if v >= 1e7:
            return f'₹{v/1e7:.1f} Cr'
        elif v >= 1e5:
            return f'₹{v/1e5:.1f} L'
        else:
            return f'₹{v:,.0f}'

    # Indian number format: 12,34,567
    s = f'{abs(v):.2f}'
    integer_part, decimal_part = s.split('.')
    integer_part = integer_part[::-1]
    groups = [integer_part[:3]] + [integer_part[i:i+2] for i in range(3, len(integer_part), 2)]
    formatted = ','.join(groups)[::-1]
    sign = '-' if v < 0 else ''
    return f'{sign}₹{formatted}.{decimal_part}'


def format_pct(value, decimals=2, sign=True) -> str:
    """
    Format a percentage value.
    Returns '—' for None/NaN.
    sign=True → adds '+' for positive values.
    """
    if value is None:
        return '—'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '—'
    import math
    if math.isnan(v):
        return '—'
    prefix = '+' if (sign and v > 0) else ''
    return f'{prefix}{v:.{decimals}f}%'


def safe_div(numerator, denominator, default=None):
    """
    Safe division that returns default on ZeroDivisionError or None inputs.
    """
    if numerator is None or denominator is None:
        return default
    try:
        if float(denominator) == 0:
            return default
        return float(numerator) / float(denominator)
    except (TypeError, ValueError):
        return default


def cagr(start_value, end_value, years: float) -> float | None:
    """
    Compute Compound Annual Growth Rate (CAGR).
    Returns None if inputs are invalid.
    """
    if years <= 0 or start_value is None or end_value is None:
        return None
    try:
        sv, ev = float(start_value), float(end_value)
        if sv <= 0:
            return None
        return ((ev / sv) ** (1.0 / years) - 1) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def parse_amfi_date(date_str: str) -> date | None:
    """Parse DD-MM-YYYY date string (AMFI/mfapi format)."""
    from datetime import datetime
    try:
        return datetime.strptime(date_str.strip(), '%d-%m-%Y').date()
    except (ValueError, AttributeError):
        return None


def parse_nse_date(date_str: str) -> date | None:
    """Parse DD-MMM-YYYY date string (NSE API format, e.g. '01-Jan-2024')."""
    from datetime import datetime
    try:
        return datetime.strptime(date_str.strip(), '%d-%b-%Y').date()
    except (ValueError, AttributeError):
        return None


def parse_iso_date(date_str: str) -> date | None:
    """Parse YYYY-MM-DD date string (captnemo/ISO format)."""
    try:
        return date.fromisoformat(date_str.strip())
    except (ValueError, AttributeError):
        return None


def is_direct_scheme(scheme_name: str) -> bool:
    """Detect if a scheme name contains 'Direct' keyword."""
    return 'direct' in scheme_name.lower()


def is_growth_scheme(scheme_name: str) -> bool:
    """Detect if a scheme is Growth (not IDCW/Dividend)."""
    name = scheme_name.lower()
    return 'growth' in name and 'idcw' not in name and 'dividend' not in name


def is_etf_scheme(scheme_name: str) -> bool:
    """Detect if a scheme is an ETF."""
    return 'etf' in scheme_name.lower()


def latest_month_date() -> date:
    """Return the first day of the current month — used for holdings queries."""
    today = date.today()
    return date(today.year, today.month, 1)
