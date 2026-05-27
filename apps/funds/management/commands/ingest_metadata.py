"""
Management command: ingest_metadata
=====================================
Weekly enrichment of Scheme records with data from captnemo.in + mstarpy.

Primary: captnemo.in (expense ratio, AUM, fund manager, SIP rules, returns, etc.)
Supplement: mstarpy (MS rating, category, risk metrics snapshot)

Strategy:
  - Process Direct Growth schemes with a valid isin_growth
  - Skip schemes already fetched within last 7 days (unless --force)
  - Store all fields in SchemeMeta (OneToOne with Scheme)
  - Update denormalized fields on Scheme (expense_ratio, aum_cr)

Usage:
    python manage.py ingest_metadata
    python manage.py ingest_metadata --limit=50
    python manage.py ingest_metadata --amfi=120503
    python manage.py ingest_metadata --force
    python manage.py ingest_metadata --skip-mstarpy
"""
import logging
import time
from datetime import date, timedelta, datetime

from django.core.management.base import BaseCommand, CommandError

from adapters.captnemo_adapter import CaptnemoAdapter
from adapters.mstarpy_adapter import MstarpyAdapter
from apps.funds.models import Scheme, SchemeMeta

logger = logging.getLogger('mfanalysis')

STALE_DAYS = 7   # re-fetch metadata if older than this many days


class Command(BaseCommand):
    help = 'Ingest fund enrichment metadata from captnemo.in + mstarpy'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--amfi', type=str, default=None)
        parser.add_argument('--force', action='store_true',
                            help='Re-fetch even if recently fetched')
        parser.add_argument('--skip-mstarpy', action='store_true',
                            help='Skip mstarpy supplement (faster)')

    def handle(self, *args, **options):
        limit        = options['limit']
        amfi_code    = options['amfi']
        force        = options['force']
        skip_mstarpy = options['skip_mstarpy']
        stale_cutoff = date.today() - timedelta(days=STALE_DAYS)

        cap_adapter  = CaptnemoAdapter()
        ms_adapter   = MstarpyAdapter() if not skip_mstarpy else None

        # Build queryset
        qs = Scheme.objects.filter(is_direct=True, plan='GROWTH', is_active=True)
        if amfi_code:
            qs = qs.filter(amfi_code=amfi_code)
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Ingesting metadata for {total} schemes"
            + (' (--force)' if force else f' (stale cutoff: {stale_cutoff})')
        ))

        success = error = skipped = 0

        for i, scheme in enumerate(qs, 1):
            try:
                # Check freshness
                try:
                    meta_obj = SchemeMeta.objects.get(scheme=scheme)
                    if not force and meta_obj.last_fetched.date() > stale_cutoff:
                        skipped += 1
                        continue
                except SchemeMeta.DoesNotExist:
                    meta_obj = None

                # Fetch from captnemo
                isin = scheme.isin_growth or scheme.isin_idcw
                if not isin:
                    logger.warning(f"[{scheme.amfi_code}] No ISIN — skipping captnemo")
                    error += 1
                    continue

                fund_info = cap_adapter.fetch_fund_info(isin=isin)
                if not fund_info:
                    logger.warning(f"[{scheme.amfi_code}] captnemo returned nothing")
                    error += 1
                    continue

                # Extract and upsert SchemeMeta
                meta_fields = cap_adapter.extract_scheme_meta(fund_info)

                # Also update scheme_category from captnemo if available
                # (captnemo 'category' field maps to SEBI category)
                cap_category = fund_info.get('category', '')
                if cap_category and not scheme.scheme_category:
                    Scheme.objects.filter(pk=scheme.pk).update(
                        scheme_category=cap_category
                    )

                # Fetch Morningstar supplement if morningstar_id exists
                if ms_adapter and scheme.morningstar_id and ms_adapter.is_available():
                    try:
                        tr_data = ms_adapter.fetch_trailing_returns(scheme.morningstar_id)
                        if tr_data:
                            meta_fields['ms_rating'] = tr_data.get('overallMorningstarRating')
                            meta_fields['ms_category'] = tr_data.get('categoryName', '')
                    except Exception as ms_err:
                        logger.debug(f"[{scheme.amfi_code}] mstarpy supplement failed: {ms_err}")

                SchemeMeta.objects.update_or_create(
                    scheme=scheme,
                    defaults=meta_fields,
                )

                # Update denormalized fields on Scheme
                update_fields = {}
                if meta_fields.get('expense_ratio') is not None:
                    update_fields['expense_ratio'] = meta_fields['expense_ratio']
                if meta_fields.get('aum') is not None:
                    update_fields['aum_cr'] = meta_fields['aum']
                if update_fields:
                    Scheme.objects.filter(pk=scheme.pk).update(**update_fields)

                success += 1

            except Exception as e:
                error += 1
                logger.error(f"[{scheme.amfi_code}] ingest_metadata error: {e}")

            if i % 50 == 0:
                self.stdout.write(f"  {i}/{total} | ok={success} err={error} skip={skipped}")

            time.sleep(cap_adapter.RATE_LIMIT_DELAY)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Success: {success} | Errors: {error} | Skipped: {skipped}"
        ))
