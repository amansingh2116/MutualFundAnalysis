"""
AMFI + mfapi.in Adapter
========================
Primary source for:
  - Scheme universe (NAVAll.txt)
  - Full NAV history (mfapi.in)
  - Scheme metadata (mfapi.in meta block)

NAVAll.txt format (semicolon-delimited):
  Scheme Code;ISIN Growth;ISIN IDCW;Scheme Name;NAV;Date

mfapi.in endpoints:
  GET https://api.mfapi.in/mf/{amfi_code}
    → {'meta': {...}, 'data': [{'date': 'DD-MM-YYYY', 'nav': '...'}]}

Date format: 'DD-MM-YYYY' → use apps.core.utils.parse_amfi_date()
"""
import logging
from typing import Optional
from .base import BaseAdapter

logger = logging.getLogger('adapters.amfi')

AMFI_NAV_URL = 'https://www.amfiindia.com/spages/NAVAll.txt'
MFAPI_BASE   = 'https://api.mfapi.in/mf'


class AMFIAdapter(BaseAdapter):
    """
    Adapter for AMFI NAVAll.txt and mfapi.in REST API.
    No authentication required. mfapi.in has generous rate limits.
    """
    SOURCE_NAME       = 'amfi_mfapi'
    RATE_LIMIT_DELAY  = 0.2   # 200ms between mfapi.in calls

    # ── Scheme Universe ────────────────────────────────────────────────────────

    def fetch_scheme_universe(self) -> list[dict]:
        """
        Download and parse AMFI NAVAll.txt.

        Returns:
            List of dicts with keys:
              amfi_code, isin_growth, isin_idcw, scheme_name, nav, date, amc_name
              
        Note: 'amc_name' is the AMC section header extracted from the file.
        """
        logger.info("Fetching AMFI scheme universe from NAVAll.txt")
        response = self._get_with_retry(AMFI_NAV_URL, timeout=30)
        return self._parse_navall(response.text)

    def _parse_navall(self, text: str) -> list[dict]:
        """
        Parse the raw NAVAll.txt content.

        File structure:
          Open Ended Schemes(Debt Schemes)
          ;ISIN Growth;ISIN IDCW;Scheme Name;NAV;Date
          120503;INF209K01UN5;INF209K01UP0;Aditya Birla...; 15.234;27-May-2026
          ...
          [blank line separates AMC sections]
        """
        schemes      = []
        current_type = ''
        current_amc  = ''

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Section headers: 'Open Ended Schemes(...)' or 'Close Ended Schemes(...)'
            if line.startswith(('Open Ended', 'Close Ended', 'Interval')):
                current_type = line
                continue

            # AMC name lines: appear before scheme rows within a section
            # They DON'T start with a digit and don't contain semicolons
            if not line[0].isdigit() and ';' not in line:
                current_amc = line
                continue

            # Scheme data rows: start with digit, semicolon-delimited
            parts = line.split(';')
            if len(parts) < 6 or not parts[0].strip().isdigit():
                continue

            schemes.append({
                'amfi_code':   parts[0].strip(),
                'isin_growth': parts[1].strip() or None,
                'isin_idcw':   parts[2].strip() or None,
                'scheme_name': parts[3].strip(),
                'nav':         parts[4].strip(),
                'date':        parts[5].strip(),
                'amc_name':    current_amc,
                'scheme_type': current_type,
            })

        logger.info(f"Parsed {len(schemes)} schemes from NAVAll.txt")
        return schemes

    # ── NAV History ────────────────────────────────────────────────────────────

    def fetch_nav_history(self, amfi_code: str) -> list[dict]:
        """
        Fetch full NAV history for a scheme from mfapi.in.

        Returns:
            List of {'date': 'DD-MM-YYYY', 'nav': '123.4567'}
            (newest date first, as returned by mfapi.in)
        """
        url = f'{MFAPI_BASE}/{amfi_code}'
        try:
            response = self._get_with_retry(url)
            data = response.json()
            history = data.get('data', [])
            logger.debug(f"[{amfi_code}] mfapi.in returned {len(history)} NAV entries")
            return history
        except Exception as e:
            logger.warning(f"[{amfi_code}] mfapi.in fetch failed: {e}")
            return []

    def fetch_scheme_meta(self, amfi_code: str) -> Optional[dict]:
        """
        Fetch scheme metadata from mfapi.in meta block.

        Returns:
            dict with: scheme_name, fund_house, scheme_type, scheme_category
            or None on failure
        """
        url = f'{MFAPI_BASE}/{amfi_code}'
        try:
            response = self._get_with_retry(url)
            return response.json().get('meta', {})
        except Exception as e:
            logger.warning(f"[{amfi_code}] mfapi.in meta fetch failed: {e}")
            return None

    # ── mftool Fallback ────────────────────────────────────────────────────────

    def fetch_nav_history_mftool(self, amfi_code: str) -> list[dict]:
        """
        Fallback: fetch NAV history via mftool library.
        Returns same format as fetch_nav_history().
        """
        try:
            from mftool import Mftool
            mf = Mftool()
            raw = mf.get_scheme_historical_nav(amfi_code)
            if not raw or 'data' not in raw:
                return []
            # mftool returns: [{'date': 'DD-MM-YYYY', 'nav': '123.456', 'repurchase_price': ..., 'sale_price': ...}]
            return [{'date': r['date'], 'nav': r['nav']} for r in raw['data']]
        except Exception as e:
            logger.warning(f"[{amfi_code}] mftool fallback failed: {e}")
            return []
