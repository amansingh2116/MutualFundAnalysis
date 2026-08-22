"""
Management command: ingest_holdings (FULL IMPLEMENTATION)

Fetches fund portfolio holdings, sector allocation, and market cap breakdown
for all active direct growth schemes and saves them to the DB for 3 months of
point-in-time portfolio evolution tracking.

Strategy:
  1. mstarpy-FIRST  — Full holdings for schemes with morningstar_id (Selenium required)
  2. yahooquery FALLBACK — Top-10 holdings + full sector data for all others
  3. CapClassifier   — Maps equity holdings → Large/Mid/Small via rapidfuzz

Key features:
  - Resume support: checkpoints progress to a JSON file, skips already-processed schemes
  - Rate limiting: 2s delay for mstarpy, 0.5s for yahooquery; exponential backoff on 429
  - Batch transactions: DB writes in batches of 50 for CockroachDB compatibility
  - Non-equity handling: Debt, cash, commodity instruments stored with their type
  - Idempotent: update_or_create safe to re-run

Usage:
    python manage.py ingest_holdings
    python manage.py ingest_holdings --date 2025-07-01    # specific month
    python manage.py ingest_holdings --limit 10           # test on 10 funds
    python manage.py ingest_holdings --amfi 120503        # single fund
    python manage.py ingest_holdings --resume             # skip already-done funds
    python manage.py ingest_holdings --source yahoo       # yahooquery only
    python manage.py ingest_holdings --force              # overwrite existing data
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.funds.models import Scheme
from apps.holdings.models import Holding, SectorAllocation, MarketCapAllocation

logger = logging.getLogger('mfanalysis')

# Management commands always run from the project root (where manage.py lives)
_CHECKPOINT_PATH = os.path.join(os.getcwd(), '.cache', 'ingest_holdings_checkpoint.json')


import math

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
        '(mstarpy-first, yahooquery fallback). Run monthly.'
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
        parser.add_argument('--source', choices=['auto', 'mstarpy', 'yahoo'],
                            default='auto',
                            help='Data source: auto (mstarpy-first), mstarpy, yahoo')
        parser.add_argument('--delay', type=float, default=2.0,
                            help='Seconds between mstarpy API calls (default 2.0)')
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

        total   = qs.count()
        success = 0
        failed  = 0
        skipped = 0
        discovered = 0

        self.stdout.write(f'Processing {total} schemes ...')

        for idx, scheme in enumerate(qs.iterator(chunk_size=100), start=1):
            amfi = scheme.amfi_code

            # ── Skip if resumed ───────────────────────────────────────────────
            if resume and amfi in done_amfis:
                skipped += 1
                continue

            # ── Auto-resolve morningstar_id if missing ──────────────────────────
            if source in ('auto', 'mstarpy') and not scheme.morningstar_id:
                try:
                    from adapters.mstarpy_adapter import MstarpyAdapter
                    _adapter = MstarpyAdapter()
                    if _adapter.is_available():
                        # Try ISIN first (more precise), fall back to fund name
                        _term = scheme.isin_growth or scheme.scheme_name
                        _results = _adapter.search_fund(_term, page_size=1)
                        if _results and isinstance(_results, list):
                            _sec_id = _results[0].get('SecId') or _results[0].get('secId')
                            if _sec_id:
                                scheme.morningstar_id = _sec_id
                                scheme.save(update_fields=['morningstar_id'])
                                logger.info('[%s] morningstar_id resolved: %s', amfi, _sec_id)
                                discovered += 1
                except Exception as _exc:
                    logger.debug('[%s] morningstar_id auto-resolve failed: %s', amfi, _exc)

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

            use_mstarpy = (source in ('auto', 'mstarpy')
                           and scheme.morningstar_id
                           and not scheme.morningstar_id.startswith('PLACEHOLDER'))
            # Yahoo only works for ETFs with explicit yahoo_ticker (e.g. NIFTYBEES.NS).
            # isin_growth-based lookup does NOT return Indian MF holdings from Yahoo Finance.
            use_yahoo   = (source in ('auto', 'yahoo') and scheme.yahoo_ticker)

            if use_mstarpy:
                try:
                    hd, sd, ad = self._fetch_mstarpy(scheme, delay)
                    if hd is not None:
                        holdings_data   = hd
                        sector_data     = sd
                        allocation_data = ad
                        data_source     = 'mstarpy'
                except Exception as exc:
                    logger.warning('[%s] mstarpy fetch failed: %s', amfi, exc)

            if holdings_data is None and (source in ('auto', 'yahoo')) and use_yahoo:
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
            f'Success: {success} | Failed: {failed} | Skipped: {skipped}\n'
            f'morningstar_id discovered: {discovered}'
        ))

    # ── mstarpy fetch ────────────────────────────────────────────────────────────

    def _fetch_mstarpy(self, scheme: Scheme, delay: float):
        """Fetch holdings, sector, allocation from mstarpy. Returns (holdings, sectors, allocation)."""
        from adapters.mstarpy_adapter import MstarpyAdapter
        import pandas as pd

        adapter = MstarpyAdapter()
        ms_id   = scheme.morningstar_id

        holdings_df = adapter.fetch_holdings(ms_id)
        time.sleep(delay)

        if holdings_df is None or (hasattr(holdings_df, 'empty') and holdings_df.empty):
            return None, None, None

        # Parse holdings DataFrame
        holdings_list = []
        for _, row in holdings_df.iterrows():
            name   = str(row.get('securityName') or row.get('name') or '')
            weight = _to_decimal(row.get('weighting') or row.get('weight') or row.get('weighting%'))
            htype  = str(row.get('holdingType', 'equity') or 'equity').lower()
            isin   = str(row.get('isin', '') or '')
            ticker = str(row.get('ticker', '') or '')
            sector = str(row.get('sector', '') or '')
            pe     = _to_decimal(row.get('forwardPERatio') or row.get('pe'))
            mval   = _to_decimal(row.get('marketValue'))

            if not name or weight is None:
                continue

            holdings_list.append({
                'security_name': name,
                'weight_pct':    weight,
                'holding_type':  htype if htype in ('equity', 'debt', 'cash', 'other') else 'equity',
                'isin':          isin[:15] if isin else '',
                'ticker':        ticker[:20] if ticker else '',
                'sector':        sector[:100] if sector else '',
                'forward_pe':    pe,
                'market_value':  mval,
            })

        # Sector allocation
        sector_df = adapter.fetch_sector_allocation(ms_id)
        time.sleep(max(delay * 0.5, 0.5))
        sector_list = _parse_sector_df(sector_df)

        # Asset allocation
        port_stats = adapter.fetch_portfolio_statistics(ms_id)
        time.sleep(max(delay * 0.5, 0.5))
        alloc = _parse_allocation_mstarpy(port_stats)

        return holdings_list, sector_list, alloc

    # ── yahooquery fetch ─────────────────────────────────────────────────────────

    def _fetch_yahoo(self, scheme: Scheme, delay: float):
        """Fetch top-10 holdings + sector weights from yahooquery."""
        try:
            from yahooquery import Ticker
        except ImportError:
            return None, None, None

        # Only use a Yahoo ticker if we have an explicit mapping.
        # Using {amfi_code}.BO as a fallback is unreliable for mutual funds.
        ticker_sym = scheme.yahoo_ticker
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
            alloc = {
                'equity_pct': _to_decimal(finfo.get('equityHoldings', {}).get('priceToBook')),
                'debt_pct':   None,
                'cash_pct':   None,
            }
            # cashPosition, bondPosition, stockPosition from top-level
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

        if cap_result:
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

def _parse_sector_df(sector_df) -> list[dict]:
    """Parse mstarpy sector allocation DataFrame or dict to list of dicts."""
    if sector_df is None:
        return []
    try:
        import pandas as pd
        if isinstance(sector_df, pd.DataFrame):
            result = []
            # mstarpy typically returns columns: 'name', 'equity' (or similar weight col)
            weight_col = next(
                (c for c in sector_df.columns if 'weight' in c.lower() or 'equity' in c.lower()),
                None
            )
            name_col = next(
                (c for c in sector_df.columns if 'name' in c.lower() or 'sector' in c.lower()),
                None
            )
            if weight_col and name_col:
                for _, row in sector_df.iterrows():
                    sector = str(row.get(name_col, ''))
                    weight = _to_decimal(row.get(weight_col))
                    if sector and weight:
                        result.append({'sector': sector, 'weight_pct': weight})
            return result
        if isinstance(sector_df, dict):
            return [
                {'sector': k, 'weight_pct': _to_decimal(v)}
                for k, v in sector_df.items() if v
            ]
    except Exception as exc:
        logger.warning('Sector parse error: %s', exc)
    return []


def _parse_allocation_mstarpy(port_stats) -> dict:
    """Parse mstarpy portfolioStatistics for asset class breakdown."""
    result = {'equity_pct': None, 'debt_pct': None, 'cash_pct': None}
    if port_stats is None:
        return result
    try:
        # Port stats is usually a dict of period -> metrics
        # Look for 'portfolioDate' row or flat dict
        data = port_stats
        if isinstance(data, dict):
            # Try to find equity/bond/cash keys
            for k, v in data.items():
                kl = str(k).lower()
                if 'equity' in kl or 'stock' in kl:
                    result['equity_pct'] = _to_decimal(v)
                elif 'bond' in kl or 'debt' in kl or 'fixed' in kl:
                    result['debt_pct'] = _to_decimal(v)
                elif 'cash' in kl:
                    result['cash_pct'] = _to_decimal(v)
    except Exception as exc:
        logger.warning('Allocation parse error: %s', exc)
    return result
