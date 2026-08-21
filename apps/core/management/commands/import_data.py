"""
management/commands/import_data.py
=====================================
Import a data snapshot archive produced by `export_data` into the local database.

Designed for:
  1. Researchers who want a full local dataset for notebooks / analysis
  2. Developers who want a populated local Postgres without running the pipeline
  3. Any new deployment that needs real data seeded

Usage:
    # Import everything from an archive
    docker compose exec web python manage.py import_data --file /app/data_snapshot.tar.gz

    # Preview what's in the archive without importing
    docker compose exec web python manage.py import_data --file /app/data_snapshot.tar.gz --dry-run

    # Import only specific tables
    docker compose exec web python manage.py import_data \\
        --file /app/data_snapshot.tar.gz \\
        --tables funds.Scheme,funds.FundScreenerSnapshot

    # Wipe existing local data before import (full replacement)
    docker compose exec web python manage.py import_data \\
        --file /app/data_snapshot.tar.gz --wipe

Behaviour:
    - Default mode: UPSERT (update existing rows by PK, insert new ones)
    - --wipe mode: DELETE existing rows then bulk_create (faster for first-time import)
    - FK ordering is read from the archive's manifest.json (same order as export)
    - Progress is printed per-table with row counts
"""

import gzip
import json
import os
import tarfile
import tempfile
import time
from decimal import Decimal
from datetime import datetime, date

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.utils import IntegrityError


def _cast_value(value, field):
    """
    Convert JSON-decoded values (str, float, etc.) back to Python types
    expected by the Django field.
    """
    if value is None:
        return None

    field_type = field.get_internal_type()

    if field_type == "DecimalField":
        return Decimal(str(value)) if value is not None else None

    if field_type == "DateField" and isinstance(value, str):
        return date.fromisoformat(value)

    if field_type in ("DateTimeField",) and isinstance(value, str):
        return datetime.fromisoformat(value)

    return value


class Command(BaseCommand):
    help = "Import a data_snapshot.tar.gz archive (from export_data) into the local database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the .tar.gz archive inside the container",
        )
        parser.add_argument(
            "--tables",
            default="",
            help="Comma-separated app_label.ModelName list to import (default: all in archive)",
        )
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete existing local rows before import (full replacement)",
        )
        parser.add_argument(
            "--chunk",
            type=int,
            default=500,
            help="Rows per bulk_create batch (default: 500)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show archive contents and row counts without importing",
        )
        parser.add_argument(
            "--db",
            default="default",
            help="Django DB alias to import into (default: 'default')",
        )

    def handle(self, *args, **options):
        archive_path = options["file"]
        chunk_size = options["chunk"]
        wipe = options["wipe"]
        dry_run = options["dry_run"]
        db_alias = options["db"]

        if not os.path.exists(archive_path):
            raise CommandError(f"Archive not found: {archive_path}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no data will be written.\n"))

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Extract archive
            self.stdout.write(f"Extracting {archive_path}…")
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmpdir)

            # 2. Read manifest
            manifest_path = os.path.join(tmpdir, "manifest.json")
            if not os.path.exists(manifest_path):
                raise CommandError("Archive is missing manifest.json — may be corrupt or wrong format.")

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            exported_at = manifest.get("exported_at", "unknown")
            self.stdout.write(f"Archive exported at: {exported_at}")
            self.stdout.write(f"Tables in archive:   {len(manifest['tables'])}\n")

            # 3. Filter tables if requested
            filter_set = set()
            if options["tables"]:
                filter_set = {t.strip() for t in options["tables"].split(",") if t.strip()}

            tables_to_import = [
                t for t in manifest["tables"]
                if not filter_set or t["key"] in filter_set
            ]

            if dry_run:
                self.stdout.write(f"{'Table':<45} {'Rows':>10}  {'File'}")
                self.stdout.write("-" * 75)
                for entry in tables_to_import:
                    self.stdout.write(
                        f"  {entry['key']:<43} {entry['rows']:>10,}  {entry['file']}"
                    )
                total = sum(t["rows"] for t in tables_to_import)
                self.stdout.write("-" * 75)
                self.stdout.write(f"  {'TOTAL':<43} {total:>10,}")
                return

            # 4. Import each table
            total_written = 0
            start_all = time.time()

            for entry in tables_to_import:
                table_key = entry["key"]
                file_path = os.path.join(tmpdir, entry["file"])

                if not os.path.exists(file_path):
                    self.stderr.write(self.style.WARNING(f"  ⚠ Missing file for {table_key}, skipping"))
                    continue

                try:
                    app_label, model_name = table_key.split(".")
                    Model = apps.get_model(app_label, model_name)
                except (ValueError, LookupError) as exc:
                    self.stderr.write(self.style.WARNING(f"  ⚠ Unknown model {table_key}: {exc}"))
                    continue

                written = self._import_table(
                    Model=Model,
                    file_path=file_path,
                    db_alias=db_alias,
                    chunk_size=chunk_size,
                    wipe=wipe,
                    label=table_key,
                    expected_rows=entry.get("rows", 0),
                )
                total_written += written

        elapsed = time.time() - start_all
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"✓ Import complete — {total_written:,} rows in {elapsed:.1f}s"
        ))

    def _import_table(self, Model, file_path, db_alias, chunk_size, wipe, label, expected_rows):
        """Read a gzipped JSONL file and bulk-insert into the local DB."""

        self.stdout.write(f"\n  {label}  ({expected_rows:,} rows expected)")

        # Wipe existing rows if requested
        if wipe:
            deleted, _ = Model.objects.using(db_alias).all().delete()
            self.stdout.write(f"    wiped {deleted:,} local rows")

        # Read fields for type casting
        field_map = {f.attname: f for f in Model._meta.concrete_fields}

        written = 0
        batch = []

        def flush_batch(batch):
            """Upsert or bulk_create the accumulated batch."""
            objects = []
            for row in batch:
                casted = {
                    k: _cast_value(v, field_map[k])
                    for k, v in row.items()
                    if k in field_map
                }
                objects.append(Model(**casted))

            try:
                with transaction.atomic():
                    if wipe:
                        Model.objects.using(db_alias).bulk_create(
                            objects, batch_size=len(objects)
                        )
                    else:
                        update_fields = [
                            f.attname
                            for f in Model._meta.concrete_fields
                            if not f.primary_key
                        ]
                        Model.objects.using(db_alias).bulk_create(
                            objects,
                            batch_size=len(objects),
                            update_conflicts=True,
                            unique_fields=["id"],
                            update_fields=update_fields,
                        )
            except IntegrityError as exc:
                self.stderr.write(
                    self.style.WARNING(f"\n    ⚠ FK/constraint error in batch: {exc}")
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"\n    ✗ Error in batch: {exc}")
                )
                return 0

            return len(objects)

        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                batch.append(row)

                if len(batch) >= chunk_size:
                    written += flush_batch(batch)
                    batch = []
                    pct = min(100, int(written / expected_rows * 100)) if expected_rows else 0
                    self.stdout.write(
                        f"\r    {written:,}/{expected_rows:,} ({pct}%)",
                        ending="",
                    )
                    self.stdout.flush()

        # Flush remainder
        if batch:
            written += flush_batch(batch)

        self.stdout.write(f"\r    ✓ {written:,} rows imported          ")
        return written
