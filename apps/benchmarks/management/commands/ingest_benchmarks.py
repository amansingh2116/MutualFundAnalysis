# Management command to ingest benchmark indices and historical NAV data.
#
# ADDING A NEW BENCHMARK
# ─────────────────────────────────────────────────────────────────────────────
# Option A: Edit apps/benchmarks/benchmark_config.py — add an entry to
#           BENCHMARK_CONFIG with the NSE name and optional Yahoo ticker.
#
# Option B: Add a row to documentation/index_benchmark_tickers_available.xlsx
#           (col A = index name, col B = Yahoo Finance ticker).
#           The pipeline picks it up automatically on the next run.
#
# DATA SOURCES (in priority order)
# ─────────────────────────────────────────────────────────────────────────────
#   1. NSE Direct API  (nseindia.com/api/historical/indicesHistory)
#   2. Yahoo Finance   (ticker from Excel sheet or benchmark_config.py)
#
# REMOVING STALE DB RECORDS
# ─────────────────────────────────────────────────────────────────────────────
#   python manage.py ingest_benchmarks --cleanup
#   Deletes BenchmarkIndex records not in BENCHMARK_CONFIG or Excel sheet.

import logging
import time
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from adapters.benchmark_adapter import BenchmarkAdapter
from apps.benchmarks.benchmark_config import BENCHMARK_CONFIG, BenchmarkConfig, REQUIRED_BENCHMARK_NAMES
from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV

logger = logging.getLogger("mfanalysis")


def _bulk_upsert(index, rows, source):
    """
    Bulk-upsert BenchmarkNAV rows using INSERT ... ON CONFLICT DO UPDATE.

    Replaces the old row-by-row update_or_create (which caused 2-hour runtimes
    on CockroachDB Cloud) with a single batched statement.  For 5 000 rows we
    send 10 INSERT statements (batch_size=500) instead of 10 000 queries.

    PostgreSQL / CockroachDB path (production + Docker local_pg):
        Uses update_conflicts=True which emits INSERT … ON CONFLICT DO UPDATE.
        This ensures existing rows get their close/source refreshed on re-runs.

    SQLite path (plain `python manage.py` dev workflow):
        update_conflicts + unique_fields is a PostgreSQL-specific feature and
        raises django.db.utils.NotSupportedError on SQLite.  We fall back to
        ignore_conflicts=True (plain INSERT OR IGNORE) which is safe on SQLite
        and still idempotent — existing rows are simply skipped.

    Returns the number of rows processed.
    """
    objs = [
        BenchmarkNAV(
            index=index,
            date=row['date'],
            close=float(row['close']),
            source=source,
        )
        for row in rows
        if row.get('date') and row.get('close') is not None
    ]
    if not objs:
        return 0

    if connection.vendor == 'sqlite':
        # SQLite does not support ON CONFLICT DO UPDATE via Django's ORM.
        # Use ignore_conflicts=True (INSERT OR IGNORE) as a safe fallback.
        # Existing rows are skipped rather than updated — acceptable for dev.
        logger.debug(
            "[_bulk_upsert] SQLite detected — using ignore_conflicts fallback "
            "(existing rows will not be updated; use Docker/local_pg for full upsert)"
        )
        BenchmarkNAV.objects.bulk_create(
            objs,
            batch_size=500,
            ignore_conflicts=True,
        )
    else:
        # PostgreSQL / CockroachDB: efficient ON CONFLICT DO UPDATE upsert.
        BenchmarkNAV.objects.bulk_create(
            objs,
            batch_size=500,
            update_conflicts=True,
            unique_fields=['index', 'date'],
            update_fields=['close', 'source'],
        )
    return len(objs)


def _load_excel_tickers(base_dir) -> dict[str, str]:
    """Load {UPPER_NAME: ticker} from the Excel sheet. Strips TRI/Index suffixes."""
    try:
        import openpyxl
    except ImportError:
        return {}

    xlsx_path = (
        Path(base_dir) / "documentation/index_benchmark_tickers_available.xlsx"
        if base_dir
        else Path(__file__).resolve().parents[5] / "documentation/index_benchmark_tickers_available.xlsx"
    )
    if not xlsx_path.exists():
        return {}

    result: dict[str, str] = {}
    try:
        wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if not row or len(row) < 2 or not row[0] or not row[1]:
                continue
            raw_name = str(row[0]).strip()
            ticker = str(row[1]).strip()
            # Strip common TRI suffixes
            canon = raw_name
            for suffix in (" TRI", " Total Return Index", " Index"):
                if canon.upper().endswith(suffix.upper()):
                    canon = canon[: -len(suffix)].strip()
                    break
            result[canon.upper()] = ticker
        wb.close()
    except Exception as exc:
        logger.warning("ingest_benchmarks: Excel load failed: %s", exc)
    return result


