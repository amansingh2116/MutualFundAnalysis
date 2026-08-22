"""
Management command: ingest_score_trend

Snapshots each fund's current model score and category rank into FundScoreTrend.
Run weekly (every Sunday). Automatically prunes records older than 52 weeks.

Usage:
    python manage.py ingest_score_trend
    python manage.py ingest_score_trend --date 2025-08-18   # specific week (Monday)
    python manage.py ingest_score_trend --prune-weeks 52    # custom retention
"""
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.funds.models import Scheme, FundScoreTrend, FundScreenerSnapshot

logger = logging.getLogger('mfanalysis')


def _week_monday(d: date) -> date:
    """Return the Monday of the ISO week containing date d."""
    return d - timedelta(days=d.weekday())


class Command(BaseCommand):
    help = 'Snapshot weekly fund score + rank into FundScoreTrend (run every Sunday).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date', type=str, default=None,
            help='ISO week Monday date YYYY-MM-DD (defaults to this week)'
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite existing snapshot for this week'
        )
        parser.add_argument(
            '--prune-weeks', type=int, default=52,
            help='Delete records older than this many weeks (default: 52)'
        )
        parser.add_argument(
            '--amfi', type=str, default=None,
            help='Process a single AMFI code only (testing)'
        )

    def handle(self, *args, **options):
        if options['date']:
            as_of_week = date.fromisoformat(options['date'])
            # Snap to Monday of that week
            as_of_week = _week_monday(as_of_week)
        else:
            as_of_week = _week_monday(timezone.localdate())

        force        = options['force']
        prune_weeks  = options['prune_weeks']
        amfi         = options['amfi']

        self.stdout.write(
            self.style.NOTICE(f'=== Score Trend Snapshot: Week of {as_of_week} ===')
        )

        # Build a lookup: amfi_code -> screener snapshot (for rank data)
        qs_snap = FundScreenerSnapshot.objects.all()
        if amfi:
            qs_snap = qs_snap.filter(scheme__amfi_code=amfi)

        snap_lookup: dict = {}
        for snap in qs_snap.select_related('scheme').iterator(chunk_size=500):
            snap_lookup[snap.scheme_id] = snap

        # Build a lookup: scheme_id -> FundModelScore
        from apps.funds.models import FundModelScore
        score_qs = FundModelScore.objects.all()
        if amfi:
            score_qs = score_qs.filter(scheme__amfi_code=amfi)
        score_lookup: dict = {}
        for ms in score_qs.iterator(chunk_size=500):
            score_lookup[ms.scheme_id] = ms

        total   = 0
        saved   = 0
        skipped = 0
        no_score = 0

        scheme_qs = Scheme.objects.filter(is_active=True)
        if amfi:
            scheme_qs = scheme_qs.filter(amfi_code=amfi)

        records_to_create = []
        records_to_update = []

        for scheme in scheme_qs.iterator(chunk_size=500):
            total += 1
            ms   = score_lookup.get(scheme.pk)
            snap = snap_lookup.get(scheme.pk)

            if not ms or ms.final_score is None:
                no_score += 1
                continue

            if not force:
                if FundScoreTrend.objects.filter(
                    scheme=scheme, as_of_week=as_of_week
                ).exists():
                    skipped += 1
                    continue

            FundScoreTrend.objects.update_or_create(
                scheme=scheme,
                as_of_week=as_of_week,
                defaults={
                    'final_score':  ms.final_score,
                    'score_badge':  ms.score_badge or '',
                    'rank_in_cat':  snap.rank_return_3y if snap else None,
                    'cat_total':    snap.rank_count_in_cat if snap else None,
                    'sub_category': snap.scheme_sub_category if snap else '',
                },
            )
            saved += 1

        # Prune old records
        if prune_weeks > 0:
            cutoff = as_of_week - timedelta(weeks=prune_weeks)
            deleted, _ = FundScoreTrend.objects.filter(as_of_week__lt=cutoff).delete()
            if deleted:
                self.stdout.write(f'Pruned {deleted} old score trend records (before {cutoff})')

        self.stdout.write(self.style.SUCCESS(
            f'Score Trend done | Week={as_of_week} | '
            f'Total={total} | Saved={saved} | Skipped={skipped} | No score={no_score}'
        ))
