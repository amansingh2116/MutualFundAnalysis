"""
Management command: build_scheme_master
=======================================
One-time (then re-runnable) command to populate the Scheme table
from AMFI NAVAll.txt.

Usage:
    python manage.py build_scheme_master
    python manage.py build_scheme_master --dry-run    (count only)
    python manage.py build_scheme_master --direct-only  (only direct plans)

What it does:
    1. Downloads AMFI NAVAll.txt via AMFIAdapter
    2. Parses all scheme rows (~14,364 as of 2025)
    3. Upserts Scheme records (amfi_code is the unique key)
    4. Detects is_direct and plan from scheme name
    5. Reports count of new vs updated records
"""
import logging
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from adapters.amfi_adapter import AMFIAdapter
from apps.funds.models import Scheme
from apps.core.utils import parse_amfi_date, is_direct_scheme, is_growth_scheme, is_etf_scheme, is_open_ended_scheme

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = 'Build/update the scheme master from AMFI NAVAll.txt'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Parse and count schemes without writing to DB',
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Limit import to first N schemes (for testing)',
        )

    def handle(self, *args, **options):
        dry_run     = options['dry_run']
        limit       = options['limit']

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Building scheme master {'(DRY RUN)' if dry_run else ''}"
        ))

        # Fetch scheme universe
        adapter = AMFIAdapter()
        try:
            raw_schemes = adapter.fetch_scheme_universe()
        except Exception as e:
            raise CommandError(f"Failed to fetch AMFI data: {e}")

        self.stdout.write(f"  Fetched {len(raw_schemes)} raw scheme rows from AMFI")

        # Filter: Open-Ended Direct Growth OR ETFs
        # New AMFI format: plan_col='Direct Plan', option_col='Growth Option'
        # Old AMFI format: plan_col='', option_col='' → fall back to name heuristics
        filtered_schemes = []
        for s in raw_schemes:
            name     = s['scheme_name']
            stype    = s.get('scheme_type', '')
            plan_col = s.get('plan_col', '').lower()
            opt_col  = s.get('option_col', '').lower()

            if not is_open_ended_scheme(stype, name):
                continue

            # ETF: always included regardless of plan/option
            if is_etf_scheme(name):
                filtered_schemes.append(s)
                continue

            # Direct Growth detection:
            #  - New format: explicit 'direct' in plan_col AND 'growth' in option_col
            #  - Old format: fallback to name heuristics (plan_col is empty)
            if plan_col:
                is_direct = 'direct' in plan_col
                is_growth = 'growth' in opt_col and 'idcw' not in opt_col and 'dividend' not in opt_col
            else:
                is_direct = is_direct_scheme(name)
                is_growth = is_growth_scheme(name)

            if is_direct and is_growth:
                filtered_schemes.append(s)

        raw_schemes = filtered_schemes
        self.stdout.write(f"  After Open-Ended Direct Growth / ETF filter: {len(raw_schemes)} schemes")

        if limit:
            raw_schemes = raw_schemes[:limit]
            self.stdout.write(f"  Limited to first {limit} schemes")

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"DRY RUN complete. Would import {len(raw_schemes)} schemes."
            ))
            return

        # Upsert into DB
        created_count = 0
        updated_count = 0
        error_count   = 0

        for i, raw in enumerate(raw_schemes, 1):
            try:
                scheme_name = raw['scheme_name']
                nav_date    = parse_amfi_date(raw.get('date', ''))

                # Detect plan and direct:
                # New format: use explicit plan_col / option_col columns
                # Old format: fall back to scheme name heuristics
                plan_col = raw.get('plan_col', '').lower()
                opt_col  = raw.get('option_col', '').lower()

                if plan_col:
                    is_direct = 'direct' in plan_col
                    is_growth_flag = 'growth' in opt_col and 'idcw' not in opt_col and 'dividend' not in opt_col
                else:
                    is_direct = is_direct_scheme(scheme_name)
                    is_growth_flag = is_growth_scheme(scheme_name)

                plan = 'GROWTH' if is_growth_flag else 'IDCW'

                # Parse NAV safely
                try:
                    nav_val = float(raw['nav']) if raw.get('nav') else None
                except (ValueError, TypeError):
                    nav_val = None

                stype_raw = raw.get('scheme_type', '')
                cat_match = re.search(r'\((.*?)\)', stype_raw)
                extracted_cat = cat_match.group(1).strip() if cat_match else ''

                defaults = {
                    'isin_growth':   raw.get('isin_growth'),
                    'isin_idcw':     raw.get('isin_idcw'),
                    'scheme_name':   scheme_name,
                    'fund_house':    raw.get('amc_name', ''),
                    'scheme_type':   stype_raw,
                    'plan':          plan,
                    'is_direct':     is_direct,
                    'is_etf':        etf,
                    'is_active':     True,
                    'nav_latest':    nav_val,
                    'nav_date':      nav_date,
                }

                obj, created = Scheme.objects.get_or_create(
                    amfi_code=raw['amfi_code'],
                    defaults={**defaults, 'scheme_category': extracted_cat},
                )
                if not created:
                    if not obj.scheme_category and extracted_cat:
                        defaults['scheme_category'] = extracted_cat
                    for k, v in defaults.items():
                        setattr(obj, k, v)
                    obj.save()
                    updated_count += 1
                else:
                    created_count += 1

            except Exception as e:
                error_count += 1
                logger.warning(f"Error processing scheme {raw.get('amfi_code', '?')}: {e}")

            if i % 1000 == 0:
                self.stdout.write(f"  Processed {i}/{len(raw_schemes)}...")

        # Clean up legacy schemes that no longer match the filter.
        # CockroachDB enforces a 1 MB per-transaction lock budget; a single
        # bulk DELETE on a large queryset easily exceeds it.  We therefore
        # collect the PKs to remove first and delete them in small batches,
        # each committed in its own transaction.
        valid_amfi_codes = [raw['amfi_code'] for raw in raw_schemes]
        stale_ids = list(
            Scheme.objects.exclude(amfi_code__in=valid_amfi_codes)
                          .values_list('pk', flat=True)
        )
        # Keep batches small: each Scheme deletion cascades into analytics,
        # holdings, recommendations etc., multiplying lock counts significantly.
        BATCH_SIZE = 25
        deleted_count = 0
        for batch_start in range(0, len(stale_ids), BATCH_SIZE):
            batch = stale_ids[batch_start:batch_start + BATCH_SIZE]
            n, _ = Scheme.objects.filter(pk__in=batch).delete()
            deleted_count += n
        self.stdout.write(f"  Cleaned up {deleted_count} legacy schemes not matching criteria.")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Created: {created_count} | Updated: {updated_count} | Errors: {error_count} | Deleted: {deleted_count}"
        ))
        self.stdout.write(f"Total schemes in DB: {Scheme.objects.count()}")
