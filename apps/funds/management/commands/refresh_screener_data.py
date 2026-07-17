"""Refresh persisted rows used by the mutual fund screener."""
from django.core.management.base import BaseCommand

from apps.funds.models import Scheme
from apps.funds.screener import refresh_snapshot_for_scheme


class Command(BaseCommand):
    help = "Refresh denormalized screener snapshots from scheme, metadata, NAV, and analytics data"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="Limit number of schemes to process")
        parser.add_argument("--amfi", type=str, default=None, help="Refresh a single AMFI scheme code")
        parser.add_argument("--direct-growth-only", action="store_true", help="Only refresh active Direct Growth schemes")
        parser.add_argument("--dry-run", action="store_true", help="Count target schemes without writing snapshots")

    def handle(self, *args, **options):
        from django.db.models import Q
        qs = Scheme.objects.filter(is_active=True).select_related("meta")
        if options["direct_growth_only"]:
            qs = qs.filter(Q(is_direct=True, plan="GROWTH") | Q(is_etf=True))
        if options["amfi"]:
            qs = qs.filter(amfi_code=options["amfi"])
        if options["limit"]:
            qs = qs[: options["limit"]]

        total = qs.count()
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN complete. Would refresh {total} screener rows."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"Refreshing {total} screener rows"))
        success = 0
        errors = 0

        for index, scheme in enumerate(qs, 1):
            try:
                refresh_snapshot_for_scheme(scheme)
                success += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(f"[{scheme.amfi_code}] refresh failed: {exc}")

            if index % 250 == 0:
                self.stdout.write(f"  {index}/{total} | ok={success} err={errors}")

        self.stdout.write(self.style.SUCCESS(f"Done. Refreshed: {success} | Errors: {errors}"))
