"""
apps/holdings/cap_classifier.py
================================
SEBI Market-Cap Classifier for mutual fund portfolio holdings.

Maps each equity security name to large / mid / small cap using fuzzy matching
against the static `data/nifty_caplist.json` reference file.

SEBI Classification (as per SEBI Circular SEBI/HO/IMD/DF3/CIR/P/2017/114):
  Large Cap  : Top 100 stocks by market cap  (Nifty 50 + Nifty Next 50)
  Mid Cap    : 101st - 250th stocks          (Nifty Midcap 150)
  Small Cap  : 251st onwards                 (everything else = residual)

Usage:
    from apps.holdings.cap_classifier import CapClassifier
    clf = CapClassifier()                       # loads JSON automatically
    cat = clf.classify("HDFC Bank Ltd")         # -> 'large'
    result = clf.classify_portfolio(holdings)   # -> {'large_pct': 45.2, ...}
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger('mfanalysis')

# Paths
_HERE        = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT   = os.path.abspath(os.path.join(_HERE, '..', '..'))
_CAPLIST_PATH = os.path.join(_REPO_ROOT, 'data', 'nifty_caplist.json')

# Fuzzy match threshold (rapidfuzz WRatio 0-100)
_SCORE_THRESHOLD = 82

# Legal entity suffixes to strip (DO NOT strip substantive words like bank, power, energy, etc.)
_LEGAL_SUFFIXES = re.compile(
    r'\b(ltd|limited|pvt|private|inc|incorporated|corp|corporation|co|company|llc|plc|'
    r'ordinary shares|ord shs|class a|class b|shares|dr|adr|gdr)\b',
    re.IGNORECASE,
)
_TICKER_SUFFIX = re.compile(r'\.(NS|BO|NSE|BSE|IN)$', re.IGNORECASE)
_PUNCTUATION   = re.compile(r'[.\-_&\',()/]')
_EXTRA_SPACES  = re.compile(r'\s{2,}')


def _normalize(name: str) -> str:
    """Lowercase, strip ticker suffixes, punctuation, and corporate entity suffixes."""
    name = str(name or '').strip()
    name = _TICKER_SUFFIX.sub('', name)
    name = _PUNCTUATION.sub(' ', name)
    name = _LEGAL_SUFFIXES.sub(' ', name)
    name = _EXTRA_SPACES.sub(' ', name)
    return name.lower().strip()


class CapClassifier:
    """
    Classifies equity security names into SEBI large / mid / small categories.
    Thread-safe after construction (read-only operations on immutable data).
    """

    def __init__(self, caplist_path: str = _CAPLIST_PATH):
        self._path   = caplist_path
        self._raw:   dict[str, str] = {}
        self._keys:  list[str]      = []
        self._loaded = False
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            stocks: dict = data.get('stocks', {})
            self._raw    = {_normalize(k): v for k, v in stocks.items() if _normalize(k)}
            self._keys   = list(self._raw.keys())
            self._loaded = True
            logger.debug("CapClassifier loaded %d stocks from %s", len(self._keys), self._path)
        except FileNotFoundError:
            logger.warning(
                "nifty_caplist.json not found at %s. "
                "Run: python manage.py update_nifty_caplist", self._path
            )
        except Exception as exc:
            logger.error("Failed to load nifty_caplist.json: %s", exc)

    def reload(self) -> None:
        """Hot-reload the cap list after update_nifty_caplist runs."""
        self._raw    = {}
        self._keys   = []
        self._loaded = False
        self._load()

    def classify(self, security_name: str) -> str:
        """
        Return SEBI cap category: 'large' | 'mid' | 'small'.
        'small' is the fallback (SEBI residual rule).
        """
        if not self._loaded or not security_name:
            return 'small'

        try:
            from rapidfuzz import process as rfprocess, fuzz
        except ImportError:
            logger.error("rapidfuzz not installed. Run: pip install rapidfuzz")
            return 'small'

        norm = _normalize(security_name)
        if not norm or len(norm) < 3:
            return 'small'

        # Exact match (fast path)
        if norm in self._raw:
            return self._raw[norm]

        # Fuzzy match using token_sort_ratio with strict score cutoff
        result = rfprocess.extractOne(
            norm, self._keys, scorer=fuzz.token_sort_ratio, score_cutoff=90
        )
        if result is not None:
            matched_key, score, _ = result
            if len(matched_key) >= 4 and len(norm) >= 4:
                category = self._raw[matched_key]
                logger.debug(
                    "Cap classify: '%s' -> '%s' -> %s  (score=%s)",
                    security_name, matched_key, category, score,
                )
                return category

        return 'small'

    def classify_portfolio(
        self,
        holdings: list[dict],
        equity_types: set | None = None,
    ) -> dict:
        """
        Compute Large/Mid/Small/Other cap breakdown for a list of holdings.

        Args:
            holdings:     List of dicts with keys:
                            'security_name' (str)   -- required
                            'weight_pct'    (float) -- % weight in portfolio
                            'holding_type'  (str)   -- 'equity'/'debt'/'cash'/'other'
            equity_types: holding_type strings to treat as equity.
                          Defaults to {'equity', 'stock', 'eq', ''}.

        Returns:
            Dict: large_pct, mid_pct, small_pct, other_pct,
                  equity_weight, classified_count, unclassified_count
        """
        if equity_types is None:
            equity_types = {'equity', 'stock', 'eq', ''}

        equity_holdings = [
            h for h in holdings
            if str(h.get('holding_type', 'equity')).lower() in equity_types
        ]

        total_equity_weight = sum(
            float(h.get('weight_pct', 0) or 0) for h in equity_holdings
        )

        caps: dict[str, float] = {'large': 0.0, 'mid': 0.0, 'small': 0.0}
        classified   = 0
        unclassified = 0

        for h in equity_holdings:
            name   = str(h.get('security_name', '') or '')
            weight = float(h.get('weight_pct', 0) or 0)
            if not name or weight <= 0:
                continue
            cat = self.classify(name)
            caps[cat] += weight
            if cat in ('large', 'mid'):
                classified += 1
            else:
                # 'small' includes unmatched names (SEBI residual rule)
                unclassified += 1

        total_classified = sum(caps.values())
        return {
            'large_pct':          round(caps['large'], 4),
            'mid_pct':            round(caps['mid'],   4),
            'small_pct':          round(caps['small'], 4),
            'other_pct':          0.0,
            'equity_weight':      round(total_equity_weight, 4),
            'classified_count':   classified,
            'unclassified_count': unclassified,
        }


# Module-level singleton (lazy-loaded)
_default_classifier: Optional[CapClassifier] = None


def get_classifier() -> CapClassifier:
    """Return the module-level singleton CapClassifier instance."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = CapClassifier()
    return _default_classifier
