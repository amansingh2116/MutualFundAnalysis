"""
Management command: ingest_nav
==============================
Daily NAV ingestion for all active Direct Growth schemes.

Primary:  mfapi.in REST API (fast JSON, no rate limits)
Fallback: mftool library

Strategy:
  - Check latest NAV date in DB per scheme
  - Skip if already up-to-date (nav_date == today)
  - Only insert missing dates (idempotent)

Usage:
    python manage.py ingest_nav
    python manage.py ingest_nav --limit=100   (test with 100 schemes)
    python manage.py ingest_nav --amfi=120503 (single scheme)
    python manage.py ingest_nav --force       (re-fetch even if up to date)
"""
import logging
import time
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from adapters.amfi_adapter import AMFIAdapter
from apps.funds.models import Scheme, NAVHistory
from apps.core.utils import parse_amfi_date

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = 'Ingest daily NAV history for all active Direct Growth schemes'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Limit to first N schemes')
        parser.add_argument('--amfi', type=str, default=None,
                            help='Process a single scheme by AMFI code')
        parser.add_argument('--force', action='store_true',
                            help='Re-fetch even if NAV is already up to date')
        parser.add_argument('--direct-only', action='store_true', default=True,
                            help='Only fetch Direct Growth schemes (default: True)')

    def handle(self, *args, **options):
        limit       = options['limit']
        amfi_code   = options['amfi']
        force       = options['force']
        today       = date.today()
        adapter     = AMFIAdapter()

        if amfi_code:
            schemes = Scheme.objects.filter(amfi_code=amfi_code)
            if not schemes.exists():
                raise CommandError(f"Scheme {amfi_code} not found in DB. Run build_scheme_master first.")
        else:
            schemes = Scheme.objects.filter(is_direct=True, plan='GROWTH', is_active=True)

        if limit:
            schemes = schemes[:limit]

        total = schemes.count()
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Ingesting NAV for {total} schemes (today={today})"
        ))

        inserted_total = 0
        skipped_total  = 0
        error_total    = 0

        for i, scheme in enumerate(schemes, 1):
            try:
                # Check if already up to date
                latest_date = (NAVHistory.objects
                               .filter(scheme=scheme)
                               .aggregate(Max('date'))['date__max'])

                if not force and latest_date and latest_date >= today:
                    skipped_total += 1
                    continue

                # Fetch full history (mfapi returns newest first)
                history = adapter.fetch_nav_history(scheme.amfi_code)

                if not history:
                    # Fallback to mftool
                    logger.info(f"[{scheme.amfi_code}] mfapi empty — trying mftool")
                    history = adapter.fetch_nav_history_mftool(scheme.amfi_code)

                if not history:
                    logger.warning(f"[{scheme.amfi_code}] No NAV data from any source")
                    error_total += 1
                    continue

                # Filter to only new dates
                cutoff = latest_date if (latest_date and not force) else date(1990, 1, 1)
                new_rows = []
                for entry in history:
                    entry_date = parse_amfi_date(entry.get('date', ''))
                    if not entry_date or entry_date <= cutoff:
                        continue
                    try:
                        nav_val = float(entry['nav'])
                        if nav_val <= 0:
                            continue
                        new_rows.append(NAVHistory(
                            scheme=scheme, date=entry_date, nav=nav_val
                        ))
                    except (ValueError, TypeError, KeyError):
                        continue

                if new_rows:
                    NAVHistory.objects.bulk_create(new_rows, ignore_conflicts=True)
                    inserted_total += len(new_rows)

                    # Update cached nav_latest on Scheme
                    latest_entry = sorted(new_rows, key=lambda r: r.date)[-1]
                    Scheme.objects.filter(pk=scheme.pk).update(
                        nav_latest=latest_entry.nav,
                        nav_date=latest_entry.date,
                    )

            except Exception as e:
                error_total += 1
                logger.error(f"[{scheme.amfi_code}] NAV ingest error: {e}")

            if i % 100 == 0:
                self.stdout.write(f"  {i}/{total} schemes processed...")

            # Small delay to be kind to mfapi.in
            time.sleep(adapter.RATE_LIMIT_DELAY)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Inserted: {inserted_total} rows | "
            f"Skipped (up-to-date): {skipped_total} | Errors: {error_total}"
        ))
