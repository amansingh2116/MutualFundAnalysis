"""
apps/funds/services.py — On-Demand Data Orchestrator
=====================================================
This is the single entry point for getting fund data.
It ensures data exists in the DB before returning it,
fetching from external APIs transparently if needed.

Usage:
    from apps.funds.services import get_or_fetch_scheme, get_or_fetch_nav_history

All functions:
  - Return instantly if DB has fresh data
  - Fetch from APIs if missing/stale, save to DB, then return
  - Are safe to call from views (handle all exceptions)
"""
import logging
from datetime import date, timedelta
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('mfanalysis')

# ── Freshness thresholds ────────────────────────────────────────────────────
NAV_STALE_HOURS    = 20   # Re-fetch NAVs if older than this
META_STALE_DAYS    = 7    # Re-fetch captnemo metadata if older than this
AMFI_LIST_CACHE_KEY = 'amfi_scheme_list'
AMFI_LIST_TTL       = 6 * 3600   # 6 hours


# ── AMFI Scheme List (search backbone) ─────────────────────────────────────

def get_amfi_scheme_list() -> list[dict]:
    """
    Returns the full AMFI scheme list (14K+ schemes) as a list of dicts:
      [{'amfi_code': '120503', 'scheme_name': '...', 'amc_name': '...', 'nav': '...'}, ...]

    Cached in Django cache for 6 hours. Fetches from AMFI NAVAll.txt on cache miss.
    This is the backbone for fund search autocomplete.
    """
    cached = cache.get(AMFI_LIST_CACHE_KEY)
    if cached:
        return cached

    try:
        from adapters.amfi_adapter import AMFIAdapter
        adapter = AMFIAdapter()
        schemes = adapter.fetch_scheme_universe()
        from apps.core.utils import is_direct_scheme, is_growth_scheme, is_etf_scheme
        # Keep only the fields we need for search and filter for Direct Growth / ETFs
        slim = []
        for s in schemes:
            if not s.get('amfi_code'):
                continue
            name = s['scheme_name']
            if is_etf_scheme(name) or (is_direct_scheme(name) and is_growth_scheme(name)):
                slim.append({
                    'amfi_code':   s['amfi_code'],
                    'scheme_name': s['scheme_name'],
                    'amc_name':    s['amc_name'],
                    'nav':         s.get('nav', ''),
                    'scheme_type': s.get('scheme_type', ''),
                })
        cache.set(AMFI_LIST_CACHE_KEY, slim, AMFI_LIST_TTL)
        logger.info(f"Cached {len(slim)} schemes from AMFI NAVAll.txt")
        return slim
    except Exception as e:
        logger.error(f"Failed to fetch AMFI scheme list: {e}")
        return []


def search_amfi_cache(query: str, limit: int = 10) -> list[dict]:
    """
    Search the in-memory AMFI scheme list for matching fund names.
    Falls back to live mfapi.in search if cache unavailable.
    """
    query_lower = query.lower()
    schemes = get_amfi_scheme_list()

    # Score matches: name starts with query > name contains query > AMC matches
    starts = []
    contains = []
    amc_matches = []

    for s in schemes:
        name_lower = s['scheme_name'].lower()
        if name_lower.startswith(query_lower):
            starts.append(s)
        elif query_lower in name_lower:
            contains.append(s)
        elif query_lower in s.get('amc_name', '').lower():
            amc_matches.append(s)

    results = (starts + contains + amc_matches)[:limit]

    if not results:
        # Fallback: live mfapi.in search
        results = _search_mfapi_live(query, limit)

    return results


def _search_mfapi_live(query: str, limit: int = 10) -> list[dict]:
    """Fallback: search mfapi.in live search endpoint."""
    from adapters.amfi_adapter import AMFIAdapter
    try:
        adapter = AMFIAdapter()
        r = adapter._get_with_retry(
            f'https://api.mfapi.in/mf/search?q={query}',
            timeout=5,
            max_retries=2,
        )
        data = r.json()
        return [
            {
                'amfi_code':   str(item.get('schemeCode', '')),
                'scheme_name': item.get('schemeName', ''),
                'amc_name':    item.get('fundHouse', ''),
                'nav':         '',
            }
            for item in data[:limit]
        ]
    except Exception as e:
        logger.warning(f"mfapi.in live search failed for '{query}': {e}")
        return []


