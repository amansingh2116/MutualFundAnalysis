"""
Management command: ingest_holdings (FULL IMPLEMENTATION)

Fetches fund portfolio holdings, sector allocation, and market cap breakdown
for all active direct growth schemes and saves them to the DB for 3 months of
point-in-time portfolio evolution tracking.

Strategy (same as runtime.py / fund detail page):
  1. Morningstar REST API — Full holdings + sectors via plain HTTP using the
     fund's morningstar_id (SecId starting with F0 for funds, 0P for ETFs).
     If morningstar_id is missing, auto-resolves via ISIN → SecId lookup
     (no browser/Selenium needed). Updates Scheme.morningstar_id in the DB.
  2. finapi (finapi.upvaly.com) — Full holdings + sectors for funds where the
     finapi portfolio endpoint returns data. Fallback when Morningstar fails.
  3. yahooquery FALLBACK — Top-10 holdings + full sector data for ETFs or
     funds when both above fail. Resolved tickers are persisted to
     Scheme.yahoo_ticker so CI re-runs skip re-resolution.
  4. CapClassifier — Maps equity holdings → Large/Mid/Small cap via rapidfuzz
     fuzzy matching against data/nifty_caplist.json (runs after any source).

Note: mstarpy (Selenium/Chrome browser library) was removed. The Morningstar
data is now fetched directly from the REST API (no browser needed).

Key features:
  - Resume support: checkpoints progress to a JSON file, skips already-done
  - Rate limiting: configurable delay between calls; exponential backoff on 429
  - Batch transactions: DB writes in batches of 50 for CockroachDB compatibility
  - Non-equity handling: Debt, cash, commodity instruments stored with their type
  - Idempotent: update_or_create safe to re-run
  - No browser/Selenium required — pure HTTP fetches only
  - ETF support: morningstar_id starting with 0P works same as F0

Usage:
    python manage.py ingest_holdings
    python manage.py ingest_holdings --date 2025-07-01    # specific month
    python manage.py ingest_holdings --limit 10           # test on 10 funds
    python manage.py ingest_holdings --amfi 120503        # single fund
    python manage.py ingest_holdings --resume             # skip already-done funds
    python manage.py ingest_holdings --source finapi      # finapi only
    python manage.py ingest_holdings --source yahoo       # yahooquery only
    python manage.py ingest_holdings --force              # overwrite existing data
    python manage.py ingest_holdings --delay 1.0          # slower (be polite)
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation

import requests

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.funds.models import Scheme
from apps.holdings.models import Holding, SectorAllocation, MarketCapAllocation

logger = logging.getLogger('mfanalysis')

# Management commands always run from the project root (where manage.py lives)
_CHECKPOINT_PATH = os.path.join(os.getcwd(), '.cache', 'ingest_holdings_checkpoint.json')

# finapi rate-limit retry settings
_FINAPI_MAX_RETRIES = 3
_FINAPI_BACKOFF_BASE = 5.0   # seconds — first retry waits 5s, next 10s, then 20s

_SECID_MAP_PATH = os.path.join(os.getcwd(), 'data', 'morningstar_secids.json')


def _load_secid_map() -> dict[str, str]:
    """Load precomputed ISIN -> Morningstar SecId mapping (data/morningstar_secids.json)."""
    if os.path.exists(_SECID_MAP_PATH):
        try:
            with open(_SECID_MAP_PATH, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning('Failed to load morningstar_secids.json: %s', exc)
    return {}


def _to_decimal(value, default=None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return default
    try:
        s = str(value).replace(',', '').strip()
        if not s or s.lower() in ('nan', 'none', 'null', 'inf', '-inf'):
            return default
        d = Decimal(s)
        if d.is_nan() or d.is_infinite():
            return default
        return d
    except (InvalidOperation, ValueError, TypeError):
        return default


def _save_checkpoint(data: dict) -> None:
    os.makedirs(os.path.dirname(_CHECKPOINT_PATH), exist_ok=True)
    with open(_CHECKPOINT_PATH, 'w') as fh:
        json.dump(data, fh)


def _load_checkpoint() -> dict:
    try:
        with open(_CHECKPOINT_PATH, 'r') as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class Command(BaseCommand):
    help = (
        'Ingest fund portfolio holdings + sector + cap-wise data '
        '(morningstar REST first, finapi second, yahooquery fallback). '
        'Run monthly. No browser required.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default=None,
                            help='Snapshot month YYYY-MM-01 (default: current month)')
        parser.add_argument('--limit', type=int, default=None,
                            help='Max number of schemes to process')
        parser.add_argument('--amfi', type=str, default=None,
                            help='Process a single AMFI code only')
        parser.add_argument('--force', action='store_true',
                            help='Re-fetch even if data exists for this month')
        parser.add_argument('--resume', action='store_true',
                            help='Skip AMFI codes already in checkpoint file')
        parser.add_argument('--source', choices=['auto', 'morningstar', 'finapi', 'yahoo'],
                            default='auto',
                            help='Data source: auto (morningstar→finapi→yahoo), '
                                 'morningstar (requires morningstar_id), finapi, yahoo')
        parser.add_argument('--delay', type=float, default=0.5,
                            help='Base seconds between API calls (default 0.5)')
        parser.add_argument('--batch-size', type=int, default=50,
                            help='DB write batch size (default 50)')

    def handle(self, *args, **options):
        # ── Date ────────────────────────────────────────────────────────────────
        if options['date']:
            as_of_month = date.fromisoformat(options['date'])
        else:
            today       = timezone.localdate()
            as_of_month = date(today.year, today.month, 1)

        limit      = options['limit']
        amfi_only  = options['amfi']
        force      = options['force']
        resume     = options['resume']
        source     = options['source']
        delay      = options['delay']
        batch_size = options['batch_size']

        self.stdout.write(
            self.style.NOTICE(f'=== Holdings Ingestion | {as_of_month} | source={source} ===')
        )

        # ── Load resume checkpoint ───────────────────────────────────────────────
        checkpoint: dict = _load_checkpoint() if resume else {}
        done_amfis: set  = set(checkpoint.get('done', []))
        if resume and done_amfis:
            self.stdout.write(f'Resuming: {len(done_amfis)} schemes already done.')

        # ── Load CapClassifier ───────────────────────────────────────────────────
        try:
            from apps.holdings.cap_classifier import get_classifier
            clf = get_classifier()
            self.stdout.write(
                f'CapClassifier ready: {len(clf._keys)} stocks in cap list.'
            )
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f'CapClassifier unavailable: {exc}. '
                                   'Run: python manage.py update_nifty_caplist')
            )
            clf = None

        # ── Scheme queryset ──────────────────────────────────────────────────────
        from django.db.models import Q
        qs = Scheme.objects.filter(
            Q(is_direct=True, plan='GROWTH') | Q(is_etf=True),
            is_active=True,
        ).order_by('amfi_code')

        if amfi_only:
            qs = qs.filter(amfi_code=amfi_only)
        if limit:
            qs = qs[:limit]

        # ── Load SecId mapping ───────────────────────────────────────────────────
        secid_map = _load_secid_map()
        if secid_map:
            self.stdout.write(f'Loaded {len(secid_map)} SecId mappings from morningstar_secids.json.')

        total   = qs.count()
        success = 0
        failed  = 0
        skipped = 0

        self.stdout.write(f'Processing {total} schemes ...')

        for idx, scheme in enumerate(qs.iterator(chunk_size=100), start=1):
            amfi = scheme.amfi_code

            # ── Skip if resumed ───────────────────────────────────────────────
            if resume and amfi in done_amfis:
                skipped += 1
                continue

            # ── Skip if data exists and not forced ───────────────────────────
            if not force:
                if Holding.objects.filter(scheme=scheme, as_of_month=as_of_month).exists():
                    logger.debug('[%s] Holdings exist for %s. Skipping.', amfi, as_of_month)
                    skipped += 1
                    done_amfis.add(amfi)
                    continue

            # ── Fetch portfolio data ──────────────────────────────────────────
            holdings_data   = None
            sector_data     = None
            allocation_data = None
            data_source     = 'none'

            use_morningstar = source in ('auto', 'morningstar')
            use_finapi      = source in ('auto', 'finapi')
            use_yahoo       = source in ('auto', 'yahoo')

            # 1) Morningstar REST API (plain HTTP, same as fund detail page)
            #    Accepts both F0xxxx (fund) and 0Pxxxx (ETF) SecIds.
            #    If morningstar_id is missing, checks static mapping or auto-resolves via ISIN lookup.
            if use_morningstar:
                # Auto-populate morningstar_id if missing
                if not scheme.morningstar_id and scheme.isin_growth:
                    isin = scheme.isin_growth.strip().upper()
                    if isin in secid_map:
                        scheme.morningstar_id = secid_map[isin]
                        try:
                            scheme.save(update_fields=['morningstar_id'])
                        except Exception:
                            pass
                    else:
                        try:
                            sec_id = self._resolve_morningstar_id(scheme, delay)
                            if sec_id:
                                scheme.morningstar_id = sec_id
                                scheme.save(update_fields=['morningstar_id'])
                                logger.info('[%s] Resolved morningstar_id=%s via ISIN', amfi, sec_id)
                        except Exception as exc:
                            logger.debug('[%s] morningstar_id auto-resolve failed: %s', amfi, exc)

                if scheme.morningstar_id:
                    try:
                        hd, sd, ad = self._fetch_morningstar(scheme, delay)
                        if hd is not None:
                            holdings_data   = hd
                            sector_data     = sd
                            allocation_data = ad
                            data_source     = 'morningstar'
                    except Exception as exc:
                        logger.warning('[%s] morningstar fetch failed: %s', amfi, exc)

            # 2) finapi (plain HTTP, no browser) — fallback
            if holdings_data is None and use_finapi:
                try:
                    hd, sd, ad = self._fetch_finapi(scheme, delay)
                    if hd is not None:
                        holdings_data   = hd
                        sector_data     = sd
                        allocation_data = ad
                        data_source     = 'finapi'
                except Exception as exc:
                    logger.warning('[%s] finapi fetch failed: %s', amfi, exc)

            # 3) yahooquery — fallback when both above return nothing
            if holdings_data is None and use_yahoo:
                try:
                    hd, sd, ad = self._fetch_yahoo(scheme, delay)
                    if hd is not None:
                        holdings_data   = hd
                        sector_data     = sd
                        allocation_data = ad
                        data_source     = 'yahoo'
                except Exception as exc:
                    logger.warning('[%s] yahooquery fetch failed: %s', amfi, exc)


            if holdings_data is None:
                logger.info('[%s] No portfolio data available.', amfi)
                failed += 1
                done_amfis.add(amfi)
                continue

            # ── Classify cap breakdown ────────────────────────────────────────
            cap_result = None
            if clf and holdings_data:
                try:
                    cap_result = clf.classify_portfolio(holdings_data)
                except Exception as exc:
                    logger.warning('[%s] Cap classification failed: %s', amfi, exc)

            # ── Persist to DB ─────────────────────────────────────────────────
            try:
                self._save_holdings(
                    scheme, as_of_month, holdings_data, sector_data,
                    allocation_data, cap_result, data_source, batch_size
                )
                success += 1
                done_amfis.add(amfi)
                logger.info(
                    '[%s] Ingested %d holdings, %d sectors | source=%s',
                    amfi, len(holdings_data or []), len(sector_data or []), data_source
                )
            except Exception as exc:
                logger.error('[%s] DB save failed: %s', amfi, exc)
                failed += 1

            # ── Checkpoint every 50 schemes ───────────────────────────────────
            if idx % 50 == 0:
                _save_checkpoint({'done': list(done_amfis), 'as_of_month': str(as_of_month)})
                self.stdout.write(
                    f'  Progress: {idx}/{total} | '
                    f'Success={success} Failed={failed} Skipped={skipped}'
                )

        # ── Final checkpoint save ────────────────────────────────────────────────
        _save_checkpoint({'done': list(done_amfis), 'as_of_month': str(as_of_month)})

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Holdings Ingestion Complete ===\n'
            f'Month: {as_of_month} | Total: {total}\n'
            f'Success: {success} | Failed: {failed} | Skipped: {skipped}'
        ))

    # ── Morningstar REST fetch (same API as runtime.py fund detail page) ──────────

    def _resolve_morningstar_id(self, scheme: Scheme, delay: float) -> str:
        """Resolve Scheme.morningstar_id via ISIN → SecId lookup (pure HTTP, no browser).

        Tries two pure-HTTP strategies in order:
         1. Morningstar holdings API with ISIN as path parameter — the API
            accepts ISINs and returns a `secId` in the response body when the
            fund is indexed by Morningstar.
         2. Morningstar token/search by fund name — used for newly-issued ISINs
            not yet indexed by the holdings endpoint.

        Returns the SecId string (e.g. 'F00000SC5Y' or '0P0001IX52') or ''.
        Note: Resolved SecIds are persisted to Scheme.morningstar_id so CI
        re-runs skip re-resolution entirely.
        """
        isin = str(scheme.isin_growth or '').strip()
        if not isin:
            return ''

        amfi = scheme.amfi_code
        api_key = 'lstzFDEOhfFNMLikKa0am9mgEKLBl49T'
        headers = {
            'apikey':     api_key,
            'Accept':     'application/json, text/plain, */*',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        # Strategy 1: Morningstar holdings API with ISIN as path param.
        # The API accepts ISINs and sometimes returns a `secId` in the response body.
        try:
            h_url = (f'https://api-global.morningstar.com/sal-service/v1/fund'
                     f'/portfolio/holding/v2/{isin}/data')
            h_resp = requests.get(
                h_url, headers=headers,
                params={'clientId': 'MDC', 'version': '4.71.0',
                        'premiumNum': 10000, 'freeNum': 10000},
                timeout=10,
            )
            if h_resp.status_code == 200:
                body   = h_resp.json()
                sec_id = str(body.get('secId') or body.get('masterPortfolioId') or '').strip()
                if sec_id:
                    logger.debug('[%s] Mstar holdings returned secId=%s for ISIN=%s',
                                 amfi, sec_id, isin)
                    return sec_id
        except Exception as exc:
            logger.debug('[%s] Mstar ISIN path-param resolve error: %s', amfi, exc)

        time.sleep(delay * 0.3)

        # Strategy 2: Name-based token search — used when the ISIN holdings endpoint
        # returns non-200 (e.g. newly-issued ISINs not yet indexed by Morningstar).
        try:
            name = str(scheme.scheme_name or '').strip()
            # Strip common suffixes for a cleaner search term
            for suffix in [' - Direct Plan Growth Option', ' Direct Growth', ' - Direct Plan',
                           ' Direct Plan Growth', '- Direct Plan Growth', ' Growth Option',
                           ' - Growth Option']:
                name = name.replace(suffix, '')
            search_term = ' '.join(name.split()[:6]).strip()
            if search_term:
                url = 'https://api-global.morningstar.com/sal-service/v1/fund/token/search'
                resp = requests.get(
                    url, headers=headers,
                    params={'term': search_term, 'limit': 5, 'clientId': 'MDC',
                            'currency': 'INR', 'universeIds': 'FOIND$$ALL|ETFIND$$ALL'},
                    timeout=12,
                )
                time.sleep(delay * 0.3)
                if resp.status_code == 200:
                    results = resp.json()
                    if isinstance(results, dict):
                        results = results.get('hits') or results.get('results') or []
                    for item in results:
                        sec_id = str(
                            item.get('SecId') or item.get('secId') or item.get('id') or ''
                        ).strip()
                        item_isin = str(item.get('Isin') or item.get('isin') or '').strip().upper()
                        # Must match ISIN exactly when present
                        if sec_id and (item_isin == isin.upper() or not item_isin):
                            logger.debug('[%s] Mstar name-search resolved SecId=%s (ISIN=%s)',
                                         amfi, sec_id, isin)
                            return sec_id
        except Exception as exc:
            logger.debug('[%s] Mstar name-search resolve error: %s', amfi, exc)

        return ''

    def _fetch_morningstar(self, scheme: Scheme, delay: float):
        """Fetch full holdings + sectors from Morningstar REST API.

        Uses the same api-global.morningstar.com endpoints as runtime.py's
        fetch_mstarpy_payload(). Accepts all Morningstar SecId formats:
        F0xxxx (mutual funds), 0Pxxxx (ETFs), FOUSAxxxxx (US-listed), F0GBRxxxx (UK-listed).

        Returns (holdings_list, sector_list, alloc_dict) or (None, None, None).
        """
        sec_id = str(scheme.morningstar_id or '').strip()
        # The Morningstar REST API accepts all SecId formats:
        # F0xxxx (funds), 0Pxxxx (ETFs), FOUSAxxxxx (older US-listed), F0GBRxxxx (UK-listed), etc.
        # Do NOT filter by prefix — let the HTTP response determine validity.
        if not sec_id:
            return None, None, None

        amfi = scheme.amfi_code
        api_key = 'lstzFDEOhfFNMLikKa0am9mgEKLBl49T'
        headers = {
            'apikey':       api_key,
            'Accept':       'application/json, text/plain, */*',
            'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        try:
            # ── 1. Holdings ───────────────────────────────────────────────────
            h_url = (f'https://api-global.morningstar.com/sal-service/v1/fund'
                     f'/portfolio/holding/v2/{sec_id}/data')
            h_resp = requests.get(
                h_url, headers=headers,
                params={'clientId': 'MDC', 'version': '4.71.0',
                        'premiumNum': 10000, 'freeNum': 10000},
                timeout=15,
            )
            time.sleep(delay)

            if h_resp.status_code == 429:
                wait = _FINAPI_BACKOFF_BASE
                logger.warning('[%s] morningstar 429. Waiting %.0fs', amfi, wait)
                time.sleep(wait)
                h_resp = requests.get(h_url, headers=headers,
                                      params={'clientId': 'MDC', 'version': '4.71.0',
                                              'premiumNum': 10000, 'freeNum': 10000},
                                      timeout=15)

            if h_resp.status_code != 200:
                logger.debug('[%s] morningstar holdings HTTP %s', amfi, h_resp.status_code)
                return None, None, None

            h_json = h_resp.json()
            if not isinstance(h_json, dict):
                return None, None, None

            eq_list = h_json.get('equityHoldingPage', {}).get('holdingList', []) or []
            bd_list = h_json.get('boldHoldingPage', {}).get('holdingList', []) or []
            ot_list = h_json.get('otherHoldingPage', {}).get('holdingList', []) or []
            all_raw = eq_list + bd_list + ot_list
            if not all_raw:
                return None, None, None

            holdings_list = []
            for row in all_raw:
                name   = str(row.get('securityName') or '').strip()
                weight = _to_decimal(row.get('weighting'))
                if not name or weight is None:
                    continue
                sector = str(row.get('sector') or row.get('superSectorName') or '').strip()
                isin   = str(row.get('isin') or '')
                ticker = str(row.get('ticker') or '')
                # Morningstar holdingType values: 'Equity', 'Bond', 'Other' (capitalized)
                # holdingTypeId further classifies: GS/B=bond, CP/CD=cash, CR/CA=cash,
                #   FO=fund-of-fund (treat as equity/other), DD=commodity (treat as other)
                htype_raw = str(row.get('holdingType') or '').lower()
                htype_id  = str(row.get('holdingTypeId') or '').upper()
                if htype_raw == 'bond':
                    htype = 'debt'
                elif htype_raw == 'equity':
                    htype = 'equity'
                elif htype_id in ('GS', 'B', 'NCD'):
                    htype = 'debt'
                elif htype_id in ('CP', 'CD', 'CR', 'CA', 'TB'):
                    htype = 'cash'
                else:
                    htype = _finapi_holding_type(name, sector)
                holdings_list.append({
                    'security_name': name,
                    'weight_pct':    weight,
                    'holding_type':  htype,
                    'isin':          isin[:15],
                    'ticker':        ticker[:20],
                    'sector':        sector[:100],
                    'forward_pe':    _to_decimal(row.get('forwardPERatio')),
                    'market_value':  _to_decimal(row.get('marketValue')),
                })

            if not holdings_list:
                return None, None, None

            # ── 2. Sectors (best-effort) ──────────────────────────────────────
            sector_list = []
            try:
                s_url = (f'https://api-global.morningstar.com/sal-service/v1/fund'
                         f'/portfolio/v2/sector/{sec_id}/data')
                s_resp = requests.get(s_url, headers=headers,
                                      params={'clientId': 'MDC', 'version': '4.71.0'},
                                      timeout=10)
                time.sleep(delay * 0.5)
                if s_resp.status_code == 200:
                    s_json = s_resp.json() or {}
                    # Morningstar sector response: nested under EQUITY → fundPortfolio
                    eq_data = (s_json.get('EQUITY') or {}).get('fundPortfolio') or {}
                    _SECTOR_MAP = {
                        'basicMaterials': 'Basic Materials',
                        'consumerCyclical': 'Consumer Cyclical',
                        'financialServices': 'Financial Services',
                        'realEstate': 'Real Estate',
                        'communicationServices': 'Communication Services',
                        'energy': 'Energy',
                        'industrials': 'Industrials',
                        'technology': 'Technology',
                        'consumerDefensive': 'Consumer Defensive',
                        'healthcare': 'Healthcare',
                        'utilities': 'Utilities',
                    }
                    for raw_key, raw_val in eq_data.items():
                        if raw_key in ('portfolioDate', 'assetType'):
                            continue
                        w = _to_decimal(raw_val)
                        if w and w > 0:
                            sector_list.append({
                                'sector':     _SECTOR_MAP.get(raw_key, raw_key.replace('_', ' ').title()),
                                'weight_pct': w,
                            })
            except Exception as exc:
                logger.debug('[%s] morningstar sectors error: %s', amfi, exc)

            # If sector endpoint returned empty, synthesize sectors from holdings_list
            if not sector_list and holdings_list:
                sec_totals = {}
                for h in holdings_list:
                    sec = (h.get('sector') or '').strip()
                    w = _to_decimal(h.get('weight_pct'))
                    if sec and w and w > 0:
                        sec_totals[sec] = sec_totals.get(sec, Decimal('0')) + w
                if sec_totals:
                    sector_list = [
                        {'sector': k, 'weight_pct': v}
                        for k, v in sorted(sec_totals.items(), key=lambda x: x[1], reverse=True)
                    ]

            # ── 3. Asset Allocation (best-effort) ─────────────────────────────
            alloc: dict = {'equity_pct': None, 'debt_pct': None, 'cash_pct': None}
            try:
                a_url = (f'https://api-global.morningstar.com/sal-service/v1/fund'
                         f'/process/asset/{sec_id}/data')
                a_resp = requests.get(a_url, headers=headers,
                                      params={'clientId': 'MDC', 'version': '4.71.0'},
                                      timeout=10)
                time.sleep(delay * 0.5)
                if a_resp.status_code == 200:
                    a_json = a_resp.json() or {}
                    alloc_map = (a_json.get('allocationMap') or {})
                    for key, field in [('AssetAllocStock', 'equity_pct'),
                                       ('INDAssetAllocStock', 'equity_pct'),
                                       ('AssetAllocBond',  'debt_pct'),
                                       ('INDAssetAllocBond', 'debt_pct'),
                                       ('AssetAllocCash',  'cash_pct'),
                                       ('INDAssetAllocCash', 'cash_pct')]:
                        item = alloc_map.get(key)
                        if isinstance(item, dict) and alloc[field] is None:
                            alloc[field] = _to_decimal(item.get('netAllocation'))
            except Exception as exc:
                logger.debug('[%s] morningstar asset alloc error: %s', amfi, exc)

            return holdings_list, sector_list, alloc

        except Exception as exc:
            logger.warning('[%s] morningstar REST fetch error: %s', amfi, exc)
            return None, None, None

    # ── finapi fetch ─────────────────────────────────────────────────────────────

    def _fetch_finapi(self, scheme: Scheme, delay: float):
        """Fetch full holdings + sectors from finapi.upvaly.com by AMFI code.

        Plain HTTP — no browser, no special ID. Works for all active MF schemes.
        Retries up to 3 times on 429 (rate limited) with exponential backoff.

        Returns (holdings_list, sector_list, alloc_dict) or (None, None, None).
        """

        amfi = str(scheme.amfi_code or '').strip()
        if not amfi:
            return None, None, None

        response = None
        for attempt in range(1, _FINAPI_MAX_RETRIES + 1):
            try:
                response = requests.get(
                    f'https://finapi.upvaly.com/api/mf/scheme-code/{amfi}',
                    params={'fields': 'schemeCode,schemeName,latestNavDate,portfolio,holdings,sectors'},
                    headers={
                        'Accept': 'application/json',
                        'User-Agent': 'MFAnalysis/1.0 (+https://github.com)',
                    },
                    timeout=20,
                )

                if response.status_code == 429:
                    wait = _FINAPI_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning('[%s] finapi 429 rate-limited. Waiting %.0fs (attempt %d/%d)',
                                   amfi, wait, attempt, _FINAPI_MAX_RETRIES)
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                break  # success

            except requests.exceptions.HTTPError as exc:
                if attempt < _FINAPI_MAX_RETRIES:
                    wait = _FINAPI_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning('[%s] finapi HTTP %s, retrying in %.0fs',
                                   amfi, exc.response.status_code if exc.response else '?', wait)
                    time.sleep(wait)
                else:
                    logger.warning('[%s] finapi HTTP error after %d attempts: %s',
                                   amfi, _FINAPI_MAX_RETRIES, exc)
                    return None, None, None
            except Exception as exc:
                logger.warning('[%s] finapi request error: %s', amfi, exc)
                return None, None, None
            finally:
                time.sleep(delay)

        if response is None:
            return None, None, None

        try:
            payload = response.json()
        except Exception:
            return None, None, None

        data = payload.get('data') if isinstance(payload, dict) else payload
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return None, None, None

        # ── Holdings ─────────────────────────────────────────────────────────
        holdings_list = []
        for row in (data.get('holdings') or []):
            if not isinstance(row, dict):
                continue
            name   = str(row.get('name') or row.get('securityName') or row.get('holdingName') or '').strip()
            weight = _to_decimal(row.get('weightage') or row.get('weight') or row.get('holdingPercent'))
            if not name or weight is None:
                continue
            sector = str(row.get('sector') or row.get('industry') or '').strip()
            isin   = str(row.get('isin') or row.get('isinCode') or '')
            ticker = str(row.get('ticker') or row.get('symbol') or '')
            htype  = _finapi_holding_type(name, sector)
            holdings_list.append({
                'security_name': name,
                'weight_pct':    weight,
                'holding_type':  htype,
                'isin':          isin[:15],
                'ticker':        ticker[:20],
                'sector':        sector[:100],
                'forward_pe':    _to_decimal(row.get('forwardPE') or row.get('forward_pe') or row.get('pe')),
                'market_value':  None,
            })

        if not holdings_list:
            return None, None, None

        # ── Sector allocation ─────────────────────────────────────────────────
        sector_list = []
        for row in (data.get('sectors') or []):
            if not isinstance(row, dict):
                continue
            name   = str(row.get('sector') or row.get('name') or '').strip()
            weight = _to_decimal(row.get('weightage') or row.get('weight'))
            if name and weight is not None:
                if weight <= 1:
                    weight = weight * 100
                sector_list.append({'sector': name, 'weight_pct': weight})

        # ── Asset allocation & Cap Weightage ──────────────────────────────────
        alloc = {
            'equity_pct': None, 'debt_pct': None, 'cash_pct': None,
            'large_pct': None, 'mid_pct': None, 'small_pct': None, 'other_pct': None,
        }
        portfolio = data.get('portfolio') if isinstance(data.get('portfolio'), dict) else {}
        asset_alloc_raw = portfolio.get('assetAllocation') or {}
        label_map = {
            'equity': 'equity_pct', 'stock': 'equity_pct',
            'debt':   'debt_pct',   'bond':  'debt_pct', 'fixed': 'debt_pct',
            'cash':   'cash_pct',   'money': 'cash_pct',
        }
        for key, val in asset_alloc_raw.items():
            pct = _to_decimal(val)
            if pct is None:
                continue
            if pct <= 1:
                pct = pct * 100
            lower = str(key).lower()
            for marker, field in label_map.items():
                if marker in lower:
                    alloc[field] = pct
                    break

        # Market Cap weightage from SEBI disclosure (if provided by finapi)
        mcap_raw = portfolio.get('marketCapWeightage') or {}
        if isinstance(mcap_raw, dict):
            for k, f in [('largeCap', 'large_pct'), ('midCap', 'mid_pct'),
                          ('smallCap', 'small_pct'), ('others', 'other_pct')]:
                v = _to_decimal(mcap_raw.get(k))
                if v is not None:
                    if 0 < v <= 1:
                        v = v * 100
                    alloc[f] = v

        return holdings_list, sector_list, alloc

    # ── yahooquery fetch ─────────────────────────────────────────────────────────

    def _fetch_yahoo(self, scheme: Scheme, delay: float):
        """Fetch top-10 holdings + sector weights from yahooquery.

        Used as fallback when finapi returns no data (e.g. for ETFs or
        very new funds). Note: yahooquery only returns top-10 holdings.
        """
        try:
            from yahooquery import Ticker
        except ImportError:
            return None, None, None

        ticker_sym = scheme.yahoo_ticker
        if not ticker_sym:
            try:
                from apps.funds.runtime import resolve_yahoo_ticker
                ticker_sym = resolve_yahoo_ticker(scheme, None)
                # Persist resolved ticker so CI re-runs skip re-resolution
                if ticker_sym:
                    scheme.yahoo_ticker = ticker_sym
                    scheme.save(update_fields=['yahoo_ticker'])
                    logger.debug('[%s] Persisted yahoo_ticker=%s', scheme.amfi_code, ticker_sym)
            except Exception:
                ticker_sym = None
        if not ticker_sym:
            return None, None, None

        time.sleep(delay * 0.25)  # yahooquery is more permissive

        try:
            t    = Ticker(ticker_sym)
            info = t.fund_holding_info

            if not isinstance(info, dict) or ticker_sym not in info:
                return None, None, None

            finfo = info[ticker_sym]
            # yahooquery sometimes returns a string error (e.g. "No fundamentals data found")
            if not isinstance(finfo, dict):
                return None, None, None

            # ── Top holdings ─────────────────────────────────────────────────
            holdings_list = []
            for h in (finfo.get('holdings') or []):
                name   = str(h.get('holdingName', '') or h.get('symbol', ''))
                weight = _to_decimal(h.get('holdingPercent'))
                if weight is not None:
                    weight = weight * 100  # yahooquery returns 0.xx fractions
                if not name or weight is None:
                    continue
                holdings_list.append({
                    'security_name': name,
                    'weight_pct':    weight,
                    'holding_type':  'equity',
                    'isin':          '',
                    'ticker':        str(h.get('symbol', '') or ''),
                    'sector':        '',
                    'forward_pe':    None,
                    'market_value':  None,
                })

            if not holdings_list:
                return None, None, None

            # ── Sector weights ────────────────────────────────────────────────
            sector_list = []
            for s in (finfo.get('sectorWeightings') or []):
                for sector_name, weight_raw in s.items():
                    w = _to_decimal(weight_raw)
                    if w is not None and sector_name:
                        sector_list.append({
                            'sector':     sector_name,
                            'weight_pct': w * 100,
                        })

            # ── Asset allocation ──────────────────────────────────────────────
            alloc: dict = {'equity_pct': None, 'debt_pct': None, 'cash_pct': None}
            for key in ('cashPosition', 'bondPosition', 'stockPosition', 'otherPosition'):
                val = finfo.get(key)
                if val is not None:
                    pct = _to_decimal(val)
                    if pct is not None:
                        pct = pct * 100
                    if key == 'cashPosition':
                        alloc['cash_pct']   = pct
                    elif key == 'bondPosition':
                        alloc['debt_pct']   = pct
                    elif key == 'stockPosition':
                        alloc['equity_pct'] = pct

            return holdings_list, sector_list, alloc

        except Exception as exc:
            logger.warning('[yahoo] fetch failed for %s (%s): %s',
                           scheme.amfi_code, ticker_sym, exc)
            return None, None, None

    # ── DB persistence ───────────────────────────────────────────────────────────

    @transaction.atomic
    def _save_holdings(
        self,
        scheme: Scheme,
        as_of_month: date,
        holdings_list: list,
        sector_list: list | None,
        alloc: dict | None,
        cap_result: dict | None,
        source: str,
        batch_size: int,
    ) -> None:
        """Save holdings, sector allocations, and market cap allocation to DB."""

        # ── Holdings ─────────────────────────────────────────────────────────────
        # Delete existing data for this month before re-inserting (clean re-run)
        Holding.objects.filter(scheme=scheme, as_of_month=as_of_month).delete()

        to_create = []
        for h in holdings_list:
            to_create.append(Holding(
                scheme        = scheme,
                as_of_month   = as_of_month,
                security_name = h['security_name'][:300],
                isin          = (h.get('isin') or '')[:15],
                ticker        = (h.get('ticker') or '')[:20],
                weight_pct    = h['weight_pct'],
                market_value  = h.get('market_value'),
                sector        = (h.get('sector') or '')[:100],
                forward_pe    = h.get('forward_pe'),
                holding_type  = h.get('holding_type', 'equity'),
                source        = source,
            ))

        # Bulk create in batches
        for i in range(0, len(to_create), batch_size):
            Holding.objects.bulk_create(
                to_create[i:i + batch_size],
                ignore_conflicts=True,
            )

        # ── Sector Allocations ────────────────────────────────────────────────────
        if not sector_list and holdings_list:
            sec_totals = {}
            for h in holdings_list:
                sec = (h.get('sector') or '').strip()
                w = _to_decimal(h.get('weight_pct'))
                if sec and w and w > 0:
                    sec_totals[sec] = sec_totals.get(sec, Decimal('0')) + w
            if sec_totals:
                sector_list = [
                    {'sector': k, 'weight_pct': v}
                    for k, v in sorted(sec_totals.items(), key=lambda x: x[1], reverse=True)
                ]

        if sector_list:
            SectorAllocation.objects.filter(
                scheme=scheme, as_of_month=as_of_month
            ).delete()
            sa_create = []
            for s in sector_list:
                sector_name = str(s.get('sector', '')).strip()[:100]
                weight      = s.get('weight_pct')
                if not sector_name or weight is None:
                    continue
                sa_create.append(SectorAllocation(
                    scheme      = scheme,
                    as_of_month = as_of_month,
                    sector      = sector_name,
                    weight_pct  = _to_decimal(weight) or Decimal('0'),
                    source      = source,
                ))
            if sa_create:
                SectorAllocation.objects.bulk_create(sa_create, ignore_conflicts=True)

        # ── Market Cap Allocation ─────────────────────────────────────────────────
        mcap_defaults: dict = {
            'large_pct':  None,
            'mid_pct':    None,
            'small_pct':  None,
            'other_pct':  None,
            'equity_pct': None,
            'debt_pct':   None,
            'cash_pct':   None,
            'cap_method': 'unknown',
            'source':     source,
        }

        if alloc:
            mcap_defaults.update({
                'equity_pct': _to_decimal(alloc.get('equity_pct')),
                'debt_pct':   _to_decimal(alloc.get('debt_pct')),
                'cash_pct':   _to_decimal(alloc.get('cash_pct')),
            })
            # If finapi provided SEBI-disclosed cap breakdown, use it directly
            if (alloc.get('large_pct') is not None
                    or alloc.get('mid_pct') is not None
                    or alloc.get('small_pct') is not None):
                mcap_defaults.update({
                    'large_pct':  _to_decimal(alloc.get('large_pct')),
                    'mid_pct':    _to_decimal(alloc.get('mid_pct')),
                    'small_pct':  _to_decimal(alloc.get('small_pct')),
                    'other_pct':  _to_decimal(alloc.get('other_pct')),
                    'cap_method': 'disclosure',
                })

        # If no cap disclosure from source, use CapClassifier on the holdings list
        if mcap_defaults.get('large_pct') is None and cap_result:
            mcap_defaults.update({
                'large_pct':  _to_decimal(cap_result['large_pct']),
                'mid_pct':    _to_decimal(cap_result['mid_pct']),
                'small_pct':  _to_decimal(cap_result['small_pct']),
                'other_pct':  _to_decimal(cap_result.get('other_pct')),
                'cap_method': 'caplist',
            })

        MarketCapAllocation.objects.update_or_create(
            scheme=scheme, as_of_month=as_of_month, defaults=mcap_defaults
        )


# ── Helper parsers ────────────────────────────────────────────────────────────────

def _finapi_holding_type(name: str, sector: str) -> str:
    """Classify a holding as equity/debt/cash/other from its name and sector."""
    text = f'{name} {sector}'.lower()
    if any(m in text for m in ['cash', 'treasury', 'clearing corporation', 'ccil',
                                'tri party', 't-bill']):
        return 'cash'
    if any(m in text for m in ['bond', 'debenture', 'government securities', 'g-sec',
                                'securit', 'ncd', 'commercial paper', 'cp ']):
        return 'debt'
    if any(m in text for m in ['gold', 'silver', 'platinum', 'commodity', 'bullion']):
        return 'other'
    return 'equity'
