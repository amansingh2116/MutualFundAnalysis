"""
Management command: ingest_holdings

Fetches top holdings and sector allocation for all direct growth schemes
using the MstarpyAdapter. Runs monthly.
"""
import logging
from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.funds.models import Scheme
from apps.holdings.models import Holding, SectorAllocation, MarketCapAllocation
from adapters.registry import ADAPTERS

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = 'Ingests holdings, sector allocation, and market cap data for schemes'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, help='Limit number of schemes to process')
        parser.add_argument('--amfi', type=str, help='Process specific AMFI code only')
        parser.add_argument('--force', action='store_true', help='Force refetch even if recent data exists')
        parser.add_argument('--date', type=str, help='Snapshot date YYYY-MM-01 (defaults to current month start)')

    def handle(self, *args, **options):
        limit = options['limit']
        amfi = options['amfi']
        force = options['force']
        
        target_date_str = options['date']
        if target_date_str:
            as_of_month = date.fromisoformat(target_date_str)
        else:
            today = timezone.localdate()
            as_of_month = date(today.year, today.month, 1)

        self.stdout.write(self.style.NOTICE(f"=== Starting Holdings Ingestion (Snapshot: {as_of_month}) ==="))

        mstar_adapter = ADAPTERS['mstarpy']()

        qs = Scheme.objects.filter(is_direct=True, plan='GROWTH', is_active=True).exclude(morningstar_id__isnull=True).exclude(morningstar_id='')
        
        if amfi:
            qs = qs.filter(amfi_code=amfi)
            
        if limit:
            qs = qs[:limit]

        total = qs.count()
        success = 0
        skipped = 0
        errors = 0

        self.stdout.write(f"Targeting {total} schemes with Morningstar IDs...")

        for scheme in qs:
            ms_id = scheme.morningstar_id
            
            if not force:
                if Holding.objects.filter(scheme=scheme, as_of_month=as_of_month).exists():
                    logger.debug(f"[{scheme.amfi_code}] Holdings for {as_of_month} already exist. Skipping.")
                    skipped += 1
                    continue
            
            try:
                # 1. Fetch data from mstarpy adapter
                # Phase 1 stub: mstarpy adapter implementation needs to be connected to models here
                # We'll just create a dummy holding for testing the scaffold
                Holding.objects.update_or_create(
                    scheme=scheme,
                    as_of_month=as_of_month,
                    security_name="Phase 1 Test Holding",
                    defaults={
                        'weight_pct': 100.0,
                        'sector': 'Financial Services',
                        'source': 'mstarpy'
                    }
                )
                success += 1
                logger.info(f"[{scheme.amfi_code}] Ingested holdings")
                
            except Exception as e:
                logger.error(f"[{scheme.amfi_code}] Failed to ingest holdings: {e}")
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f"=== Holdings Ingestion Complete ===\n"
            f"Total: {total} | Success: {success} | Skipped: {skipped} | Errors: {errors}"
        ))
