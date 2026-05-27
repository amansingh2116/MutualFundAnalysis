# Management command to ingest benchmark indices and historical NAV data

from django.core.management.base import BaseCommand
from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
from adapters.benchmark_adapter import BenchmarkAdapter
from datetime import date, timedelta

class Command(BaseCommand):
    help = "Ingest benchmark indices and historical NAV data."

    def handle(self, *args, **options):
        adapter = BenchmarkAdapter()
        # ---- Fetch live index list and ensure BenchmarkIndex records exist ----
        live_indices = adapter.fetch_all_indices_live()
        for item in live_indices:
            name = item.get('index')
            if not name:
                continue
            BenchmarkIndex.objects.get_or_create(
                name=name,
                defaults={
                    'description': item.get('last', ''),
                },
            )
        # ---- Fetch historical NAV for each benchmark ----
        today = date.today()
        # start year chosen to cover typical mutual fund history
        start_year = 2000
        for bench in BenchmarkIndex.objects.all():
            self.stdout.write(f"Fetching history for {bench.name}")
            start = date(start_year, 1, 1)
            while start < today:
                end = min(date(start.year + 1, 1, 1) - timedelta(days=1), today)
                try:
                    rows = adapter.fetch_index_history(bench.name, start, end)
                except Exception as e:
                    self.stderr.write(f"NSE fetch error for {bench.name} {start}–{end}: {e}")
                    # fallback to yfinance if NSE fails entirely for this range
                    rows = []
                if not rows:
                    # Attempt yfinance fallback using the mapped Yahoo ticker if available
                    if bench.yahoo_ticker:
                        self.stdout.write(f"  Falling back to yfinance for {bench.yahoo_ticker}")
                        rows_df = adapter.fetch_yfinance_fallback(bench.yahoo_ticker)
                        if rows_df is not None:
                            for nav_date, close in rows_df['close'].items():
                                BenchmarkNAV.objects.update_or_create(
                                    index=bench,
                                    date=nav_date,
                                    defaults={"close": float(close)},
                                )
                    start = end + timedelta(days=1)
                    continue
                for row in rows:
                    nav_date = row.get('date')
                    close = row.get('close')
                    if nav_date and close is not None:
                        BenchmarkNAV.objects.update_or_create(
                            index=bench,
                            date=nav_date,
                            defaults={"close": float(close)},
                        )
                start = end + timedelta(days=1)
        self.stdout.write(self.style.SUCCESS("Benchmark ingestion completed."))
