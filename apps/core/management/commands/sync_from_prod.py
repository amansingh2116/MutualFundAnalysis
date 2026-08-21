"""
management/commands/sync_from_prod.py
======================================
Pull production data from CockroachDB (or any PostgreSQL-compatible source)
into the local Docker Postgres database.

Uses a direct psycopg2 connection for reading the source (avoids Django's
DB registration complexity) and Django's ORM bulk_create for writing locally.
Handles FK ordering automatically (parents before children).

Usage:
    docker compose exec web python manage.py sync_from_prod \\
        --url "postgresql://user:pass@host:26257/defaultdb?sslmode=verify-full"

Options:
    --url           Source DATABASE_URL (required)
    --tables        Comma-separated list of app_label.ModelName to sync
                    (default: all app data tables, excludes django_q / auth / sessions)
    --chunk         Rows per bulk_create batch (default: 500)
    --skip-nav      Skip NAVHistory (large table ~5M+ rows) for faster partial syncs
    --wipe          Wipe each local table before syncing (default: upsert by PK)
    --dry-run       Print row counts from source without writing anything

Example — sync everything except raw NAV history:
    docker compose exec web python manage.py sync_from_prod \\
        --url "postgresql://..." --skip-nav

Example — sync only screener and benchmark tables:
    docker compose exec web python manage.py sync_from_prod \\
        --url "postgresql://..." \\
        --tables funds.FundScreenerSnapshot,benchmarks.BenchmarkReturns
"""

import time
import urllib.parse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError
from django.apps import apps


# ---------------------------------------------------------------------------
# Table sync order — respects FK dependency (parents before children)
# ---------------------------------------------------------------------------
DEFAULT_SYNC_ORDER = [
    # ── Core (no FK deps) ───────────────────────────────────────────────
    "core.DataProvenance",
    "core.LearnPDFGuide",
    "core.LearnBlogPost",

    # ── Benchmarks (no FK to funds) ─────────────────────────────────────
    "benchmarks.BenchmarkIndex",
    "benchmarks.BenchmarkNAV",
    "benchmarks.BenchmarkReturns",
    "benchmarks.UserBenchmarkProfile",
    "benchmarks.UserMarketStripProfile",
    "benchmarks.UserAPIKey",

    # ── Funds master (Scheme must come before everything that FKs to it) ─
    "funds.Scheme",
    "funds.SchemeMeta",
    "funds.FundScreenerSnapshot",
    "funds.FundModelScore",
    "funds.CategorySnapshot",

    # ── Analytics (FK → Scheme) ──────────────────────────────────────────
    "analytics.TrailingReturn",
    "analytics.CalendarReturn",
    "analytics.RollingReturn",
    "analytics.RiskMetrics",

    # ── NAV history (FK → Scheme, potentially millions of rows) ──────────
    "funds.NAVHistory",

    # ── Holdings (FK → Scheme) ───────────────────────────────────────────
    "holdings.Holding",
    "holdings.SectorAllocation",
    "holdings.MarketCapAllocation",

    # ── Portfolio / Recommendations (user-facing, small tables) ──────────
    "portfolio.Portfolio",
    "portfolio.Transaction",
    "portfolio.SavedStrategy",
    "recommendations.RecommendationProfile",
    "recommendations.FundRecommendation",
]


def _parse_db_url(url: str) -> dict:
    """Parse a DATABASE_URL into psycopg2 connect() kwargs."""
    url = (
        url.replace("cockroachdb://", "postgresql://", 1)
           .replace("cockroach://", "postgresql://", 1)
    )
    p = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(p.query)

    kwargs = {
        "dbname": p.path.lstrip("/") or "defaultdb",
        "user": urllib.parse.unquote(p.username or ""),
        "password": urllib.parse.unquote(p.password or ""),
        "host": p.hostname or "localhost",
        "port": p.port or 26257,
        "connect_timeout": 15,
    }
    sslmode = qs.get("sslmode", [None])[0]
    if sslmode:
        kwargs["sslmode"] = sslmode
    return kwargs


