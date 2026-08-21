"""
management/commands/export_data.py
=====================================
Export all application data to a portable compressed archive (.tar.gz)
that any user can download and import to run the app locally with real data.

Each table is serialised as newline-delimited JSON (JSONL) — one file per model.
The archive is self-describing: it includes a manifest.json with table names,
row counts, schema version, and export timestamp.

Usage:
    # Export everything (inside Docker container)
    docker compose exec web python manage.py export_data

    # Export to a specific path
    docker compose exec web python manage.py export_data --output /app/data_snapshot.tar.gz

    # Skip NAV history (produces a much smaller file for testing)
    docker compose exec web python manage.py export_data --skip-nav

    # Export only specific tables
    docker compose exec web python manage.py export_data \\
        --tables funds.Scheme,funds.FundScreenerSnapshot,benchmarks.BenchmarkReturns

Output on host (volume-mounted):
    ./data_snapshot.tar.gz      (~50–200 MB compressed, depending on NAV history)

The archive can then be shared and imported with:
    docker compose exec web python manage.py import_data --file /app/data_snapshot.tar.gz
"""

import gzip
import json
import os
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models as django_models


# ---------------------------------------------------------------------------
# Default export order — parents before children (FK safety for import)
# ---------------------------------------------------------------------------
DEFAULT_EXPORT_ORDER = [
    "core.DataProvenance",
    "core.LearnPDFGuide",
    "core.LearnBlogPost",
    "benchmarks.BenchmarkIndex",
    "benchmarks.BenchmarkNAV",
    "benchmarks.BenchmarkReturns",
    "benchmarks.UserBenchmarkProfile",
    "benchmarks.UserMarketStripProfile",
    "benchmarks.UserAPIKey",
    "funds.Scheme",
    "funds.SchemeMeta",
    "funds.FundScreenerSnapshot",
    "funds.FundModelScore",
    "funds.CategorySnapshot",
    "analytics.TrailingReturn",
    "analytics.CalendarReturn",
    "analytics.RollingReturn",
    "analytics.RiskMetrics",
    "funds.NAVHistory",
    "holdings.Holding",
    "holdings.SectorAllocation",
    "holdings.MarketCapAllocation",
    "portfolio.Portfolio",
    "portfolio.Transaction",
    "portfolio.SavedStrategy",
    "recommendations.RecommendationProfile",
    "recommendations.FundRecommendation",
]

# Tables that are read-only / public data (safe to include by default)
# User-specific tables (Portfolio, Transaction, SavedStrategy, etc.) are
# included by default but can be excluded with --no-user-data.
USER_DATA_TABLES = {
    "portfolio.Portfolio",
    "portfolio.Transaction",
    "portfolio.SavedStrategy",
    "recommendations.RecommendationProfile",
    "recommendations.FundRecommendation",
    "benchmarks.UserBenchmarkProfile",
    "benchmarks.UserMarketStripProfile",
    "benchmarks.UserAPIKey",
}


