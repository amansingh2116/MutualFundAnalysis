"""
Analytics Computation Engine
============================
The single source of truth for all metric computation.

All formulas were verified and tested in:
  notebooks/01_data_source_exploration.ipynb (Section 13)

Design principles:
  - All computation is pandas/numpy — no Django ORM inside hot loops
  - Engine reads NAV from DB at start, computes, writes results back
  - Risk-free rate is taken from Django settings (RF_ANNUAL_RATE), not hardcoded
  - All functions are pure and testable independently of Django
  - Benchmark alignment: daily returns are inner-joined on date before regression
"""

import logging
import math
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import brentq

from django.conf import settings

logger = logging.getLogger('mfanalysis.analytics')

# ── Constants ──────────────────────────────────────────────────────────────────
TRADING_DAYS = 252
RF_ANNUAL    = getattr(settings, 'RF_ANNUAL_RATE', 0.065)
RF_DAILY     = RF_ANNUAL / TRADING_DAYS

# Rolling window definitions (label → trading days)
ROLLING_WINDOWS = {
    '1Y': 252,
    '3Y': 756,
    '5Y': 1260,
}

# Trailing period definitions (label → calendar days)
TRAILING_PERIODS = {
    '1M':  30,
    '3M':  91,
    '6M':  182,
    '1Y':  365,
    '2Y':  730,
    '3Y':  1096,
    '5Y':  1826,
    '7Y':  2556,
    '10Y': 3652,
}

# Risk metric period definitions (label → calendar days)
RISK_PERIODS = {
    '3Y': 1096,
    '5Y': 1826,
}


# ── Main orchestrator ──────────────────────────────────────────────────────────

def compute_all_metrics(scheme) -> None:
    """
    Compute and persist all analytics for a single scheme.
    Called nightly by tasks/compute_analytics.py.

    Args:
        scheme: apps.funds.models.Scheme instance
    """
    try:
        nav = _load_nav_series(scheme)
    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] Failed to load NAV: {e}")
        return

    if len(nav) < TRADING_DAYS:
        logger.info(f"[{scheme.amfi_code}] Insufficient NAV history ({len(nav)} days) — skipping")
        return

    try:
        bm = _load_benchmark_series(scheme)
    except Exception as e:
        logger.warning(f"[{scheme.amfi_code}] Benchmark load failed: {e} — computing without benchmark")
        bm = None

    logger.info(f"[{scheme.amfi_code}] Computing analytics ({len(nav)} NAV days)")

    try:
        _compute_trailing_returns(scheme, nav, bm)
    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] trailing_returns failed: {e}")

    try:
        _compute_calendar_returns(scheme, nav, bm)
    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] calendar_returns failed: {e}")

    try:
        _compute_rolling_returns(scheme, nav)
    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] rolling_returns failed: {e}")

    try:
        _compute_risk_metrics(scheme, nav, bm)
    except Exception as e:
        logger.error(f"[{scheme.amfi_code}] risk_metrics failed: {e}")


# ── Data loaders ───────────────────────────────────────────────────────────────

def _load_nav_series(scheme) -> pd.Series:
    """Load NAV history from DB as a sorted pd.Series indexed by date."""
    from apps.funds.models import NAVHistory
    qs = (NAVHistory.objects
          .filter(scheme=scheme)
          .values('date', 'nav')
          .order_by('date'))
    df = pd.DataFrame(list(qs))
    if df.empty:
        raise ValueError(f"No NAV data for {scheme.amfi_code}")
    df['date'] = pd.to_datetime(df['date'])
    df['nav']  = pd.to_numeric(df['nav'], errors='coerce')
    series = df.set_index('date')['nav'].dropna()
    series = series[~series.index.duplicated(keep='last')]
    return series.sort_index()


def _load_benchmark_series(scheme) -> Optional[pd.Series]:
    """
    Load benchmark NAV series for a scheme based on its SEBI category.
    Returns None if no benchmark is mapped or no data exists.
    """
    from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
    from adapters.benchmark_adapter import CATEGORY_BENCHMARK_MAP

    bm_name = CATEGORY_BENCHMARK_MAP.get(scheme.scheme_category)
    if not bm_name:
        return None

    try:
        bm_index = BenchmarkIndex.objects.get(name=bm_name)
    except BenchmarkIndex.DoesNotExist:
        return None

    qs = (BenchmarkNAV.objects
          .filter(index=bm_index)
          .values('date', 'close')
          .order_by('date'))
    df = pd.DataFrame(list(qs))
    if df.empty:
        return None
    df['date']  = pd.to_datetime(df['date'])
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    series = df.set_index('date')['close'].dropna()
    series = series[~series.index.duplicated(keep='last')]
    return series.sort_index()


