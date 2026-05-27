"""
captnemo.in (Kuvera proxy) Adapter
====================================
Primary source for fund enrichment metadata:
  - Expense ratio, AUM, fund manager, investment objective
  - SIP/lumpsum rules, lock-in, tax period
  - Pre-computed returns (1W, 1Y, 3Y, 5Y, inception)
  - CRISIL rating, Kuvera fund rating
  - Peer comparison list

API endpoint:
  GET https://mf.captnemo.in/kuvera/{isin}

⚠️ CRITICAL — CONFIRMED IN NOTEBOOK:
  The API ALWAYS returns a LIST, never a plain dict.
  You must ALWAYS access raw[0] (after filtering for Direct Growth).

Field names in response exactly match SchemeMeta model fields.
Date format: 'YYYY-MM-DD' (ISO) → use date.fromisoformat()
"""
import logging
from typing import Optional
from .base import BaseAdapter

logger = logging.getLogger('adapters.captnemo')

CAPTNEMO_BASE = 'https://mf.captnemo.in'


class CaptnemoAdapter(BaseAdapter):
    """
    Adapter for mf.captnemo.in — Kuvera fund data proxy.
    
    Usage:
        adapter = CaptnemoAdapter()
        info = adapter.fetch_fund_info(isin='INF209K01UN5')
        returns = adapter.extract_returns(info)
    """
    SOURCE_NAME      = 'captnemo'
    RATE_LIMIT_DELAY = 1.0   # 1s between requests (be gentle with this free API)

    def fetch_fund_info(self, isin: str) -> Optional[dict]:
        """
        Fetch fund enrichment data by ISIN (Growth ISIN preferred).

        ⚠️ Returns a SINGLE dict (Direct Growth plan if available),
           but the raw API response is a list — this method normalises it.

        Args:
            isin: ISIN string (Growth or IDCW; Growth preferred)

        Returns:
            Single fund info dict, or None on failure.
        """
        url = f'{CAPTNEMO_BASE}/kuvera/{isin}'
        try:
            response = self._get_with_retry(url)
            raw = response.json()
        except Exception as e:
            logger.warning(f"[captnemo] Failed for ISIN {isin}: {e}")
            return None

        return self._normalise_response(raw, isin)

    def _normalise_response(self, raw, isin: str) -> Optional[dict]:
        """
        Normalise the list-wrapped API response.
        Prefers Direct Growth plan; falls back to first item in list.
        """
        if not raw:
            logger.warning(f"[captnemo] Empty response for ISIN {isin}")
            return None

        # API always returns a list — confirmed in notebook
        if isinstance(raw, list):
            # Prefer Direct Growth
            direct_growth = [
                p for p in raw
                if str(p.get('direct', '')).upper() == 'Y'
                and str(p.get('plan', '')).upper() == 'GROWTH'
            ]
            if direct_growth:
                return direct_growth[0]
            # Fallback: any Growth
            growth = [p for p in raw if str(p.get('plan', '')).upper() == 'GROWTH']
            if growth:
                return growth[0]
            return raw[0]

        # Unexpected: single dict returned
        logger.debug(f"[captnemo] Non-list response for ISIN {isin} — using as-is")
        return raw

    def fetch_fund_info_by_amfi(self, amfi_code: str) -> Optional[dict]:
        """
        Alternative: fetch by AMFI code (Kuvera uses AMFI code as identifier too).
        """
        url = f'{CAPTNEMO_BASE}/kuvera/mf/{amfi_code}'
        try:
            response = self._get_with_retry(url)
            raw = response.json()
            return self._normalise_response(raw, amfi_code)
        except Exception as e:
            logger.warning(f"[captnemo] AMFI fetch failed for {amfi_code}: {e}")
            return None

    def extract_returns(self, fund_info: dict) -> dict:
        """
        Extract pre-computed returns from a captnemo fund info dict.

        captnemo returns nested: fund_info['returns'] = {
            'week_1': float,   'month_1': float, 'month_3': float,
            'year_1': float,   'year_3': float,  'year_5': float,
            'inception': float
        }
        Values are in % (e.g. 24.5 means 24.5% return).
        """
        r = fund_info.get('returns') or {}
        return {
            'returns_1w':        r.get('week_1'),
            'returns_1m':        r.get('month_1'),
            'returns_3m':        r.get('month_3'),
            'returns_1y':        r.get('year_1'),
            'returns_3y':        r.get('year_3'),
            'returns_5y':        r.get('year_5'),
            'returns_inception': r.get('inception'),
        }

    def extract_scheme_meta(self, fund_info: dict) -> dict:
        """
        Map captnemo fields to SchemeMeta model fields.
        Returns a flat dict ready to pass to SchemeMeta.objects.update_or_create().
        """
        from apps.core.utils import parse_iso_date

        def _bool(v):
            return str(v).upper() == 'Y' if v is not None else False

        def _int_safe(v):
            try:
                return int(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        def _dec_safe(v):
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        sip_dates_raw = fund_info.get('sip_dates', '')
        sip_dates = [d.strip() for d in str(sip_dates_raw).split(',') if d.strip()] \
                    if sip_dates_raw else []

        returns = self.extract_returns(fund_info)

        return {
            # Investment rules
            'lump_available':       _bool(fund_info.get('lump_available')),
            'lump_min':             _dec_safe(fund_info.get('lump_min')),
            'lump_min_additional':  _dec_safe(fund_info.get('lump_min_additional')),
            'sip_available':        _bool(fund_info.get('sip_available')),
            'sip_min':              _dec_safe(fund_info.get('sip_min')),
            'sip_dates':            sip_dates,
            'sip_multiplier':       _dec_safe(fund_info.get('sip_multiplier')),
            'redemption_allowed':   _bool(fund_info.get('redemption_allowed', 'Y')),
            'switch_allowed':       _bool(fund_info.get('switch_allowed', 'Y')),
            'stp_flag':             _bool(fund_info.get('stp_flag')),
            'swp_flag':             _bool(fund_info.get('swp_flag')),
            'lock_in_period':       _int_safe(fund_info.get('lock_in_period')) or 0,
            'tax_period':           _int_safe(fund_info.get('tax_period')) or 0,
            # Cost metrics
            'expense_ratio':        _dec_safe(fund_info.get('expense_ratio')),
            'expense_ratio_date':   parse_iso_date(fund_info.get('expense_ratio_date', '')),
            'aum':                  _int_safe(fund_info.get('aum')),
            'fund_rating':          _int_safe(fund_info.get('fund_rating')),
            'fund_rating_date':     parse_iso_date(fund_info.get('fund_rating_date', '')),
            'volatility':           _dec_safe(fund_info.get('volatility')),
            # Returns
            **returns,
            # Textual
            'fund_manager':         str(fund_info.get('fund_manager') or ''),
            'crisil_rating':        str(fund_info.get('crisil_rating') or ''),
            'investment_objective': str(fund_info.get('investment_objective') or ''),
            'portfolio_turnover':   _dec_safe(fund_info.get('portfolio_turnover')),
            'start_date':           parse_iso_date(fund_info.get('start_date', '')),
            'detail_info_url':      str(fund_info.get('detail_info_url') or ''),
            # Peers
            'comparison_peers':     fund_info.get('comparison') or [],
            # Provenance
            'fetch_source': 'captnemo',
        }
