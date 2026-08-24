"""
Management command: build_mstar_ids

One-time command to populate Scheme.morningstar_id for all active direct-growth
equity/hybrid funds. Once populated, ingest_holdings can use the Morningstar
REST API (plain HTTP, no browser) for all subsequent ingestion runs.

This command uses the mstarpy library's screener (which requires Selenium/Chrome
on FIRST run) to map each fund's ISIN → Morningstar SecId (F0...).

Run this ONCE (or when new funds are added):
    python manage.py build_mstar_ids
    python manage.py build_mstar_ids --limit 20    # test first 20
    python manage.py build_mstar_ids --amfi 120503 # single fund
    python manage.py build_mstar_ids --force        # re-lookup even if set

After this runs successfully, ingest_holdings can use --source morningstar
(or --source auto) and it will use the pure-HTTP REST API with no browser.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.funds.models import Scheme

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = (
        'Populate Scheme.morningstar_id via ISIN → SecId lookup (one-time setup). '
        'Requires mstarpy + Chrome for the screener search.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Max number of schemes to process')
        parser.add_argument('--amfi', type=str, default=None,
                            help='Process a single AMFI code only')
        parser.add_argument('--force', action='store_true',
                            help='Re-lookup even if morningstar_id is already set')
        parser.add_argument('--delay', type=float, default=2.0,
                            help='Seconds between API calls (default 2.0 — Morningstar rate limits)')

    def handle(self, *args, **options):
        limit  = options['limit']
        amfi   = options['amfi']
        force  = options['force']
        delay  = options['delay']

        self.stdout.write(self.style.NOTICE('=== Building Morningstar SecId Mapping ==='))

        # Check mstarpy availability
        try:
            from adapters.mstarpy_adapter import MstarpyAdapter
            adapter = MstarpyAdapter()
            if not adapter.is_available():
                self.stdout.write(self.style.ERROR('mstarpy is not installed. Run: pip install mstarpy'))
                return
        except ImportError as exc:
            self.stdout.write(self.style.ERROR(f'Cannot import MstarpyAdapter: {exc}'))
            return

        # Scheme queryset — equity + hybrid, active, direct growth
        qs = Scheme.objects.filter(
            Q(is_direct=True, plan='GROWTH') | Q(is_etf=True),
            is_active=True,
        ).exclude(isin_growth='').exclude(isin_growth__isnull=True)

        if not force:
            qs = qs.filter(Q(morningstar_id='') | Q(morningstar_id__isnull=True))

        if amfi:
            qs = qs.filter(amfi_code=amfi)

        if limit:
            qs = qs[:limit]

        total   = qs.count()
        success = 0
        failed  = 0
        skipped = 0

        self.stdout.write(f'Looking up SecIds for {total} schemes (delay={delay}s) ...')
        self.stdout.write(
            self.style.WARNING(
                'Note: mstarpy screener requires Chrome/Selenium. '
                'This may fail in headless environments without GPU/display.'
            )
        )

        for idx, scheme in enumerate(qs.iterator(chunk_size=50), start=1):
            amfi_code = scheme.amfi_code
            isin      = scheme.isin_growth

            try:
                # Use mstarpy adapter search (Selenium-based screener)
                results = adapter.search_fund(
                    name=isin, page_size=5
                )

                if not results:
                    logger.warning('[%s] No mstarpy results for ISIN %s', amfi_code, isin)
                    failed += 1
                    continue

                # Pick the first result whose ISIN matches
                sec_id = None
                for r in results:
                    r_isin = str(r.get('isin') or '').strip().upper()
                    r_secid = str(r.get('SecId') or r.get('securityID') or '').strip()
                    if r_isin == isin.upper() and r_secid.startswith('F'):
                        sec_id = r_secid
                        break

                if not sec_id:
                    # Try first result with a valid SecId even if ISIN doesn't match
                    for r in results:
                        r_secid = str(r.get('SecId') or r.get('securityID') or '').strip()
                        if r_secid.startswith('F'):
                            sec_id = r_secid
                            break

                if sec_id:
                    scheme.morningstar_id = sec_id
                    scheme.save(update_fields=['morningstar_id'])
                    success += 1
                    logger.info('[%s] SecId=%s for ISIN=%s', amfi_code, sec_id, isin)
                    self.stdout.write(f'  [{idx}/{total}] {amfi_code} → {sec_id}')
                else:
                    logger.warning('[%s] No valid SecId found in results for ISIN=%s', amfi_code, isin)
                    failed += 1

            except Exception as exc:
                logger.warning('[%s] build_mstar_ids failed: %s', amfi_code, exc)
                failed += 1

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Mstar ID Mapping Complete ===\n'
            f'Total: {total} | Success: {success} | Failed: {failed} | Skipped: {skipped}\n'
            f'\nNext step: run ingest_holdings --source morningstar --resume'
        ))
