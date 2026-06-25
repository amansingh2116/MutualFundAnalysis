"""
Management command: populate_home_dashboard
============================================
Phase A: Computes CategorySnapshot aggregates for every scheme_sub_category.
Phase B: Runs compute_quartile_ranks_for_category() for every sub-category.

Both phases operate purely from FundScreenerSnapshot + FundModelScore (no API
calls, no heavy joins).  Fast — typically completes in under 60 seconds.

Usage:
    python manage.py populate_home_dashboard
    python manage.py populate_home_dashboard --category="Mid Cap Fund"
    python manage.py populate_home_dashboard --skip-quartiles
    python manage.py populate_home_dashboard --skip-snapshots
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import numpy as np

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Max, Min

from apps.analytics.models import CalendarReturn
from apps.funds.models import (
    CategorySnapshot,
    FundModelScore,
    FundScreenerSnapshot,
)
from apps.funds.screener import compute_quartile_ranks_for_category

logger = logging.getLogger("mfanalysis")


def _d(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(f"{float(val):.4f}")
    except Exception:
        return None


def _d1(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(f"{float(val):.1f}")
    except Exception:
        return None


def build_category_snapshot(sub_category: str) -> CategorySnapshot | None:
    """
    Compute aggregates for one sub-category and upsert CategorySnapshot.
    Returns the saved object or None if no data.
    """
    qs = FundScreenerSnapshot.objects.filter(
        scheme_sub_category=sub_category,
        is_direct=True,
    )
    count = qs.count()
    if count == 0:
        return None

    # First row for metadata
    first = qs.values("category_group", "benchmark_name", "data_as_of").first()

    # ── Aggregate returns ──────────────────────────────────────────────────
    agg = qs.aggregate(
        avg_1y=Avg("returns_1y_pct"),
        max_1y=Max("returns_1y_pct"),
        min_1y=Min("returns_1y_pct"),
        avg_3y=Avg("returns_3y_pct"),
        max_3y=Max("returns_3y_pct"),
        min_3y=Min("returns_3y_pct"),
        avg_5y=Avg("returns_5y_pct"),
        max_5y=Max("returns_5y_pct"),
        min_5y=Min("returns_5y_pct"),
        avg_vol=Avg("volatility_3y_pct"),
        avg_sharpe=Avg("sharpe_ratio"),
        avg_sortino=Avg("sortino_ratio"),
        avg_drawdown=Avg("max_drawdown"),
        avg_vol_5y=Avg("volatility_5y_pct"),
        avg_sharpe_5y=Avg("sharpe_ratio_5y"),
        avg_sortino_5y=Avg("sortino_ratio_5y"),
        avg_drawdown_5y=Avg("max_drawdown_5y"),
    )

    # ── Median returns (NumPy) ─────────────────────────────────────────────
    # pull lists in one query for efficiency
    vals_1y = list(
        qs.exclude(returns_1y_pct=None)
        .values_list("returns_1y_pct", flat=True)
    )
    vals_3y = list(
        qs.exclude(returns_3y_pct=None)
        .values_list("returns_3y_pct", flat=True)
    )
    vals_5y = list(
        qs.exclude(returns_5y_pct=None)
        .values_list("returns_5y_pct", flat=True)
    )

    med_1y = float(np.median([float(v) for v in vals_1y])) if vals_1y else None
    med_3y = float(np.median([float(v) for v in vals_3y])) if vals_3y else None
    med_5y = float(np.median([float(v) for v in vals_5y])) if vals_5y else None

    # ── Score distribution ─────────────────────────────────────────────────
    scheme_ids = list(qs.values_list("scheme_id", flat=True))
    scores = list(
        FundModelScore.objects.filter(scheme_id__in=scheme_ids)
        .exclude(final_score=None)
        .values_list("final_score", flat=True)
    )
    avg_score = float(np.mean([float(s) for s in scores])) if scores else None
    total_scored = len(scores)

    def _pct(predicate):
        if not total_scored:
            return None
        return round(100 * sum(1 for s in scores if predicate(float(s))) / total_scored, 1)

    pct_strong = _pct(lambda s: s >= 75)
    pct_good   = _pct(lambda s: 55 <= s < 75)
    pct_fair   = _pct(lambda s: 40 <= s < 55)
    pct_weak   = _pct(lambda s: s < 40)

    # ── Calendar year returns (avg per year across all funds in category) ─────────
    scheme_ids = list(qs.values_list("scheme_id", flat=True))
    current_year = date.today().year
    start_year = current_year - 10
    calendar_data = {}
    try:
        for year in range(start_year, current_year + 1):
            year_rets = list(
                CalendarReturn.objects.filter(
                    scheme_id__in=scheme_ids, year=year
                ).exclude(return_pct=None)
                .values_list("return_pct", flat=True)
            )
            if year_rets:
                avg_ret = float(np.mean([float(r) for r in year_rets]))
                calendar_data[str(year)] = round(avg_ret, 2)
    except Exception as exc:
        logger.warning("calendar_returns failed for '%s': %s", sub_category, exc)

    # ── Trailing short-period returns (from screener snapshot fields) ────────────
    trailing_data = {}
    trailing_fields = {
        "1W": "returns_1w_pct",
        "1M": "returns_1m_pct",
        "3M": "returns_3m_pct",
        "6M": "returns_6m_pct",
        "1Y": "returns_1y_pct",
        "3Y": "returns_3y_pct",
        "5Y": "returns_5y_pct",
    }
    for label, field in trailing_fields.items():
        vals = list(
            qs.exclude(**{f"{field}__isnull": True})
            .values_list(field, flat=True)
        )
        if vals:
            trailing_data[label] = round(float(np.mean([float(v) for v in vals])), 2)

    # ── Rolling Returns (from screener snapshot rolling_returns_json) ─────────────
    rolling_data = {}
    all_rolling = list(qs.values_list("rolling_returns_json", flat=True))
    for period in ("1Y", "3Y", "5Y"):
        avgs = [r.get(period, {}).get("avg") for r in all_rolling if r and r.get(period) and r[period].get("avg") is not None]
        maxs = [r.get(period, {}).get("max") for r in all_rolling if r and r.get(period) and r[period].get("max") is not None]
        mins = [r.get(period, {}).get("min") for r in all_rolling if r and r.get(period) and r[period].get("min") is not None]
        pos = [r.get(period, {}).get("pos_pct") for r in all_rolling if r and r.get(period) and r[period].get("pos_pct") is not None]
        
        if avgs:
            rolling_data[period] = {
                "avg": round(float(np.mean(avgs)), 2),
                "max": round(float(np.mean(maxs)), 2) if maxs else None,
                "min": round(float(np.mean(mins)), 2) if mins else None,
                "pos_pct": round(float(np.mean(pos)), 1) if pos else None,
            }

    obj, _ = CategorySnapshot.objects.update_or_create(
        scheme_sub_category=sub_category,
        defaults={
            "category_group":        first.get("category_group", ""),
            "benchmark_name":        first.get("benchmark_name", ""),
            "fund_count":            count,
            "avg_return_1y":         _d(agg["avg_1y"]),
            "max_return_1y":         _d(agg["max_1y"]),
            "min_return_1y":         _d(agg["min_1y"]),
            "median_return_1y":      _d(med_1y),
            "avg_return_3y":         _d(agg["avg_3y"]),
            "max_return_3y":         _d(agg["max_3y"]),
            "min_return_3y":         _d(agg["min_3y"]),
            "median_return_3y":      _d(med_3y),
            "avg_return_5y":         _d(agg["avg_5y"]),
            "max_return_5y":         _d(agg["max_5y"]),
            "min_return_5y":         _d(agg["min_5y"]),
            "median_return_5y":      _d(med_5y),
            "avg_volatility":        _d(agg["avg_vol"]),
            "avg_sharpe":            _d(agg["avg_sharpe"]),
            "avg_sortino":           _d(agg["avg_sortino"]),
            "avg_max_drawdown":      _d(agg["avg_drawdown"]),
            "avg_volatility_5y":     _d(agg["avg_vol_5y"]),
            "avg_sharpe_5y":         _d(agg["avg_sharpe_5y"]),
            "avg_sortino_5y":        _d(agg["avg_sortino_5y"]),
            "avg_max_drawdown_5y":   _d(agg["avg_drawdown_5y"]),
            "avg_model_score":       _d1(avg_score),
            "pct_strong":            _d1(pct_strong),
            "pct_good":              _d1(pct_good),
            "pct_fair":              _d1(pct_fair),
            "pct_weak":              _d1(pct_weak),
            "data_as_of":            first.get("data_as_of") or date.today(),
            "calendar_returns_json": calendar_data,
            "quarterly_returns_json": trailing_data,
            "rolling_returns_json":  rolling_data,
        },
    )
    return obj


class Command(BaseCommand):
    help = (
        "Build CategorySnapshot aggregates and compute quartile ranks "
        "within each sub-category. Run after populate_screener."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--category",
            dest="category",
            default=None,
            metavar="NAME",
            help="Only process this sub-category (exact match).",
        )
        parser.add_argument(
            "--skip-quartiles",
            action="store_true",
            help="Skip quartile rank computation (only build CategorySnapshot).",
        )
        parser.add_argument(
            "--skip-snapshots",
            action="store_true",
            help="Skip CategorySnapshot build (only compute quartile ranks).",
        )

    def handle(self, *args, **options):
        category_filter = options.get("category")
        skip_quartiles  = options.get("skip_quartiles", False)
        skip_snapshots  = options.get("skip_snapshots", False)

        # Collect distinct sub-categories from screener snapshots
        # Use sorted(set(...)) instead of distinct() alone — in some DB configurations
        # (especially SQLite without an ORDER BY), distinct() on flat values_list may
        # return duplicates, which causes the dashboard to process the same category
        # thousands of times unnecessarily.
        qs = (
            FundScreenerSnapshot.objects
            .filter(is_direct=True)
            .exclude(scheme_sub_category="")
        )
        if category_filter:
            qs = qs.filter(scheme_sub_category=category_filter)

        raw_cats = qs.values_list("scheme_sub_category", flat=True)
        sub_categories = sorted(set(raw_cats))
        total = len(sub_categories)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"populate_home_dashboard: {total} sub-categories | "
                f"snapshots={'SKIP' if skip_snapshots else 'YES'} "
                f"quartiles={'SKIP' if skip_quartiles else 'YES'}"
            )
        )

        snap_ok = snap_skip = snap_err = 0
        q_ok = q_err = 0

        for i, sub_cat in enumerate(sub_categories, 1):
            # ── Phase A: CategorySnapshot ──────────────────────────────────
            if not skip_snapshots:
                try:
                    obj = build_category_snapshot(sub_cat)
                    if obj:
                        snap_ok += 1
                    else:
                        snap_skip += 1
                except Exception as exc:
                    snap_err += 1
                    logger.error("CategorySnapshot error for '%s': %s", sub_cat, exc)

            # ── Phase B: Quartile ranks ────────────────────────────────────
            if not skip_quartiles:
                try:
                    n = compute_quartile_ranks_for_category(sub_cat)
                    q_ok += 1
                    logger.debug("Ranked %d funds in '%s'", n, sub_cat)
                except Exception as exc:
                    q_err += 1
                    logger.error("Quartile rank error for '%s': %s", sub_cat, exc)

            if i % 10 == 0 or i == total:
                self.stdout.write(
                    f"  [{i}/{total}]  "
                    f"snap={snap_ok}+{snap_skip}skip({snap_err}err)  "
                    f"quartiles={q_ok}({q_err}err)"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\npopulate_home_dashboard complete:\n"
                f"  CategorySnapshot:  ok={snap_ok}  skip={snap_skip}  err={snap_err}\n"
                f"  Quartile ranks:    ok={q_ok}  err={q_err}"
            )
        )