def _json_default(obj):
    """JSON serialiser for non-standard types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


class Command(BaseCommand):
    help = "Export all app data to a portable .tar.gz archive for local distribution."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="/app/data_snapshot.tar.gz",
            help="Output archive path inside the container (default: /app/data_snapshot.tar.gz)",
        )
        parser.add_argument(
            "--tables",
            default="",
            help="Comma-separated app_label.ModelName list to export (default: all)",
        )
        parser.add_argument(
            "--skip-nav",
            action="store_true",
            help="Skip NAVHistory to produce a smaller file (~5 MB vs ~200 MB)",
        )
        parser.add_argument(
            "--no-user-data",
            action="store_true",
            help="Exclude user-specific tables (Portfolio, Recommendations, etc.)",
        )
        parser.add_argument(
            "--chunk",
            type=int,
            default=1000,
            help="Rows per read batch (default: 1000)",
        )
        parser.add_argument(
            "--db",
            default="default",
            help="Django DB alias to export from (default: 'default')",
        )

    def handle(self, *args, **options):
        output_path = options["output"]
        chunk_size = options["chunk"]
        db_alias = options["db"]
        skip_nav = options["skip_nav"]
        no_user_data = options["no_user_data"]

        # Determine table list
        if options["tables"]:
            export_list = [t.strip() for t in options["tables"].split(",") if t.strip()]
        else:
            export_list = list(DEFAULT_EXPORT_ORDER)

        if skip_nav:
            export_list = [t for t in export_list if t != "funds.NAVHistory"]
            self.stdout.write(self.style.WARNING("  ⚠ Skipping funds.NAVHistory (--skip-nav)"))

        if no_user_data:
            export_list = [t for t in export_list if t not in USER_DATA_TABLES]
            self.stdout.write(self.style.WARNING("  ⚠ Excluding user-specific tables"))

        self.stdout.write(f"\nExporting {len(export_list)} tables → {output_path}\n")

        manifest = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format_version": "1.0",
            "tables": [],
        }

        start_all = time.time()

        with tempfile.TemporaryDirectory() as tmpdir:
            for table_key in export_list:
                try:
                    app_label, model_name = table_key.split(".")
                    Model = apps.get_model(app_label, model_name)
                except (ValueError, LookupError) as exc:
                    self.stderr.write(self.style.WARNING(f"  ⚠ Unknown model {table_key}: {exc}"))
                    continue

                rows_written = self._export_table(
                    Model=Model,
                    db_alias=db_alias,
                    chunk_size=chunk_size,
                    tmpdir=tmpdir,
                    label=table_key,
                )

                manifest["tables"].append({
                    "key": table_key,
                    "db_table": Model._meta.db_table,
                    "rows": rows_written,
                    "file": f"{table_key.replace('.', '__')}.jsonl.gz",
                })

            # Write manifest
            manifest_path = os.path.join(tmpdir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            # Bundle everything into a tar.gz
            self.stdout.write(f"\nCreating archive at {output_path}…")
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
            with tarfile.open(output_path, "w:gz") as tar:
                tar.add(manifest_path, arcname="manifest.json")
                for entry in manifest["tables"]:
                    file_path = os.path.join(tmpdir, entry["file"])
                    if os.path.exists(file_path):
                        tar.add(file_path, arcname=entry["file"])

        # Print summary
        elapsed = time.time() - start_all
        size_mb = os.path.getsize(output_path) / 1_048_576
        total_rows = sum(t["rows"] for t in manifest["tables"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"✓ Export complete: {output_path}\n"
            f"  Tables: {len(manifest['tables'])}  |  Rows: {total_rows:,}  |  "
            f"Size: {size_mb:.1f} MB  |  Time: {elapsed:.1f}s"
        ))
        self.stdout.write("\nTo copy the archive to your host machine:")
        container = "mutualfundanalysis-web-1"
        host_path = output_path.replace("/app/", "./")
        self.stdout.write(f"  docker cp {container}:{output_path} {host_path}")

    def _export_table(self, Model, db_alias, chunk_size, tmpdir, label):
        """Serialise all rows of Model to a gzipped JSONL file."""
        filename = f"{label.replace('.', '__')}.jsonl.gz"
        filepath = os.path.join(tmpdir, filename)

        total = Model.objects.using(db_alias).count()
        self.stdout.write(f"  {label:<45} {total:>8,} rows", ending="")
        self.stdout.flush()

        if total == 0:
            self.stdout.write("  (empty)")
            open(filepath, "wb").close()  # create empty file
            return 0

        written = 0
        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            offset = 0
            while True:
                batch = list(
                    Model.objects.using(db_alias)
                    .order_by("pk")
                    .values()[offset: offset + chunk_size]
                )
                if not batch:
                    break
                for row in batch:
                    f.write(json.dumps(row, default=_json_default) + "\n")
                written += len(batch)
                offset += chunk_size

        self.stdout.write(f"  ✓")
        return written