# ── Trailing Returns ───────────────────────────────────────────────────────────

def _compute_trailing_returns(scheme, nav: pd.Series, bm: Optional[pd.Series]) -> None:
    """
    Compute and persist trailing CAGR for all standard periods + since inception.
    Deletes today's existing rows before inserting fresh results.
    """
    from apps.analytics.models import TrailingReturn
    today = nav.index[-1]
    rows  = []

    for label, days in TRAILING_PERIODS.items():
        cutoff = today - pd.Timedelta(days=days)
        sub    = nav[nav.index >= cutoff]
        if len(sub) < 5:
            continue
        years     = days / 365.25
        fund_cagr = _cagr(sub.iloc[0], sub.iloc[-1], years)
        bm_cagr   = None
        if bm is not None:
            bm_sub = bm[bm.index >= cutoff]
            if len(bm_sub) > 5:
                bm_cagr = _cagr(bm_sub.iloc[0], bm_sub.iloc[-1], years)

        excess = (fund_cagr - bm_cagr) if (fund_cagr is not None and bm_cagr is not None) else None
        rows.append(TrailingReturn(
            scheme=scheme, period=label, years=round(years, 2),
            cagr_pct=fund_cagr, bm_cagr=bm_cagr, excess=excess,
            as_of=today.date(),
        ))

    # Since inception
    si_days = (today - nav.index[0]).days
    si_yrs  = si_days / 365.25
    si_cagr = _cagr(nav.iloc[0], nav.iloc[-1], si_yrs)
    rows.append(TrailingReturn(
        scheme=scheme, period='SI', years=round(si_yrs, 2),
        cagr_pct=si_cagr, bm_cagr=None, excess=None,
        as_of=today.date(),
    ))

    TrailingReturn.objects.filter(scheme=scheme, as_of=today.date()).delete()
    TrailingReturn.objects.bulk_create(rows, ignore_conflicts=True)
    logger.debug(f"[{scheme.amfi_code}] Trailing returns: {len(rows)} rows saved")


# ── Calendar Returns ───────────────────────────────────────────────────────────

def _compute_calendar_returns(scheme, nav: pd.Series, bm: Optional[pd.Series]) -> None:
    """
    Compute and persist annual return for each complete calendar year.
    Overwrites existing rows for each year.
    """
    from apps.analytics.models import CalendarReturn
    rows = []
    start_year = nav.index[0].year
    end_year   = nav.index[-1].year

    for year in range(start_year, end_year + 1):
        year_nav = nav[nav.index.year == year]
        if len(year_nav) < 50:  # need meaningful trading days
            continue
        ret_pct = _simple_return(year_nav.iloc[0], year_nav.iloc[-1])
        bm_ret  = None
        if bm is not None:
            year_bm = bm[bm.index.year == year]
            if len(year_bm) > 10:
                bm_ret = _simple_return(year_bm.iloc[0], year_bm.iloc[-1])

        outperformed = None
        if ret_pct is not None and bm_ret is not None:
            outperformed = ret_pct > bm_ret

        rows.append(CalendarReturn(
            scheme=scheme, year=year, return_pct=ret_pct,
            bm_return=bm_ret, outperformed=outperformed,
        ))

    # Upsert by year
    for row in rows:
        CalendarReturn.objects.update_or_create(
            scheme=scheme, year=row.year,
            defaults={
                'return_pct':   row.return_pct,
                'bm_return':    row.bm_return,
                'outperformed': row.outperformed,
            }
        )
    logger.debug(f"[{scheme.amfi_code}] Calendar returns: {len(rows)} years saved")


# ── Rolling Returns ────────────────────────────────────────────────────────────

