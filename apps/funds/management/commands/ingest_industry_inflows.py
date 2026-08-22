"""
Management command: ingest_industry_inflows

Fetches AMFI monthly industry-level mutual fund inflow/outflow data and saves
it to the IndustryInflow model for historical trend charts.

Source: AMFI publishes monthly data at:
  https://www.amfiindia.com/research-information/mf-data

The data is available as a JSON API used by the AMFI website.

Usage:
    python manage.py ingest_industry_inflows              # current month
    python manage.py ingest_industry_inflows --months 6   # last 6 months
    python manage.py ingest_industry_inflows --dry-run    # preview only
"""
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.funds.models import IndustryInflow

logger = logging.getLogger('mfanalysis')

# AMFI data endpoint — returns monthly industry-level statistics
# This URL pattern has been stable since 2020.
_AMFI_BASE = 'https://www.amfiindia.com/modules/ProductDetails'

# Public JSON API used by AMFI website (observed via browser devtools)
_AMFI_INFLOW_API = (
    'https://www.amfiindia.com/modules/ReportSummary'
    '?mf=0&ty=0&sc=1&frm={from_date}&to={to_date}'
)

# Category name normalization map (AMFI names -> our standard labels)
_CAT_MAP = {
    'income / debt oriented schemes':     'Debt',
    'debt':                                'Debt',
    'growth / equity oriented schemes':   'Equity',
    'equity':                              'Equity',
    'hybrid schemes':                      'Hybrid',
    'hybrid':                              'Hybrid',
    'solution oriented schemes':           'Solution Oriented',
    'solution oriented':                   'Solution Oriented',
    'other schemes':                       'Other',
    'other':                               'Other',
    'exchange traded fund':                'ETF / Index',
    'etf':                                 'ETF / Index',
    'fund of funds investing overseas':    'FOF - Overseas',
    'fund of funds':                       'FOF - Overseas',
}


def _normalize_category(name: str) -> str:
    key = name.strip().lower()
    for pattern, label in _CAT_MAP.items():
        if pattern in key:
            return label
    return name.strip().title()


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = 'Fetch AMFI monthly industry inflow data and save to IndustryInflow.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months', type=int, default=1,
            help='Number of recent months to fetch (default: 1 = current month)'
        )
        parser.add_argument(
            '--date', type=str, default=None,
            help='Specific month to fetch (YYYY-MM-01). Overrides --months.'
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite existing records for fetched months'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would be saved without writing to DB'
        )

    def handle(self, *args, **options):
        months   = options['months']
        force    = options['force']
        dry_run  = options['dry_run']

        today = timezone.localdate()

        if options['date']:
            target_months = [date.fromisoformat(options['date'])]
        else:
            # Generate list of month-starts going back `months` months
            target_months = []
            for i in range(months):
                # Subtract i months from current month
                d = today.replace(day=1)
                for _ in range(i):
                    d = (d - timedelta(days=1)).replace(day=1)
                target_months.append(d)

        self.stdout.write(
            self.style.NOTICE(
                f'=== Industry Inflows: fetching {len(target_months)} month(s) ==='
            )
        )

        total_saved = 0
        for month_start in target_months:
            self.stdout.write(f'Fetching {month_start.strftime("%B %Y")} ...')
            rows = self._fetch_month(month_start)
            if not rows:
                self.stdout.write(self.style.WARNING(f'  No data returned for {month_start}'))
                continue

            for row in rows:
                cat      = _normalize_category(row.get('category', ''))
                net_in   = _to_decimal(row.get('net_inflow'))
                gross_p  = _to_decimal(row.get('gross_purchase'))
                gross_r  = _to_decimal(row.get('gross_redemption'))
                aum      = _to_decimal(row.get('aum'))
                folios   = row.get('folio_count')

                if dry_run:
                    self.stdout.write(
                        f'  [DRY RUN] {month_start} | {cat} | '
                        f'Net={net_in} | AUM={aum}'
                    )
                    continue

                if not force:
                    if IndustryInflow.objects.filter(
                        as_of_month=month_start, category_group=cat
                    ).exists():
                        self.stdout.write(f'  Skipped (exists): {cat}')
                        continue

                IndustryInflow.objects.update_or_create(
                    as_of_month=month_start,
                    category_group=cat,
                    defaults={
                        'gross_purchase':   gross_p,
                        'gross_redemption': gross_r,
                        'net_inflow':       net_in,
                        'aum_cr':           aum,
                        'folio_count':      folios,
                    },
                )
                total_saved += 1
                self.stdout.write(f'  Saved: {cat} | Net={net_in} Cr')

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'Industry Inflows complete | Records saved: {total_saved}'
            ))
        else:
            self.stdout.write(self.style.WARNING('Dry run complete. Nothing saved.'))

    def _fetch_month(self, month_start: date) -> list[dict]:
        """
        Attempt to fetch AMFI monthly inflow data for a given month.

        AMFI provides a summary endpoint. If it fails, return fallback structure
        to be populated manually or from a different source.
        """
        # Format: DD-MMM-YYYY
        from_date = month_start.strftime('%d-%b-%Y')
        last_day  = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        to_date   = last_day.strftime('%d-%b-%Y')

        url = _AMFI_INFLOW_API.format(from_date=from_date, to_date=to_date)
        headers = {
            'User-Agent':  'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept':      'application/json, text/plain, */*',
            'Referer':     'https://www.amfiindia.com/',
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Parse AMFI JSON format
            rows = []
            items = data if isinstance(data, list) else data.get('data', [])
            for item in items:
                row = {
                    'category':         item.get('SchemeType') or item.get('category', ''),
                    'gross_purchase':   item.get('Sales')      or item.get('gross_purchase'),
                    'gross_redemption': item.get('Repurchase') or item.get('gross_redemption'),
                    'net_inflow':       item.get('Net')        or item.get('net_inflow'),
                    'aum':              item.get('ClosingAUM') or item.get('aum'),
                    'folio_count':      item.get('Folio')      or item.get('folio_count'),
                }
                if row['category']:
                    rows.append(row)
            if rows:
                return rows
        except Exception as exc:
            logger.warning('AMFI inflow API failed for %s: %s', month_start, exc)

        # Fallback: return empty (operator will need to check AMFI manually)
        return []