class Command(BaseCommand):
    help = (
        "Ingest benchmark NAV history for the benchmarks listed in "
        "apps/benchmarks/benchmark_config.py (or the Excel sheet). "
        "Only those benchmarks are processed — all others are ignored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-fetch all data even for up-to-date benchmarks.",
        )
        parser.add_argument(
            "--index",
            type=str,
            default=None,
            help="Only ingest a specific benchmark (partial name match, case-insensitive).",
        )
        parser.add_argument(
            "--since",
            type=str,
            default=None,
            help=(
                "Earliest date to fetch when a benchmark has NO existing history "
                "(format: YYYY-MM-DD). Defaults to 2000-01-01. "
                "Use e.g. --since 2015-01-01 for a faster initial setup. "
                "Ignored for benchmarks that already have data in DB "
                "(incremental fetch always resumes from last stored date)."
            ),
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help=(
                "Delete BenchmarkIndex records (and all their NAV history) "
                "that are NOT in the current required benchmarks list."
            ),
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        filter_name = options.get("index", None)
        do_cleanup = options.get("cleanup", False)

        # Parse --since date (only used when a benchmark has no existing data)
        since_str = options.get("since", None)
        if since_str:
            try:
                from datetime import datetime as _dt
                since_date = _dt.strptime(since_str, "%Y-%m-%d").date()
            except ValueError:
                self.stderr.write(f"Invalid --since date '{since_str}'. Use YYYY-MM-DD.")
                return
        else:
            since_date = None  # will default to 2000-01-01 per start_year below

        base_dir = getattr(settings, "BASE_DIR", None)

        # ── Step 1: Load Excel tickers ─────────────────────────────────────────
        excel_tickers = _load_excel_tickers(base_dir)
        self.stdout.write(f"Loaded {len(excel_tickers)} ticker(s) from Excel sheet.")

        # ── Step 2: Build merged required-benchmarks set ───────────────────────
        # Start with BENCHMARK_CONFIG; Excel sheet can only provide/update tickers
        # for benchmarks already listed in BENCHMARK_CONFIG — it does NOT add new ones.
        # To add a new benchmark, edit BENCHMARK_CONFIG directly.
        required: dict[str, BenchmarkConfig] = dict(BENCHMARK_CONFIG)
        excel_only_count = 0
        for upper_name, ticker in excel_tickers.items():
            # Only update ticker for benchmarks already in BENCHMARK_CONFIG
            existing_key = next((k for k in required if k.upper() == upper_name), None)
            if existing_key and not required[existing_key].yahoo_ticker and ticker:
                required[existing_key] = BenchmarkConfig(
                    nse_name=required[existing_key].nse_name,
                    yahoo_ticker=ticker,
                    description=required[existing_key].description,
                )
                excel_only_count += 1

        required_upper = frozenset(k.upper() for k in required)
        self.stdout.write(
            f"Required benchmarks: {len(required)} "
            f"({excel_only_count} ticker(s) filled in from Excel)"
        )

        # ── Step 3 (optional): Cleanup unrequired DB records ──────────────────
        if do_cleanup:
            all_db = BenchmarkIndex.objects.all()
            to_delete = [b for b in all_db if b.name.upper() not in required_upper]
            if to_delete:
                count = len(to_delete)
                names = [b.name for b in to_delete]
                BenchmarkIndex.objects.filter(pk__in=[b.pk for b in to_delete]).delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Cleanup: deleted {count} BenchmarkIndex records not in required list:"
                    )
                )
                for n in sorted(names):
                    self.stdout.write(f"  - {n}")
            else:
                self.stdout.write("Cleanup: nothing to delete — DB is already clean.")

        # ── Step 4: Ensure BenchmarkIndex records exist for all required ───────
        for name, cfg in required.items():
            obj = BenchmarkIndex.objects.filter(name__iexact=name).first()
            if obj is None:
                obj = BenchmarkIndex.objects.create(
                    name=name,
                    nse_type_str=cfg.nse_name or name,
                    yahoo_ticker=cfg.yahoo_ticker,
                    description=cfg.description,
                    is_active=True,
                )
            else:
                # Fill in missing fields without overwriting existing data
                updated = False
                if not obj.nse_type_str and cfg.nse_name:
                    obj.nse_type_str = cfg.nse_name
                    updated = True
                if not obj.description and cfg.description:
                    obj.description = cfg.description
                    updated = True
                # Excel ticker always takes precedence over code-defined ticker
                excel_ticker = excel_tickers.get(name.upper(), "")
                best = excel_ticker or cfg.yahoo_ticker
                if best and best != obj.yahoo_ticker:
                    obj.yahoo_ticker = best
                    updated = True
                if updated:
                    obj.save()

        # ── Step 5: Fetch NAV history ──────────────────────────────────────────
        today = date.today()
        cutoff_date = today - timedelta(days=7)
        start_year = 2000

        # Build queryset: all BenchmarkIndex whose name (upper) is in our required set
        qs = [b for b in BenchmarkIndex.objects.all() if b.name.upper() in required_upper]

        if filter_name:
            qs = [b for b in qs if filter_name.lower() in b.name.lower()]
            self.stdout.write(self.style.WARNING(f"Filtering to: '{filter_name}'"))

        adapter = BenchmarkAdapter()
        skipped = fetched_nse = fetched_yf = failed = 0

        for bench in sorted(qs, key=lambda b: b.name):
            cfg = required.get(bench.name) or required.get(
                next((k for k in required if k.upper() == bench.name.upper()), None), None
            )
            best_ticker = (
                excel_tickers.get(bench.name.upper())
                or (cfg.yahoo_ticker if cfg else "")
                or bench.yahoo_ticker
                or ""
            )

            # ── Skip if already up-to-date ───────────────────────────────────
            if not force:
                latest = bench.nav_history.order_by("-date").first()
                if latest and latest.date >= cutoff_date:
                    self.stdout.write(f"  SKIP  {bench.name} (up to {latest.date})")
                    skipped += 1
                    continue

            self.stdout.write(f"  FETCH {bench.name} (ticker={best_ticker or 'none'})")

            # ── Source 1: NSE Direct API ──────────────────────────────────────
            nse_name = (cfg.nse_name if cfg else "") or bench.nse_type_str or bench.name

            latest = bench.nav_history.order_by("-date").first()
            if latest:
                start = latest.date + timedelta(days=1)
            elif since_date:
                start = since_date
            else:
                start = date(start_year, 1, 1)

            nse_rows_list = []
            nse_ok = False
            while start < today:
                end = min(date(start.year + 1, 1, 1) - timedelta(days=1), today)
                try:
                    chunk = adapter.fetch_index_history(nse_name, start, end)
                except Exception as exc:
                    logger.debug("NSE error %s %s–%s: %s", bench.name, start, end, exc)
                    chunk = []

                if chunk:
                    nse_rows_list.extend(chunk)
                    start = end + timedelta(days=1)
                    nse_ok = True
                else:
                    break  # NSE failed for this chunk — fall through to yfinance

            if nse_ok and nse_rows_list:
                saved = _bulk_upsert(bench, nse_rows_list, "nse")
                self.stdout.write(f"    NSE: {saved} rows saved")
                fetched_nse += 1
                continue

            # ── Source 2: Yahoo Finance ───────────────────────────────────────
            if best_ticker:
                try:
                    yf_rows = adapter.fetch_yfinance_history(best_ticker, start)
                except Exception as exc:
                    logger.warning("yfinance failed %s (%s): %s", bench.name, best_ticker, exc)
                    yf_rows = []

                if yf_rows:
                    saved = _bulk_upsert(bench, yf_rows, "yfinance")
                    if saved:
                        self.stdout.write(f"    yfinance ({best_ticker}): {saved} rows saved")
                        fetched_yf += 1
                        continue

            self.stdout.write(self.style.WARNING(f"    NO DATA: {bench.name}"))
            failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Skipped={skipped}  NSE={fetched_nse}  "
                f"yfinance={fetched_yf}  no_data={failed}"
            )
        )

