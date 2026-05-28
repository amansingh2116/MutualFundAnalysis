"""
mstarpy Adapter
===============
Source for:
  - Full equity holdings (all stocks with weights, sector, P/E, ISIN)
  - Sector allocation
  - Trailing returns + Morningstar category/rating
  - Risk volatility measures (beta, alpha, Sharpe, R², std dev)
  - Max drawdown
  - Portfolio statistics (market cap blend)

⚠️ CRITICAL — CONFIRMED IN NOTEBOOK (v10.0.0):
  The 'country' kwarg was REMOVED in mstarpy v10.0.0.
  Use _init_fund() which inspects the constructor signature at runtime.

mstarpy requires a Morningstar SecId (e.g. 'F00000PDX2'), not AMFI code.
SecIds are stored in Scheme.morningstar_id (nullable).
If Scheme.morningstar_id is None → skip all mstarpy calls for that fund.
"""
import inspect
import logging
from typing import Optional

from .base import BaseAdapter

logger = logging.getLogger('adapters.mstarpy')


class MstarpyAdapter(BaseAdapter):
    """
    Adapter for the mstarpy library (Morningstar data).
    
    Usage:
        adapter = MstarpyAdapter()
        holdings_df = adapter.fetch_holdings('F00000PDX2')
    """
    SOURCE_NAME      = 'mstarpy'
    RATE_LIMIT_DELAY = 2.0   # 2s between calls — Morningstar rate-limits aggressively

    _FUNDS_PARAMS: Optional[list] = None  # cached constructor params

    @classmethod
    def _get_funds_params(cls) -> list:
        """Cache and return mstarpy.Funds.__init__ parameter names."""
        if cls._FUNDS_PARAMS is None:
            try:
                import mstarpy
                sig = inspect.signature(mstarpy.Funds.__init__)
                cls._FUNDS_PARAMS = list(sig.parameters.keys())
                logger.debug(f"mstarpy.Funds params: {cls._FUNDS_PARAMS}")
            except ImportError:
                cls._FUNDS_PARAMS = []
        return cls._FUNDS_PARAMS

    def _init_fund(self, mstar_id: str):
        """
        Version-agnostic mstarpy.Funds() constructor.

        v10.0.0: mstarpy.Funds(term=mstar_id)  ← no country kwarg
        older:   mstarpy.Funds(term=mstar_id, country='IN')

        Inspects constructor signature at runtime to handle both.
        """
        import mstarpy
        params = self._get_funds_params()

        if 'country' in params:
            return mstarpy.Funds(term=mstar_id, country='IN')
        elif 'region' in params:
            return mstarpy.Funds(term=mstar_id, region='ASIA')
        else:
            # v10.0.0 confirmed working without country/region
            return mstarpy.Funds(term=mstar_id)

    def is_available(self) -> bool:
        """Check if mstarpy is installed."""
        try:
            import mstarpy  # noqa
            return True
        except ImportError:
            return False

    def fetch_holdings(self, mstar_id: str):
        """
        Fetch full equity holdings.

        Returns:
            pandas DataFrame with columns:
              securityName, weighting, marketValue, shareChange, country,
              ticker, totalReturn1Year, forwardPERatio, sector, isin, holdingType
            or None on failure.
        """
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            result = fund.holdings()
            logger.debug(f"[mstarpy] Holdings for {mstar_id}: {len(result) if result is not None else 0} rows")
            return result
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_holdings failed for {mstar_id}: {e}")
            return None

    def fetch_sector_allocation(self, mstar_id: str):
        """
        Fetch sector allocation.

        Returns:
            DataFrame or dict with sector → weight % mapping, or None on failure.
        """
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            return fund.sectorAllocation()
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_sector_allocation failed for {mstar_id}: {e}")
            return None

    def fetch_trailing_returns(self, mstar_id: str) -> Optional[dict]:
        """
        Fetch trailing returns and Morningstar rating.

        Returns dict with keys (among others):
          overallMorningstarRating, categoryName,
          totalReturnNAV (fund trailing), totalReturnCategory
        """
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            return fund.trailingReturn()
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_trailing_returns failed for {mstar_id}: {e}")
            return None

    def fetch_risk_metrics(self, mstar_id: str) -> Optional[dict]:
        """
        Fetch risk volatility measures.

        Returns dict keyed by '3Year'/'5Year' containing:
          standardDeviation, sharpeRatio, beta, alpha, rSquared, informationRatio
        """
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            data = fund.riskVolatilityMeasures()
            # Normalise to dict indexed by period if DataFrame returned
            import pandas as pd
            if isinstance(data, pd.DataFrame) and 'period' in data.columns:
                return data.set_index('period').to_dict('index')
            return data
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_risk_metrics failed for {mstar_id}: {e}")
            return None

    def fetch_max_drawdown(self, mstar_id: str) -> Optional[dict]:
        """Fetch max drawdown data."""
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            return fund.maxDrawDown()
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_max_drawdown failed for {mstar_id}: {e}")
            return None

    def fetch_portfolio_statistics(self, mstar_id: str) -> Optional[dict]:
        """Fetch portfolio statistics (market cap blend, P/E, etc.)."""
        import time
        try:
            fund = self._init_fund(mstar_id)
            time.sleep(self.RATE_LIMIT_DELAY)
            return fund.portfolioStatistics()
        except Exception as e:
            logger.warning(f"[mstarpy] fetch_portfolio_statistics failed for {mstar_id}: {e}")
            return None

    def search_fund(self, name: str, page_size: int = 5) -> list:
        """
        Search for a fund by name to get its Morningstar SecId.
        Used by build_mstar_mapping management command.

        Returns:
            List of dicts with 'SecId', 'Name', 'LegalName' etc.
        """
        try:
            from mstarpy.search import MorningstarSession
            session = MorningstarSession()
            results = session.screener_universe(name, field=["SecId", "Name"], pageSize=page_size)
            return [r.get('meta', {}) | r.get('fields', {}) for r in results]
        except Exception as e:
            logger.warning(f"[mstarpy] search_fund failed for '{name}': {e}")
            return []