# ── Fund Scheme ─────────────────────────────────────────────────────────────

def get_or_fetch_scheme(amfi_code: str):
    """
    Get a Scheme from DB, fetching from mfapi.in if it doesn't exist.
    Returns a Scheme instance or None on complete failure.
    """
    from apps.funds.models import Scheme

    try:
        return Scheme.objects.get(amfi_code=amfi_code)
    except Scheme.DoesNotExist:
        pass

    logger.info(f"[{amfi_code}] Scheme not in DB — fetching from mfapi.in")
    return _fetch_and_create_scheme(amfi_code)


def _fetch_and_create_scheme(amfi_code: str):
    """Fetch scheme metadata from mfapi.in and create DB record."""
    from apps.funds.models import Scheme

    try:
        from adapters.amfi_adapter import AMFIAdapter
        adapter = AMFIAdapter()
        meta = adapter.fetch_scheme_meta(amfi_code)

        if not meta:
            logger.error(f"[{amfi_code}] Could not fetch metadata from mfapi.in")
            return None

        # Parse name to determine plan/direct
        scheme_name = meta.get('scheme_name', '')
        is_direct   = 'direct' in scheme_name.lower()
        plan        = 'IDCW' if any(x in scheme_name.upper() for x in ['IDCW', 'DIVIDEND']) else 'GROWTH'

        scheme, created = Scheme.objects.update_or_create(
            amfi_code=amfi_code,
            defaults={
                'scheme_name':     scheme_name,
                'fund_house':      meta.get('fund_house', ''),
                'scheme_type':     meta.get('scheme_type', 'Open Ended'),
                'scheme_category': meta.get('scheme_category', ''),
                'plan':            plan,
                'is_direct':       is_direct,
                'is_active':       True,
            }
        )
        action = 'Created' if created else 'Updated'
        logger.info(f"[{amfi_code}] {action} scheme: {scheme_name}")
        return scheme

    except Exception as e:
        logger.error(f"[{amfi_code}] Failed to create scheme: {e}")
        return None


# ── NAV History ─────────────────────────────────────────────────────────────

def get_or_fetch_nav_history(scheme) -> bool:
    """
    Ensure NAVHistory is populated and fresh for the given scheme.
    Returns True if data is available (existing or freshly fetched).
    """
    from apps.funds.models import NAVHistory

    latest = NAVHistory.objects.filter(scheme=scheme).order_by('-date').first()

    if latest:
        age_hours = (timezone.now().date() - latest.date).total_seconds() / 3600
        if age_hours < NAV_STALE_HOURS:
            return True   # Fresh enough
        # Stale — only fetch recent NAVs (incremental update)
        logger.info(f"[{scheme.amfi_code}] NAV stale ({latest.date}) — refreshing")

    # No data or stale → full fetch
    return _fetch_and_store_nav_history(scheme)


def _fetch_and_store_nav_history(scheme) -> bool:
    """Fetch full NAV history from mfapi.in and bulk-insert."""
    from apps.funds.models import NAVHistory
    from apps.core.utils import parse_amfi_date

    try:
        from adapters.amfi_adapter import AMFIAdapter
        adapter = AMFIAdapter()
        raw = adapter.fetch_nav_history(scheme.amfi_code)

        if not raw:
            # Try mftool fallback
            raw = adapter.fetch_nav_history_mftool(scheme.amfi_code)

        if not raw:
            logger.warning(f"[{scheme.amfi_code}] No NAV history available")
            return False

        # Build objects for bulk insert (skip existing dates)
        existing_dates = set(
            NAVHistory.objects.filter(scheme=scheme)
            .values_list('date', flat=True)
        )

        to_create = []
        for entry in raw:
            try:
                nav_date = parse_amfi_date(entry['date'])
                if nav_date and nav_date not in existing_dates:
                    to_create.append(NAVHistory(
                        scheme=scheme,
                        date=nav_date,
                        nav=float(entry['nav']),
                    ))
            except (ValueError, KeyError):
                continue

        if to_create:
            NAVHistory.objects.bulk_create(to_create, ignore_conflicts=True)
            # Update scheme's cached latest NAV
            newest = to_create[0]  # mfapi returns newest first
            scheme.nav_latest = newest.nav
            scheme.nav_date   = newest.date
            scheme.save(update_fields=['nav_latest', 'nav_date'])

        logger.info(f"[{scheme.amfi_code}] Stored {len(to_create)} NAV entries")
        return True

    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] NAV history fetch failed: {e}")
        return False


