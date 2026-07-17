"""
Management command: backfill_rolling_medians
Reads each FundScreenerSnapshot.rolling_returns_json and extracts per-period
median values into the new scalar columns (rolling_median_1y/3y/5y/7y_pct).

Run after migration or after populate_screener to ensure columns are up-to-date.

Usage:
    python manage.py backfill_rolling_medians
    python manage.py backfill_rolling_medians --category "Mid Cap Fund"
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand

from apps.funds.models import FundScreenerSnapshot


class Command(BaseCommand):
    help = "Backfill rolling_median_* columns from rolling_returns_json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            help="Limit to a single sub-category (optional).",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=500,
            help="Bulk-update batch size (default 500).",
        )

    def handle(self, *args, **options):
        qs = FundScreenerSnapshot.objects.all()
        cat = options.get("category")
        if cat:
            qs = qs.filter(scheme_sub_category=cat)
            self.stdout.write(f"Filtering to category: {cat}")

        total = qs.count()
        self.stdout.write(f"Processing {total} snapshots...")

        def _dec(v):
            if v is None:
                return None
            try:
                return Decimal(f"{float(v):.4f}")
            except (InvalidOperation, TypeError, ValueError):
                return None

        BATCH = options["batch"]
        to_update = []
        done = 0

        for snap in qs.only(
            "id",
            "rolling_returns_json",
            "rolling_median_1y_pct",
            "rolling_median_3y_pct",
            "rolling_median_5y_pct",
            "rolling_median_7y_pct",
        ).iterator(chunk_size=BATCH):
            rj = snap.rolling_returns_json or {}
            snap.rolling_median_1y_pct = _dec(rj.get("1Y", {}).get("median"))
            snap.rolling_median_3y_pct = _dec(rj.get("3Y", {}).get("median"))
            snap.rolling_median_5y_pct = _dec(rj.get("5Y", {}).get("median"))
            snap.rolling_median_7y_pct = _dec(rj.get("7Y", {}).get("median"))
            to_update.append(snap)
            done += 1

            if len(to_update) >= BATCH:
                FundScreenerSnapshot.objects.bulk_update(
                    to_update,
                    [
                        "rolling_median_1y_pct",
                        "rolling_median_3y_pct",
                        "rolling_median_5y_pct",
                        "rolling_median_7y_pct",
                    ],
                    batch_size=BATCH,
                )
                self.stdout.write(f"  Updated {done}/{total}")
                to_update = []

        if to_update:
            FundScreenerSnapshot.objects.bulk_update(
                to_update,
                [
                    "rolling_median_1y_pct",
                    "rolling_median_3y_pct",
                    "rolling_median_5y_pct",
                    "rolling_median_7y_pct",
                ],
                batch_size=BATCH,
            )

        self.stdout.write(self.style.SUCCESS(f"Done. Updated {done} snapshots."))