def _compute_rolling_returns(scheme, nav: pd.Series) -> None:
    """
    Compute rolling return statistics for 1Y, 3Y, 5Y windows.
    Stats: min, max, mean, std, win_rate (> 0%), win_rate (> 12%).
    """
    from apps.analytics.models import RollingReturn
    today = nav.index[-1].date()

    rows = []
    for label, window_days in ROLLING_WINDOWS.items():
        if len(nav) < window_days + 10:
            continue

        # Compute rolling CAGR for every window
        years = window_days / TRADING_DAYS
        rolling_end   = nav.iloc[window_days:]
        rolling_start = nav.iloc[:-window_days]
        rolling_start.index = rolling_end.index  # align

        cagrs = ((rolling_end.values / rolling_start.values) ** (1 / years) - 1) * 100
        cagrs = cagrs[np.isfinite(cagrs)]

        if len(cagrs) < 10:
            continue

        rows.append(RollingReturn(
            scheme=scheme, window=label, window_days=window_days,
            min_pct  = float(np.min(cagrs)),
            max_pct  = float(np.max(cagrs)),
            mean_pct = float(np.mean(cagrs)),
            std_dev  = float(np.std(cagrs)),
            win_rate_0  = float(np.mean(cagrs > 0) * 100),
            win_rate_12 = float(np.mean(cagrs > 12) * 100),
            as_of    = today,
        ))

    RollingReturn.objects.filter(scheme=scheme, as_of=today).delete()
    RollingReturn.objects.bulk_create(rows, ignore_conflicts=True)
    logger.debug(f"[{scheme.amfi_code}] Rolling returns: {len(rows)} windows saved")


# ── Risk Metrics ───────────────────────────────────────────────────────────────

def _compute_risk_metrics(scheme, nav: pd.Series, bm: Optional[pd.Series]) -> None:
    """
    Compute risk-adjusted metrics for 3Y and 5Y periods:
    Std Dev, Sharpe, Sortino, Max Drawdown, Beta, Alpha, R², 
    Upside/Downside Capture, Tracking Error, Information Ratio.
    """
    from apps.analytics.models import RiskMetrics
    today = nav.index[-1].date()
    rf    = getattr(settings, 'RF_ANNUAL_RATE', 0.065)
    rf_d  = rf / TRADING_DAYS

    for label, cal_days in RISK_PERIODS.items():
        cutoff  = nav.index[-1] - pd.Timedelta(days=cal_days)
        nav_sub = nav[nav.index >= cutoff]
        if len(nav_sub) < 126:   # need minimum 6 months
            continue

        ret_sub    = nav_sub.pct_change().dropna()
        excess_ret = ret_sub - rf_d

        # Volatility
        std_ann = float(ret_sub.std() * math.sqrt(TRADING_DAYS) * 100)

        # Sharpe (annualised)
        sharpe = float(
            (excess_ret.mean() / excess_ret.std()) * math.sqrt(TRADING_DAYS)
        ) if excess_ret.std() > 0 else None

        # Sortino (downside deviation only)
        downside = ret_sub[ret_sub < rf_d]
        sortino  = float(
            excess_ret.mean() * TRADING_DAYS / (downside.std() * math.sqrt(TRADING_DAYS))
        ) if (len(downside) > 5 and downside.std() > 0) else None

        # Max drawdown
        running_max = nav_sub.cummax()
        drawdown_series = (nav_sub - running_max) / running_max * 100
        max_dd = float(drawdown_series.min())

        # Benchmark-relative metrics
        beta = alpha = r_sq = up_cap = dn_cap = track_err = info_ratio = None

        if bm is not None:
            bm_sub  = bm[bm.index >= cutoff]
            bm_ret  = bm_sub.pct_change().dropna()
            aligned = pd.DataFrame({'fund': ret_sub, 'bm': bm_ret}).dropna()

            if len(aligned) > 30:
                slope, intercept, r_val, *_ = stats.linregress(
                    aligned['bm'].values, aligned['fund'].values
                )
                beta  = float(slope)
                alpha = float(intercept * TRADING_DAYS * 100)
                r_sq  = float(r_val ** 2 * 100)

                up_mask = aligned['bm'] > 0
                dn_mask = aligned['bm'] < 0
                if up_mask.sum() > 5:
                    up_cap = float(
                        aligned.loc[up_mask, 'fund'].mean() /
                        aligned.loc[up_mask, 'bm'].mean() * 100
                    )
                if dn_mask.sum() > 5:
                    dn_cap = float(
                        aligned.loc[dn_mask, 'fund'].mean() /
                        aligned.loc[dn_mask, 'bm'].mean() * 100
                    )

                diff = aligned['fund'] - aligned['bm']
                te   = diff.std() * math.sqrt(TRADING_DAYS) * 100
                if te > 0:
                    track_err  = float(te)
                    info_ratio = float(diff.mean() * TRADING_DAYS * 100 / te)

        RiskMetrics.objects.update_or_create(
            scheme=scheme, period=label, as_of=today,
            defaults=dict(
                period_days     = cal_days,
                std_dev_ann     = std_ann,
                sharpe_ratio    = sharpe,
                sortino_ratio   = sortino,
                max_drawdown    = max_dd,
                beta            = beta,
                alpha_ann       = alpha,
                r_squared       = r_sq,
                upside_capture  = up_cap,
                downside_capture= dn_cap,
                tracking_error  = track_err,
                info_ratio      = info_ratio,
                rf_rate_used    = rf,
            )
        )
    logger.debug(f"[{scheme.amfi_code}] Risk metrics saved")