# ── Metadata (captnemo) ─────────────────────────────────────────────────────

def get_or_fetch_metadata(scheme) -> bool:
    """
    Ensure SchemeMeta is populated for the given scheme.
    Returns True if metadata is available.
    """
    from apps.funds.models import SchemeMeta

    try:
        meta = scheme.meta
        # Check freshness
        age_days = (timezone.now() - meta.last_fetched).days
        if age_days < META_STALE_DAYS:
            return True
        logger.info(f"[{scheme.amfi_code}] Metadata stale ({age_days}d) — refreshing")
    except SchemeMeta.DoesNotExist:
        logger.info(f"[{scheme.amfi_code}] No metadata — fetching from captnemo")

    return _fetch_and_store_metadata(scheme)


def _fetch_and_store_metadata(scheme) -> bool:
    """Fetch fund metadata using captnemo and mstarpy fallbacks, save to SchemeMeta."""
    from apps.funds.models import SchemeMeta
    from adapters.captnemo_adapter import CaptnemoAdapter
    from adapters.mstarpy_adapter import MstarpyAdapter

    meta_fields = {}
    
    # 1. Try Captnemo for AUM, Expense Ratio, Min Investment, Managers
    try:
        adapter = CaptnemoAdapter()
        fund_info = None
        if scheme.isin_growth:
            fund_info = adapter.fetch_fund_info(scheme.isin_growth)
        if not fund_info:
            fund_info = adapter.fetch_fund_info_by_amfi(scheme.amfi_code)

        if fund_info:
            meta_fields = adapter.extract_scheme_meta(fund_info)
        else:
            logger.warning(f"[{scheme.amfi_code}] captnemo returned no data, falling back")
    except Exception as e:
        logger.warning(f"[{scheme.amfi_code}] captnemo fetch failed: {e}")

    # 2. Use mstarpy for Ratings, Category, and Manager fallback
    try:
        mstar_adapter = MstarpyAdapter()
        if not scheme.morningstar_id:
            results = mstar_adapter.search_fund(scheme.scheme_name, page_size=1)
            if results and isinstance(results, list) and len(results) > 0:
                scheme.morningstar_id = results[0].get('SecId')
                scheme.save(update_fields=['morningstar_id'])
                
        if scheme.morningstar_id:
            tr = mstar_adapter.fetch_trailing_returns(scheme.morningstar_id)
            if tr and isinstance(tr, dict):
                meta_fields['ms_rating'] = tr.get('overallMorningstarRating')
                meta_fields['ms_category'] = tr.get('categoryName')
                # Morningstar provides manager names sometimes in trailing returns or information,
                # but we'll stick to rating/category for now as mapped in the notebook.
    except Exception as e:
        logger.warning(f"[{scheme.amfi_code}] mstarpy metadata enrich failed: {e}")

    if not meta_fields:
        logger.warning(f"[{scheme.amfi_code}] Could not fetch any metadata from any source")
        # Create an empty SchemeMeta so we don't keep failing UI checks
        SchemeMeta.objects.update_or_create(scheme=scheme, defaults={})
        return True

    try:
        # Update denormalized fields on Scheme itself
        if meta_fields.get('expense_ratio') is not None:
            scheme.expense_ratio = meta_fields['expense_ratio']
        if meta_fields.get('aum') is not None:
            scheme.aum_cr = meta_fields['aum']
        scheme.save(update_fields=['expense_ratio', 'aum_cr'])

        SchemeMeta.objects.update_or_create(
            scheme=scheme,
            defaults=meta_fields,
        )
        logger.info(f"[{scheme.amfi_code}] Metadata saved from available sources")
        return True

    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] Metadata save failed: {e}")
        return False


