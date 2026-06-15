"""Generate top-fund screener CSV and HTML performance reports."""
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.funds.screener_reports import TOP_REPORT_SORTS, generate_top_screener_reports


class Command(BaseCommand):
    help = "Generate a top-funds CSV plus HTML performance reports from screener snapshots"

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=10, help="Number of top funds to export")
        parser.add_argument(
            "--sort",
            choices=sorted(TOP_REPORT_SORTS.keys()),
            default="cagr_3y",
            help="Metric used to select the top funds",
        )
        parser.add_argument("--output-dir", type=str, default="", help="Optional output directory")

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]) if options["output_dir"] else None
        result = generate_top_screener_reports(
            top=options["top"],
            sort=options["sort"],
            output_dir=output_dir,
        )

        self.stdout.write(self.style.SUCCESS(f"Top CSV: {result.csv_path}"))
        self.stdout.write(self.style.SUCCESS(f"Reports directory: {result.output_dir}"))
        for path in result.report_paths:
            self.stdout.write(f"  {path}")
