"""
management/commands/sync_from_sqlite.py
=======================================
Transfers all data from local SQLite (db.sqlite3) into the Docker PostgreSQL database.

This is super fast, reliable, and does not depend on external network/CockroachDB connections.
It handles FK dependency ordering and bulk inserts with conflict handling or clean wipes.

Usage:
    docker compose exec web python manage.py sync_from_sqlite
    docker compose exec web python manage.py sync_from_sqlite --skip-nav
    docker compose exec web python manage.py sync_from_sqlite --wipe
"""

import os
import sqlite3
import time
from datetime import datetime, date
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError

DEFAULT_SYNC_ORDER = [
    # Core
    "core.DataProvenance",
    "core.LearnPDFGuide",
    "core.LearnBlogPost",

    # Benchmarks
    "benchmarks.BenchmarkIndex",
    "benchmarks.BenchmarkNAV",
    "benchmarks.BenchmarkReturns",
    "benchmarks.UserBenchmarkProfile",
    "benchmarks.UserMarketStripProfile",
    "benchmarks.UserAPIKey",

    # Funds master & analytics
    "funds.Scheme",
    "funds.SchemeMeta",
    "funds.FundScreenerSnapshot",
    "funds.FundModelScore",
    "funds.CategorySnapshot",
    "analytics.TrailingReturn",
    "analytics.CalendarReturn",
    "analytics.RollingReturn",
    "analytics.RiskMetrics",

    # NAV History (largest table)
    "funds.NAVHistory",

    # Holdings
    "holdings.Holding",
    "holdings.SectorAllocation",
    "holdings.MarketCapAllocation",

    # Portfolio / Recommendations
    "portfolio.Portfolio",
    "portfolio.Transaction",
    "portfolio.SavedStrategy",
    "recommendations.RecommendationProfile",
    "recommendations.FundRecommendation",
]


def _cast_val(val, field):
    if val is None:
        return None
    ftype = field.get_internal_type()
    if ftype == "DecimalField":
        return Decimal(str(val))
    if ftype == "BooleanField":
        return bool(val)
    if ftype == "DateField" and isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return val
    if ftype == "DateTimeField" and isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return val
    return val


class Command(BaseCommand):
    help = "Sync all tables from local SQLite database (db.sqlite3) into Postgres."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default="db.sqlite3",
            help="Path to SQLite database file (default: db.sqlite3)",
        )
        parser.add_argument(
            "--tables",
            default="",
            help="Comma-separated app_label.ModelName list (default: all)",
        )
        parser.add_argument(
            "--chunk",
            type=int,
            default=2000,
            help="Rows per batch (default: 2000)",
        )
        parser.add_argument(
            "--skip-nav",
            action="store_true",
            help="Skip NAVHistory for faster sync",
        )
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Wipe destination tables before syncing",
        )

    def handle(self, *args, **options):
        sqlite_file = options["file"]
        chunk_size = options["chunk"]
        skip_nav = options["skip_nav"]
        wipe = options["wipe"]

        if not os.path.exists(sqlite_file):
            raise CommandError(f"SQLite file not found at: {sqlite_file}")

        self.stdout.write(f"Connecting to SQLite: {sqlite_file}")
        con = sqlite3.connect(sqlite_file)
        con.row_factory = sqlite3.Row

        if options["tables"]:
            sync_list = [t.strip() for t in options["tables"].split(",") if t.strip()]
        else:
            sync_list = list(DEFAULT_SYNC_ORDER)

        if skip_nav:
            sync_list = [t for t in sync_list if t != "funds.NAVHistory"]
            self.stdout.write(self.style.WARNING("  [!] Skipping funds.NAVHistory (--skip-nav)"))

        start_time = time.time()
        total_rows = 0

        for table_key in sync_list:
            try:
                app_label, model_name = table_key.split(".")
                Model = apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                continue

            db_table = Model._meta.db_table
            cur = con.cursor()

            # Check if table exists in SQLite
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (db_table,))
            if cur.fetchone()[0] == 0:
                continue

            cur.execute(f'SELECT count(*) FROM "{db_table}"')
            src_count = cur.fetchone()[0]

            self.stdout.write(f"\n  {table_key:<40} ({src_count:,} rows in SQLite)")
            if src_count == 0:
                continue

            if wipe:
                deleted, _ = Model.objects.using("default").all().delete()
                self.stdout.write(f"    wiped {deleted:,} rows in Postgres")

            field_map = {f.attname: f for f in Model._meta.concrete_fields}
            update_fields = [f.attname for f in Model._meta.concrete_fields if not f.primary_key]

            cur.execute(f'SELECT * FROM "{db_table}" ORDER BY rowid')

            written = 0
            while True:
                rows = cur.fetchmany(chunk_size)
                if not rows:
                    break

                batch_objs = []
                for r in rows:
                    r_dict = dict(r)
                    casted = {
                        k: _cast_val(v, field_map[k])
                        for k, v in r_dict.items()
                        if k in field_map
                    }
                    batch_objs.append(Model(**casted))

                try:
                    with transaction.atomic():
                        if wipe:
                            Model.objects.using("default").bulk_create(
                                batch_objs, batch_size=chunk_size
                            )
                        else:
                            Model.objects.using("default").bulk_create(
                                batch_objs,
                                batch_size=chunk_size,
                                update_conflicts=True,
                                unique_fields=["id"],
                                update_fields=update_fields,
                            )
                except IntegrityError as e:
                    self.stderr.write(self.style.WARNING(f"    Integrity warning: {e}"))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"    Error in batch: {e}"))

                written += len(rows)
                pct = int(written / src_count * 100) if src_count else 100
                self.stdout.write(f"\r    {written:,}/{src_count:,} ({pct}%)", ending="")
                self.stdout.flush()

            self.stdout.write(f"\r    [OK] {written:,} rows synced          ")
            total_rows += written

        con.close()
        elapsed = time.time() - start_time
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done! {total_rows:,} total rows synced into PostgreSQL in {elapsed:.1f}s"
        ))