# ── SIP Simulation ─────────────────────────────────────────────────────────────

def simulate_sip(
    nav_series: pd.Series,
    monthly_amount: float = 10000,
    start_date=None,
) -> Optional[dict]:
    """
    Simulate a monthly SIP investment and compute XIRR.

    Args:
        nav_series: pd.Series indexed by date, values are NAV
        monthly_amount: monthly investment in rupees
        start_date: start of SIP (defaults to series start)

    Returns:
        dict with total_invested, current_value, absolute_gain,
        absolute_return_pct, xirr_pct, units_held, sip_instalments,
        avg_cost, current_nav
    """
    if start_date is None:
        start_date = nav_series.index[0]

    nav_series = nav_series.copy()
    nav_series.index = pd.to_datetime(nav_series.index)
    monthly = nav_series.resample('MS').first().dropna()
    monthly = monthly[monthly.index >= pd.Timestamp(start_date)]

    if len(monthly) == 0:
        return None

    units_held = 0.0
    invested   = 0.0
    cashflows  = []
    dates      = []

    for ts, nav_val in monthly.items():
        if nav_val <= 0:
            continue
        units_held += monthly_amount / float(nav_val)
        invested   += monthly_amount
        cashflows.append(-monthly_amount)
        dates.append(ts.to_pydatetime())

    final_nav   = float(nav_series.iloc[-1])
    final_value = units_held * final_nav
    cashflows.append(final_value)
    dates.append(nav_series.index[-1].to_pydatetime())

    xirr = _compute_xirr(cashflows, dates)

    return {
        'total_invested':      round(invested, 2),
        'current_value':       round(final_value, 2),
        'absolute_gain':       round(final_value - invested, 2),
        'absolute_return_pct': round((final_value / invested - 1) * 100, 2) if invested > 0 else None,
        'xirr_pct':            round(xirr * 100, 2) if xirr is not None else None,
        'units_held':          round(units_held, 4),
        'sip_instalments':     len(monthly),
        'avg_cost':            round(invested / units_held, 4) if units_held > 0 else None,
        'current_nav':         final_nav,
    }


# ── Helper functions ───────────────────────────────────────────────────────────

def _cagr(start_val, end_val, years: float) -> Optional[float]:
    """Compute CAGR. Returns None on invalid inputs."""
    try:
        sv, ev = float(start_val), float(end_val)
        if years <= 0 or sv <= 0 or not math.isfinite(sv) or not math.isfinite(ev):
            return None
        return round(((ev / sv) ** (1.0 / years) - 1) * 100, 4)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _simple_return(start_val, end_val) -> Optional[float]:
    """Compute simple return %."""
    try:
        sv, ev = float(start_val), float(end_val)
        if sv <= 0:
            return None
        return round((ev / sv - 1) * 100, 4)
    except (TypeError, ValueError):
        return None


def _compute_xirr(cashflows: list, dates: list) -> Optional[float]:
    """
    Compute XIRR using Brent's method (scipy.optimize.brentq).
    Returns annual rate as a decimal (0.15 = 15%). None on failure.
    """
    if len(cashflows) < 2:
        return None

    def xnpv(rate, cfs, ds):
        t0 = ds[0]
        return sum(
            cf / (1 + rate) ** ((d - t0).days / 365.0)
            for cf, d in zip(cfs, ds)
        )

    try:
        rate = brentq(lambda r: xnpv(r, cashflows, dates), -0.9999, 100.0, maxiter=500)
        return rate if math.isfinite(rate) else None
    except (ValueError, RuntimeError):
        return None