# ── Full Fund Prepare (called by FundDetailView) ────────────────────────────

def prepare_fund_for_display(amfi_code: str) -> tuple:
    """
    Orchestrates all data fetching for a fund detail page.
    Returns (scheme, has_nav, has_meta) tuple.
    Guaranteed not to raise — all errors are logged.
    """
    scheme = get_or_fetch_scheme(amfi_code)
    if not scheme:
        return None, False, False

    has_nav  = get_or_fetch_nav_history(scheme)
    has_meta = get_or_fetch_metadata(scheme)

    # Compute analytics if we have NAV data
    if has_nav:
        _ensure_analytics(scheme)

    _ensure_holdings(scheme)

    return scheme, has_nav, has_meta


def _ensure_analytics(scheme) -> None:
    """Compute trailing returns and risk metrics if not already done today."""
    from apps.analytics.models import TrailingReturn
    from datetime import date

    today = date.today()
    already_computed = TrailingReturn.objects.filter(
        scheme=scheme,
        as_of=today,
    ).exists()

    if already_computed:
        return

    try:
        from apps.analytics.engine import compute_all_metrics
        compute_all_metrics(scheme)
        logger.info(f"[{scheme.amfi_code}] Analytics computed")
    except Exception as e:
        logger.warning(f"[{scheme.amfi_code}] Analytics computation failed: {e}")


def _ensure_holdings(scheme) -> None:
    """Fetch holdings and sector allocation from Morningstar if missing."""
    from apps.holdings.models import Holding, SectorAllocation
    from adapters.mstarpy_adapter import MstarpyAdapter
    from datetime import date
    from apps.funds.models import SchemeMeta

    today = date.today()
    as_of_month = date(today.year, today.month, 1)

    # Check if already ingested for this month
    if Holding.objects.filter(scheme=scheme, as_of_month=as_of_month).exists():
        return

    adapter = MstarpyAdapter()
    
    # 1. Resolve Morningstar ID if missing
    if not scheme.morningstar_id:
        results = adapter.search_fund(scheme.scheme_name, page_size=1)
        if results and isinstance(results, list) and len(results) > 0:
            scheme.morningstar_id = results[0].get('SecId')
            scheme.save(update_fields=['morningstar_id'])

    if not scheme.morningstar_id:
        logger.warning(f"[{scheme.amfi_code}] Could not find Morningstar ID for holdings")
        return

    # 2. Fetch Holdings
    holdings_df = adapter.fetch_holdings(scheme.morningstar_id)
    if holdings_df is not None and not holdings_df.empty:
        to_create = []
        for _, row in holdings_df.iterrows():
            to_create.append(Holding(
                scheme=scheme,
                as_of_month=as_of_month,
                security_name=str(row.get('securityName', 'Unknown')),
                weight_pct=float(row.get('weighting', 0)),
                sector=str(row.get('sector', '')),
                isin=str(row.get('isin', '')),
                source='mstarpy'
            ))
        if to_create:
            Holding.objects.bulk_create(to_create, ignore_conflicts=True)
            logger.info(f"[{scheme.amfi_code}] Ingested {len(to_create)} holdings")

    # 3. Fetch Sector Allocation
    sector_data = adapter.fetch_sector_allocation(scheme.morningstar_id)
    if sector_data and isinstance(sector_data, dict) and 'EQUITY' in sector_data:
        portfolio = sector_data['EQUITY'].get('fundPortfolio', {})
        portfolio.pop('portfolioDate', None)
        
        s_create = []
        for sec, weight in portfolio.items():
            if isinstance(weight, (int, float)) and weight > 0:
                s_create.append(SectorAllocation(
                    scheme=scheme,
                    as_of_month=as_of_month,
                    sector=sec.replace('_', ' ').title(),
                    weight_pct=float(weight),
                    source='mstarpy'
                ))
        if s_create:
            SectorAllocation.objects.bulk_create(s_create, ignore_conflicts=True)
            logger.info(f"[{scheme.amfi_code}] Ingested {len(s_create)} sectors")

    # Meta enrichment is now handled in _fetch_and_store_metadata