def _count_rows(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        return cur.fetchone()[0]


def _fetch_rows(conn, table_name: str, offset: int, limit: int) -> list:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT * FROM "{table_name}" ORDER BY id LIMIT %s OFFSET %s',
            [limit, offset],
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


class Command(BaseCommand):
    help = "Sync data from a production CockroachDB/PostgreSQL into the local Docker Postgres."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url", required=True,
            help="Source DATABASE_URL (postgresql:// or cockroachdb://)",
        )
        parser.add_argument(
            "--tables", default="",
            help="Comma-separated app_label.ModelName list (default: all)",
        )
        parser.add_argument(
            "--chunk", type=int, default=500,
            help="Rows per bulk_create batch (default: 500)",
        )
        parser.add_argument(
            "--skip-nav", action="store_true",
            help="Skip NAVHistory for a fast partial sync",
        )
        parser.add_argument(
            "--wipe", action="store_true",
            help="Delete all local rows before syncing",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print row counts from source without writing",
        )

    def handle(self, *args, **options):
        url = options["url"]
        chunk_size = options["chunk"]
        skip_nav = options["skip_nav"]
        wipe = options["wipe"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no data will be written."))

        # 1. Open raw psycopg2 connection to source
        self.stdout.write("Connecting to source database…")
        try:
            import psycopg2
        except ImportError:
            raise CommandError("psycopg2 is not installed.")

        try:
            src_conn = psycopg2.connect(**_parse_db_url(url))
            src_conn.autocommit = True
        except Exception as exc:
            raise CommandError(
                f"Cannot connect to source: {exc}\n"
                "Check --url, credentials, and network/firewall access."
            ) from exc

        try:
            with src_conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
            self.stdout.write(self.style.SUCCESS(f"  ✓ Connected: {version[:80]}"))
        except Exception as exc:
            src_conn.close()
            raise CommandError(f"Connection test failed: {exc}") from exc

        # 2. Determine tables
        if options["tables"]:
            sync_list = [t.strip() for t in options["tables"].split(",") if t.strip()]
        else:
            sync_list = list(DEFAULT_SYNC_ORDER)

        if skip_nav:
            sync_list = [t for t in sync_list if t != "funds.NAVHistory"]
            self.stdout.write(self.style.WARNING("  ⚠ Skipping funds.NAVHistory (--skip-nav)"))

        # 3. Sync each table
        total_written = 0
        start_all = time.time()

        try:
            for table_key in sync_list:
                try:
                    app_label, model_name = table_key.split(".")
                    Model = apps.get_model(app_label, model_name)
                except (ValueError, LookupError) as exc:
                    self.stderr.write(self.style.WARNING(
                        f"  ⚠ Skipping unknown model {table_key}: {exc}"
                    ))
                    continue

                written = self._sync_table(
                    Model=Model,
                    src_conn=src_conn,
                    chunk_size=chunk_size,
                    wipe=wipe,
                    dry_run=dry_run,
                    label=table_key,
                )
                total_written += written
        finally:
            src_conn.close()

        elapsed = time.time() - start_all
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"{'[DRY RUN] ' if dry_run else ''}Done — "
            f"{total_written:,} rows processed in {elapsed:.1f}s"
        ))

    def _sync_table(self, Model, src_conn, chunk_size, wipe, dry_run, label):
        """Copy all rows from Model on src_conn into the local 'default' DB."""
        db_table = Model._meta.db_table

        try:
            src_count = _count_rows(src_conn, db_table)
        except Exception as exc:
            self.stderr.write(self.style.WARNING(f"  ⚠ {label}: cannot count — {exc}"))
            return 0

        self.stdout.write(f"\n  {label}  ({src_count:,} rows in source)")

        if dry_run:
            local_count = Model.objects.using("default").count()
            self.stdout.write(f"    local: {local_count:,} rows")
            return src_count

        if src_count == 0:
            self.stdout.write("    → empty, skipping")
            return 0

        if wipe:
            deleted, _ = Model.objects.using("default").all().delete()
            self.stdout.write(f"    wiped {deleted:,} local rows")

        update_fields = [
            f.attname
            for f in Model._meta.concrete_fields
            if not f.primary_key
        ]

        written = 0
        offset = 0

        while True:
            try:
                batch_dicts = _fetch_rows(src_conn, db_table, offset, chunk_size)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f"\n    ✗ Fetch error at offset {offset}: {exc}"
                ))
                break

            if not batch_dicts:
                break

            objects = [Model(**row) for row in batch_dicts]

            try:
                with transaction.atomic():
                    if wipe:
                        Model.objects.using("default").bulk_create(
                            objects, batch_size=chunk_size
                        )
                    else:
                        Model.objects.using("default").bulk_create(
                            objects,
                            batch_size=chunk_size,
                            update_conflicts=True,
                            unique_fields=["id"],
                            update_fields=update_fields,
                        )
            except IntegrityError as exc:
                self.stderr.write(self.style.WARNING(
                    f"\n    ⚠ FK violation in batch offset={offset}: {exc}"
                ))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(
                    f"\n    ✗ Error in batch offset={offset}: {exc}"
                ))

            written += len(batch_dicts)
            offset += chunk_size

            pct = min(100, int(written / src_count * 100)) if src_count else 100
            self.stdout.write(f"\r    {written:,}/{src_count:,} ({pct}%)", ending="")
            self.stdout.flush()

        self.stdout.write(f"\r    ✓ {written:,} rows synced          ")
        return written
