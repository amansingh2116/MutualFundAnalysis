"""
Management command: ingest_aum_snapshots

Snapshots the current AUM for every active scheme into SchemeAumSnapshot.
Run monthly (around the 5th–10th of each month) after ingest_metadata refreshes
the SchemeMeta.aum field from captnemo.

Usage:
    python manage.py ingest_aum_snapshots
    python manage.py ingest_aum_snapshots --date 2025-07-01   # specific month
    python manage.py ingest_aum_snapshots --force             # overwrite existing
"""
import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone

from decimal import Decimal
from django.db.models import Sum

from apps.funds.models import Scheme, SchemeAumSnapshot
from apps.holdings.models import Holding

logger = logging.getLogger('mfanalysis')


class Command(BaseCommand):
    help = 'Snapshot current AUM into SchemeAumSnapshot (monthly).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date', type=str, default=None,
            help='Snapshot date YYYY-MM-01 (defaults to first of current month)'
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite existing snapshot for this month'
        )
        parser.add_argument(
            '--amfi', type=str, default=None,
            help='Process specific AMFI code only (for testing)'
        )

    def handle(self, *args, **options):
        target_date_str = options['date']
        if target_date_str:
            as_of_month = date.fromisoformat(target_date_str)
        else:
            today       = timezone.localdate()
            as_of_month = date(today.year, today.month, 1)

        force   = options['force']
        amfi    = options['amfi']

        self.stdout.write(
            self.style.NOTICE(f'=== AUM Snapshot: {as_of_month} ===')
        )

        qs = Scheme.objects.filter(is_active=True).select_related('meta', 'screener_snapshot')
        if amfi:
            qs = qs.filter(amfi_code=amfi)

        total   = 0
        saved   = 0
        skipped = 0
        no_aum  = 0

        for scheme in qs.iterator(chunk_size=500):
            total += 1
            meta = getattr(scheme, 'meta', None)

            aum_value = getattr(meta, 'aum', None) or scheme.aum_cr
            source = 'captnemo'

            # Fallback 1: check FundScreenerSnapshot
            if aum_value is None:
                snap = getattr(scheme, 'screener_snapshot', None)
                if snap and snap.aum_cr:
                    aum_value = snap.aum_cr
                    source = 'screener'

            # Fallback 2: check sum of holding market values (INR / 1e7 = Cr)
            if aum_value is None:
                mkt_sum = Holding.objects.filter(
                    scheme=scheme, as_of_month=as_of_month, market_value__isnull=False
                ).aggregate(total=Sum('market_value'))['total']
                if mkt_sum and mkt_sum > 0:
                    aum_value = round(Decimal(str(mkt_sum)) / Decimal('10000000'), 2)
                    source = 'morningstar_holdings'

            if aum_value is None:
                no_aum += 1
                continue

            if not force:
                if SchemeAumSnapshot.objects.filter(
                    scheme=scheme, as_of_month=as_of_month
                ).exists():
                    skipped += 1
                    continue

            SchemeAumSnapshot.objects.update_or_create(
                scheme=scheme,
                as_of_month=as_of_month,
                defaults={'aum_cr': aum_value, 'source': source},
            )
            saved += 1

        self.stdout.write(self.style.SUCCESS(
            f'AUM Snapshot done | Month={as_of_month} | '
            f'Total={total} | Saved={saved} | Skipped={skipped} | No AUM={no_aum}'
        ))
