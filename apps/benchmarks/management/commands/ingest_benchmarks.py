# Management command to ingest benchmark indices and historical NAV data

from django.core.management.base import BaseCommand
from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
from adapters.benchmark_adapter import BenchmarkAdapter
from apps.benchmarks.registry import BENCHMARK_DEFINITIONS, fetch_yahoo_history_for_benchmark, primary_yahoo_ticker
from datetime import date, timedelta

class Command(BaseCommand):
    help = "Ingest benchmark indices and historical NAV data."

    def handle(self, *args, **options):
        adapter = BenchmarkAdapter()
        for name, definition in BENCHMARK_DEFINITIONS.items():
            BenchmarkIndex.objects.update_or_create(
                name=name,
                defaults={
                    'nse_type_str': definition.nse_name or name,
                    'yahoo_ticker': primary_yahoo_ticker(name),
                    'description': f"Fallback source: {definition.fallback}" if definition.fallback else '',
                    'is_active': True,
                },
            )

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
        cutoff_date = today - timedelta(days=7)
        # start year chosen to cover typical mutual fund history
        start_year = 2000
        for bench in BenchmarkIndex.objects.all():
            latest_nav = bench.nav_history.order_by('-date').first()
            if latest_nav and latest_nav.date >= cutoff_date:
                self.stdout.write(f"Skipping {bench.name} (already has recent data up to {latest_nav.date})")
                continue

            self.stdout.write(f"Fetching history for {bench.name}")
            start = date(start_year, 1, 1)
            while start < today:
                end = min(date(start.year + 1, 1, 1) - timedelta(days=1), today)
                try:
                    rows = adapter.fetch_index_history(bench.nse_type_str or bench.name, start, end)
                except Exception as e:
                    self.stderr.write(f"NSE fetch error for {bench.name} {start}–{end}: {e}")
                    # fallback to yfinance if NSE fails entirely for this range
                    rows = []
                if not rows:
                    # Attempt yfinance fallback using the mapped Yahoo ticker if available
                    if bench.yahoo_ticker:
                        self.stdout.write(f"  Falling back to yfinance for {bench.yahoo_ticker}")
                        # Fetch the entire history from 'start' to today in one call
                        rows = adapter.fetch_yfinance_history(bench.yahoo_ticker, start)
                        if rows:
                            for row in rows:
                                nav_date = row.get('date')
                                close = row.get('close')
                                if nav_date and close is not None:
                                    BenchmarkNAV.objects.update_or_create(
                                        index=bench,
                                        date=nav_date,
                                        defaults={"close": float(close), "source": "yfinance"},
                                    )
                            # Fast-forward start to today to terminate the loop for this benchmark
                            start = today
                            continue

                    # If yfinance wasn't attempted or returned no data, try registry providers
                    self.stdout.write(f"  Falling back to benchmark registry providers for {bench.name}")
                    series, candidate = fetch_yahoo_history_for_benchmark(bench.name, start_date=start, end_date=today, min_rows=1)
                    rows = [
                        {"date": idx.date(), "close": float(value)}
                        for idx, value in series.items()
                        if start <= idx.date() <= today
                    ]
                    if rows:
                        source = candidate.source if candidate else "registry"
                        for row in rows:
                            BenchmarkNAV.objects.update_or_create(
                                index=bench,
                                date=row["date"],
                                defaults={"close": float(row["close"]), "source": source},
                            )
                    # Fast-forward start to today because we've queried the entire history to today
                    start = today
                    continue
                for row in rows:
                    nav_date = row.get('date')
                    close = row.get('close')
                    if nav_date and close is not None:
                        BenchmarkNAV.objects.update_or_create(
                            index=bench,
                            date=nav_date,
                            defaults={"close": float(close), "source": "nse"},
                        )
                start = end + timedelta(days=1)
        self.stdout.write(self.style.SUCCESS("Benchmark ingestion completed."))
