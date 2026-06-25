"""
Management command: populate_benchmark_returns
===============================================
Computes period returns for every BenchmarkIndex that has BenchmarkNAV history,
then upserts a BenchmarkReturns row for each.

Return periods:
  1W   — last 7 calendar days (simple return)
  1M   — last 30 calendar days (simple return)
  3M   — last 91 calendar days (simple return)
  6M   — last 182 calendar days (simple return)
  YTD  — Jan 1 of current year to latest NAV date (simple return)
  1Y   — CAGR over 365 days
  3Y   — CAGR over 3 × 365 days
  5Y   — CAGR over 5 × 365 days
  10Y  — CAGR over 10 × 365 days
  SL   — CAGR from earliest BenchmarkNAV date to latest (since-launch)

Usage:
    python manage.py populate_benchmark_returns
    python manage.py populate_benchmark_returns --index="NIFTY 50"
    python manage.py populate_benchmark_returns --index="NIFTY 50" --index="NIFTY MIDCAP 150"
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from django.core.management.base import BaseCommand

from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV, BenchmarkReturns

logger = logging.getLogger("mfanalysis")


def _cagr(start_val: float, end_val: float, years: float) -> float | None:
    """Annualised CAGR. Returns None if inputs are invalid."""
    if not start_val or not end_val or years <= 0:
        return None
    try:
        return ((end_val / start_val) ** (1 / years) - 1) * 100
    except (ZeroDivisionError, ValueError):
        return None


def _simple_return(start_val: float, end_val: float) -> float | None:
    """Simple percentage return: (end - start) / start * 100."""
    if not start_val or not end_val:
        return None
    try:
        return (end_val / start_val - 1) * 100
    except ZeroDivisionError:
        return None


def _decimal(val: float | None) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(f"{val:.4f}")
    except Exception:
        return None


def compute_returns_for_index(index: BenchmarkIndex) -> dict | None:
    """
    Load all BenchmarkNAV for this index as a Pandas Series and compute
    all period returns.  Returns a dict of field values or None if no data.
    """
    rows = list(
        BenchmarkNAV.objects.filter(index=index)
        .order_by("date")
        .values_list("date", "close")
    )
    if len(rows) < 2:
        return None

    series = pd.Series(
        {pd.Timestamp(d): float(c) for d, c in rows}
    ).sort_index()

    latest_date = series.index[-1].date()
    latest_val  = series.iloc[-1]
    launch_date = series.index[0].date()
    launch_val  = series.iloc[0]
    nav_count   = len(series)
    today       = latest_date  # use most recent available as "today"

    def _val_at(target_date: date) -> float | None:
        """Closest NAV value on or before target_date."""
        ts = pd.Timestamp(target_date)
        sub = series[series.index <= ts]
        if sub.empty:
            return None
        return float(sub.iloc[-1])

    # ── Period boundaries ────────────────────────────────────────────────────
    ytd_start = date(today.year, 1, 1)
    d_1w   = today - timedelta(days=7)
    d_1m   = today - timedelta(days=30)
    d_3m   = today - timedelta(days=91)
    d_6m   = today - timedelta(days=182)
    d_1y   = today - timedelta(days=365)
    d_3y   = today - timedelta(days=365 * 3)
    d_5y   = today - timedelta(days=365 * 5)
    d_10y  = today - timedelta(days=365 * 10)

    v_1w   = _val_at(d_1w)
    v_1m   = _val_at(d_1m)
    v_3m   = _val_at(d_3m)
    v_6m   = _val_at(d_6m)
    v_ytd  = _val_at(ytd_start)
    v_1y   = _val_at(d_1y)
    v_3y   = _val_at(d_3y)
    v_5y   = _val_at(d_5y)
    v_10y  = _val_at(d_10y)

    # Years since launch
    sl_years = (latest_date - launch_date).days / 365.25

    # ── Risk metrics per window ───────────────────────────────────────────────
    def _risk_for_window(days: int):
        """Return (volatility%, sharpe, max_drawdown%) for a trailing window."""
        cutoff = pd.Timestamp(today - timedelta(days=days))
        sub = series[series.index >= cutoff]
        if len(sub) < 30:
            return None, None, None
        pct_chg = sub.pct_change().dropna()
        if pct_chg.empty:
            return None, None, None
        vol_daily = float(pct_chg.std())
        vol_annual = vol_daily * (252 ** 0.5) * 100  # percent
        cagr_val = _cagr(float(sub.iloc[0]), float(sub.iloc[-1]), days / 365.25)
        rf_daily = 0.065 / 252
        sharpe = None
        if cagr_val is not None and vol_annual > 0:
            sharpe = (cagr_val / 100 - 0.065) / (vol_annual / 100)
        # Max drawdown
        rolling_max = sub.cummax()
        dd = (sub - rolling_max) / rolling_max * 100
        max_dd = float(dd.min()) if not dd.empty else None
        return (
            _decimal(vol_annual),
            _decimal(sharpe),
            _decimal(max_dd),
        )

    vol_1y, sharpe_1y, mdd_1y = _risk_for_window(365)
    vol_3y, sharpe_3y, mdd_3y = _risk_for_window(365 * 3)
    vol_5y, sharpe_5y, mdd_5y = _risk_for_window(365 * 5)

    # ── Calendar returns ──────────────────────────────────────────────────────
    calendar_returns_json = {}
    start_year = launch_date.year
    current_year = today.year
    for year in range(start_year, current_year + 1):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        # Find first and last available NAVs for the year
        sub = series[(series.index.date >= year_start) & (series.index.date <= year_end)]
        if not sub.empty:
            cal_ret = _simple_return(float(sub.iloc[0]), float(sub.iloc[-1]))
            if cal_ret is not None:
                calendar_returns_json[str(year)] = float(f"{cal_ret:.2f}")

    # ── Rolling returns ───────────────────────────────────────────────────────
    rolling_returns_json = {}
    # Helper to calculate daily rolling returns
    def _rolling_for_window(days: int):
        if len(series) < days:
            return None
        # We can approximate rolling return by shifting the series by trading days
        # roughly 252 trading days in a year.
        trading_days = int(days * 252 / 365.25)
        shifted = series.shift(trading_days)
        # Return for the period is (current - shifted) / shifted
        rolls = ((series - shifted) / shifted).dropna() * 100
        if rolls.empty:
            return None
        
        avg_ret = float(rolls.mean())
        max_ret = float(rolls.max())
        min_ret = float(rolls.min())
        pos_pct = float((rolls > 0).sum() / len(rolls) * 100)
        return {
            "avg": float(f"{avg_ret:.2f}"),
            "max": float(f"{max_ret:.2f}"),
            "min": float(f"{min_ret:.2f}"),
            "pos_pct": float(f"{pos_pct:.1f}"),
        }

    rolling_returns_json["1Y"] = _rolling_for_window(365)
    rolling_returns_json["3Y"] = _rolling_for_window(365 * 3)
    rolling_returns_json["5Y"] = _rolling_for_window(365 * 5)
    # Remove nulls
    rolling_returns_json = {k: v for k, v in rolling_returns_json.items() if v is not None}

    return {
        "ret_1w":           _decimal(_simple_return(v_1w,  latest_val)),
        "ret_1m":           _decimal(_simple_return(v_1m,  latest_val)),
        "ret_3m":           _decimal(_simple_return(v_3m,  latest_val)),
        "ret_6m":           _decimal(_simple_return(v_6m,  latest_val)),
        "ret_ytd":          _decimal(_simple_return(v_ytd, latest_val)),
        "ret_1y":           _decimal(_cagr(v_1y,  latest_val, 1.0)),
        "ret_3y":           _decimal(_cagr(v_3y,  latest_val, 3.0)),
        "ret_5y":           _decimal(_cagr(v_5y,  latest_val, 5.0)),
        "ret_10y":          _decimal(_cagr(v_10y, latest_val, 10.0)),
        "ret_since_launch": _decimal(_cagr(launch_val, latest_val, sl_years)),
        "volatility_1y":    vol_1y,
        "volatility_3y":    vol_3y,
        "volatility_5y":    vol_5y,
        "sharpe_1y":        sharpe_1y,
        "sharpe_3y":        sharpe_3y,
        "sharpe_5y":        sharpe_5y,
        "max_drawdown_1y":  mdd_1y,
        "max_drawdown_3y":  mdd_3y,
        "max_drawdown_5y":  mdd_5y,
        "calendar_returns_json": calendar_returns_json,
        "rolling_returns_json":  rolling_returns_json,
        "launch_date":      launch_date,
        "data_as_of":       latest_date,
        "nav_count":        nav_count,
    }


class Command(BaseCommand):
    help = "Compute period returns for all BenchmarkIndex entries and save to BenchmarkReturns."

    def add_arguments(self, parser):
        parser.add_argument(
            "--index",
            action="append",
            dest="indices",
            default=None,
            metavar="NAME",
            help="Only process this index name (can be repeated for multiple indices).",
        )

    def handle(self, *args, **options):
        filter_names = options.get("indices") or []
        qs = BenchmarkIndex.objects.all()
        if filter_names:
            qs = qs.filter(name__in=filter_names)

        total = qs.count()
        ok = skip = err = 0

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"populate_benchmark_returns: processing {total} indices"
            )
        )

        for index in qs.iterator():
            try:
                fields = compute_returns_for_index(index)
                if fields is None:
                    skip += 1
                    logger.info("[%s] no BenchmarkNAV rows — skipped", index.name)
                    continue

                BenchmarkReturns.objects.update_or_create(
                    index=index,
                    defaults=fields,
                )
                ok += 1
                logger.debug("[%s] returns saved (as_of=%s)", index.name, fields["data_as_of"])

            except Exception as exc:
                err += 1
                logger.error("[%s] benchmark returns error: %s", index.name, exc)

        self.stdout.write(
            self.style.SUCCESS(
                f"\npopulate_benchmark_returns complete: "
                f"ok={ok}  skip={skip}  err={err}"
            )
        )
