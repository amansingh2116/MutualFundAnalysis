"""
Management command: compute_analytics

Triggers the central analytics engine for all active schemes.
Runs nightly after NAV ingestion.
"""
import logging
from django.core.management.base import BaseCommand
from apps.funds.models import Scheme
from apps.analytics.engine import compute_all_metrics

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = 'Computes trailing, calendar, rolling returns and risk metrics for schemes'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, help='Limit number of schemes to process')
        parser.add_argument('--amfi', type=str, help='Process specific AMFI code only')

    def handle(self, *args, **options):
        limit = options['limit']
        amfi = options['amfi']

        self.stdout.write(self.style.NOTICE("=== Starting Analytics Computation ==="))

        qs = Scheme.objects.filter(is_active=True)
        
        if amfi:
            qs = qs.filter(amfi_code=amfi)
            
        if limit:
            qs = qs[:limit]

        total = qs.count()
        success = 0
        errors = 0

        self.stdout.write(f"Targeting {total} schemes...")

        for scheme in qs:
            try:
                compute_all_metrics(scheme)
                success += 1
            except Exception as e:
                logger.error(f"[{scheme.amfi_code}] Analytics computation failed: {e}")
                errors += 1

        self.stdout.write(self.style.SUCCESS(
            f"=== Analytics Computation Complete ===\n"
            f"Total: {total} | Success: {success} | Errors: {errors}"
        ))
