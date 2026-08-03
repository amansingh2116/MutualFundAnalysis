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


def _sn(value) -> "float | None":
    """Safe-number: return None for NaN / Inf / values exceeding DecimalField limits,
    otherwise return the float.
    
    Django DecimalFields raise decimal.InvalidOperation when given float('nan')
    or float('inf') or numbers out of max_digits range [-9999.9999, 9999.9999],
    so we sanitize every computed metric before the ORM save.
    """
    if value is None:
        return None
    try:
        f = float(value)
        if math.isfinite(f) and -9999.0 <= f <= 9999.0:
            return f
        return None
    except (TypeError, ValueError):
        return None

# ── Constants ──────────────────────────────────────────────────────────────────
TRADING_DAYS = 252
RF_ANNUAL    = getattr(settings, 'RF_ANNUAL_RATE', 0.065)
RF_DAILY     = RF_ANNUAL / TRADING_DAYS

# Rolling window definitions (label → trading days)
ROLLING_WINDOWS = {
    '1Y': 252,
    '3Y': 756,
    '5Y': 1260,
    '7Y': 1764,
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
    '1Y': 365,
    '3Y': 1096,
    '5Y': 1826,
    '7Y': 2556,
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
        logger.info(f"[{scheme.amfi_code}] Fund has short history ({len(nav)} days) — computing partial analytics")

    try:
        bm = _load_benchmark_series(scheme, nav)
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


def _load_benchmark_series(scheme, nav: Optional[pd.Series] = None) -> Optional[pd.Series]:
    """
    Load benchmark NAV series for a scheme based on its SEBI category.
    Returns None if no benchmark is mapped or no data exists.
    """
    from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
    from apps.benchmarks.registry import benchmark_for, fetch_yahoo_history_for_benchmark, iter_benchmark_candidates

    bm_name = benchmark_for(scheme.scheme_category, getattr(scheme, 'scheme_name', ''))
    if not bm_name:
        return None
    start_date = None
    if nav is not None and not nav.empty:
        start_date = (nav.index[0] - pd.Timedelta(days=10)).date()

    candidates = [bm_name, *(candidate.benchmark_name for candidate in iter_benchmark_candidates(bm_name) if candidate.is_fallback)]

    for candidate in dict.fromkeys(candidates):
        bm_index = BenchmarkIndex.objects.filter(name__iexact=candidate).first()
        if not bm_index:
            continue
        qs = BenchmarkNAV.objects.filter(index=bm_index)
        if start_date:
            qs = qs.filter(date__gte=start_date)
        df = pd.DataFrame(list(qs.values('date', 'close').order_by('date')))
        if df.empty:
            continue
        df['date'] = pd.to_datetime(df['date'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        series = df.set_index('date')['close'].dropna()
        series = series[~series.index.duplicated(keep='last')].sort_index()
        if len(series) >= 2:
            return series

    series, _candidate = fetch_yahoo_history_for_benchmark(bm_name, start_date=start_date, min_rows=2)
    if not series.empty:
        return series
    return None


# ── Trailing Returns ───────────────────────────────────────────────────────────

def _compute_trailing_returns(scheme, nav: pd.Series, bm: Optional[pd.Series]) -> None:
    """
    Compute and persist trailing CAGR for all standard periods + since inception.
    Deletes today's existing rows before inserting fresh results.
    """
    from apps.analytics.models import TrailingReturn
    today = nav.index[-1]
    rows  = []

    # Ensure benchmark is truncated to fund's last NAV date (`today`)
    # to avoid comparing historical fund dates to today's benchmark value.
    bm_clipped = bm[bm.index <= today] if bm is not None else None

    for label, days in TRAILING_PERIODS.items():
        cutoff = today - pd.Timedelta(days=days)
        # Skip this period if fund hasn't been active this long
        if nav.index[0] > cutoff:
            continue
            
        sub = nav[nav.index >= cutoff]
        if len(sub) < 5:
            continue
        years     = days / 365.25
        fund_cagr = _cagr(sub.iloc[0], sub.iloc[-1], years)
        bm_cagr   = None
        if bm_clipped is not None:
            bm_sub = bm_clipped[bm_clipped.index >= cutoff]
            if len(bm_sub) > 5 and (bm_sub.index[-1] - bm_sub.index[0]).days >= int(days * 0.7):
                bm_cagr = _cagr(bm_sub.iloc[0], bm_sub.iloc[-1], years)

        excess = (fund_cagr - bm_cagr) if (fund_cagr is not None and bm_cagr is not None) else None
        rows.append(TrailingReturn(
            scheme=scheme, period=label, years=round(years, 2),
            cagr_pct=_sn(fund_cagr), bm_cagr=_sn(bm_cagr), excess=_sn(excess),
            as_of=today.date(),
        ))

    # Since inception
    si_days = (today - nav.index[0]).days
    si_yrs  = si_days / 365.25
    si_cagr = _cagr(nav.iloc[0], nav.iloc[-1], si_yrs)
    rows.append(TrailingReturn(
        scheme=scheme, period='SI', years=round(si_yrs, 2),
        cagr_pct=_sn(si_cagr), bm_cagr=None, excess=None,
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

    # Clip benchmark to fund's own last NAV date
    bm_clipped = bm[bm.index <= nav.index[-1]] if bm is not None else None

    for year in range(start_year, end_year + 1):
        year_nav = nav[nav.index.year == year]
        if len(year_nav) < 50:  # need meaningful trading days
            continue
        ret_pct = _simple_return(year_nav.iloc[0], year_nav.iloc[-1])
        bm_ret  = None
        if bm_clipped is not None:
            year_bm = bm_clipped[bm_clipped.index.year == year]
            if len(year_bm) > 10:
                bm_ret = _simple_return(year_bm.iloc[0], year_bm.iloc[-1])

        outperformed = None
        if ret_pct is not None and bm_ret is not None:
            outperformed = ret_pct > bm_ret

        rows.append(CalendarReturn(
            scheme=scheme, year=year, return_pct=_sn(ret_pct),
            bm_return=_sn(bm_ret), outperformed=outperformed,
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
        # Filter out extreme CAGRs (e.g. from price discontinuities in older funds)
        # max_digits=8, decimal_places=4 → max value is 9999.9999
        cagrs = cagrs[np.abs(cagrs) <= 9999.0]

        if len(cagrs) < 10:
            continue

        rows.append(RollingReturn(
            scheme=scheme, window=label, window_days=window_days,
            min_pct  = _sn(float(np.min(cagrs))),
            max_pct  = _sn(float(np.max(cagrs))),
            mean_pct = _sn(float(np.mean(cagrs))),
            median_pct = _sn(float(np.median(cagrs))),
            std_dev  = _sn(float(np.std(cagrs))),
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
        # Skip if the fund hasn't been active for this full period
        if nav.index[0] > cutoff:
            continue
            
        nav_sub = nav[nav.index >= cutoff]
        if len(nav_sub) < 126:   # need minimum 6 months
            continue

        _save_risk_period(scheme, label, cal_days, nav_sub, bm, today, rf_d, rf, cutoff)
        
    # Also do 'SI' (Since Inception)
    if len(nav) >= 126:
        cal_days_si = (nav.index[-1] - nav.index[0]).days
        _save_risk_period(scheme, 'SI', cal_days_si, nav, bm, today, rf_d, rf, nav.index[0])

def _save_risk_period(scheme, label, cal_days, nav_sub, bm, today, rf_d, rf, cutoff):
    from apps.analytics.models import RiskMetrics

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
            std_dev_ann     = _sn(std_ann),
            sharpe_ratio    = _sn(sharpe),
            sortino_ratio   = _sn(sortino),
            max_drawdown    = _sn(max_dd),
            beta            = _sn(beta),
            alpha_ann       = _sn(alpha),
            r_squared       = _sn(r_sq),
            upside_capture  = _sn(up_cap),
            downside_capture= _sn(dn_cap),
            tracking_error  = _sn(track_err),
            info_ratio      = _sn(info_ratio),
            rf_rate_used    = rf,
        )
    )


# ── SIP Simulation ─────────────────────────────────────────────────────────────

def simulate_sip(
    nav_series: pd.Series,
    monthly_amount: float = 10000,
    start_date=None,
) -> Optional[dict]:
    """
    Simulate a monthly SIP investment and compute XIRR.
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
    history    = []
    instalment_count = 0

    for ts, nav_val in monthly.items():
        if nav_val <= 0:
            continue
        units_held += monthly_amount / float(nav_val)
        invested   += monthly_amount
        cashflows.append(-monthly_amount)
        dates.append(ts.to_pydatetime())
        instalment_count += 1
        
        if instalment_count % 12 == 0:
            current_value = units_held * float(nav_val)
            history.append({
                'year': instalment_count // 12,
                'invested': round(invested, 2),
                'value': round(current_value, 2),
                'gain': round(current_value - invested, 2)
            })

    final_nav   = float(nav_series.iloc[-1])
    final_value = units_held * final_nav
    cashflows.append(final_value)
    dates.append(nav_series.index[-1].to_pydatetime())
    
    if instalment_count % 12 != 0 and instalment_count > 0:
        history.append({
            'year': (instalment_count // 12) + 1,
            'invested': round(invested, 2),
            'value': round(final_value, 2),
            'gain': round(final_value - invested, 2)
        })

    xirr = _compute_xirr(cashflows, dates)
    years = (nav_series.index[-1] - nav_series.index[0]).days / 365.25

    return {
        'total_invested':      round(invested, 2),
        'current_value':       round(final_value, 2),
        'absolute_gain':       round(final_value - invested, 2),
        'absolute_return_pct': round((final_value / invested - 1) * 100, 2) if invested > 0 else None,
        'cagr':                round(xirr * 100, 2) if xirr is not None else None,
        'units_held':          round(units_held, 4),
        'sip_instalments':     instalment_count,
        'avg_cost':            round(invested / units_held, 4) if units_held > 0 else None,
        'current_nav':         final_nav,
        'history':             history,
    }


# ── Lumpsum Simulation ─────────────────────────────────────────────────────────

def simulate_lumpsum(
    nav_series: pd.Series,
    principal: float = 100000,
    start_date=None,
) -> Optional[dict]:
    """
    Simulate a lump sum investment.
    """
    if start_date is None:
        start_date = nav_series.index[0]

    nav_series = nav_series.copy()
    nav_series = nav_series[nav_series.index >= pd.Timestamp(start_date)]

    if len(nav_series) < 2:
        return None

    start_nav = float(nav_series.iloc[0])
    end_nav = float(nav_series.iloc[-1])
    
    if start_nav <= 0:
        return None

    units = principal / start_nav
    current_value = units * end_nav
    days = (nav_series.index[-1] - nav_series.index[0]).days
    years = days / 365.25
    cagr = _cagr(principal, current_value, years) if years > 0 else None

    history = []
    start_ts = nav_series.index[0]
    for yr in range(1, int(math.ceil(years)) + 1):
        target_date = start_ts + pd.DateOffset(years=yr)
        if target_date > nav_series.index[-1]:
            target_date = nav_series.index[-1]
        
        subset = nav_series[nav_series.index <= target_date]
        if len(subset) > 0:
            val = units * float(subset.iloc[-1])
            history.append({
                'year': yr,
                'invested': round(principal, 2),
                'value': round(val, 2),
                'gain': round(val - principal, 2)
            })
        if target_date == nav_series.index[-1]:
            break

    return {
        'principal': principal,
        'current_value': round(current_value, 2),
        'gain': round(current_value - principal, 2),
        'absolute_gain': round(current_value - principal, 2),
        'return_pct': round((current_value / principal - 1) * 100, 2),
        'absolute_return_pct': round((current_value / principal - 1) * 100, 2),
        'cagr': cagr,
        'duration_days': days,
        'years': round(years, 2),
        'units_held': round(units, 4),
        'start_nav': start_nav,
        'end_nav': end_nav,
        'history': history,
    }


# ── SWP Simulation ─────────────────────────────────────────────────────────────

def simulate_swp(
    nav_series: pd.Series,
    corpus: float = 1000000,
    monthly_withdrawal: float = 10000,
    start_date=None,
) -> Optional[dict]:
    """
    Simulate a Systematic Withdrawal Plan.
    Assumes corpus is invested at start_date, and withdrawals happen monthly.
    """
    if start_date is None:
        start_date = nav_series.index[0]

    nav_series = nav_series.copy()
    nav_series.index = pd.to_datetime(nav_series.index)
    
    nav_series = nav_series[nav_series.index >= pd.Timestamp(start_date)]
    if len(nav_series) < 2:
        return None

    initial_nav = float(nav_series.iloc[0])
    if initial_nav <= 0:
        return None

    units_held = corpus / initial_nav
    
    monthly = nav_series.resample('MS').first().dropna()
    
    months = 0
    total_withdrawn = 0
    history = []
    
    # Record initial state
    history.append({'month': 0, 'balance': round(corpus, 2), 'withdrawn_cumulative': 0, 'interest_cumulative': 0})
    
    for ts, nav_val in monthly.items():
        if nav_val <= 0:
            continue
            
        current_value = units_held * float(nav_val)
        if current_value <= 0:
            break
            
        # Withdraw
        withdrawal_amount = min(monthly_withdrawal, current_value)
        units_to_sell = withdrawal_amount / float(nav_val)
        
        units_held -= units_to_sell
        total_withdrawn += withdrawal_amount
        months += 1
        
        new_value = units_held * float(nav_val) # after withdrawal
        current_gains = new_value + total_withdrawn - corpus
        
        history.append({
            'month': months,
            'balance': max(0, round(new_value, 2)),
            'withdrawn_cumulative': round(total_withdrawn, 2),
            'interest_cumulative': round(current_gains, 2)
        })
        
        if units_held <= 1e-6:
            units_held = 0
            break

    final_nav = float(nav_series.iloc[-1]) if units_held > 0 else 0
    remaining_corpus = units_held * final_nav
    total_interest_earned = remaining_corpus + total_withdrawn - corpus
    
    fund_years = (nav_series.index[-1] - nav_series.index[0]).days / 365.25
    fund_cagr = _cagr(initial_nav, nav_series.iloc[-1], fund_years) if fund_years > 0 else 0

    return {
        'months_sustained': months,
        'years_sustained': round(months / 12, 1),
        'total_withdrawn': round(total_withdrawn, 2),
        'remaining_corpus': round(remaining_corpus, 2),
        'total_interest_earned': round(total_interest_earned, 2),
        'gain_from_corpus': round(total_interest_earned, 2),
        'corpus': corpus,
        'monthly_withdrawal': monthly_withdrawal,
        'fund_cagr': fund_cagr,
        'history': history,
    }
# ── Helper functions ───────────────────────────────────────────────────────────

def _cagr(start_val, end_val, years: float) -> Optional[float]:
    """Compute CAGR. Returns None on invalid inputs or out-of-range values."""
    try:
        sv, ev = float(start_val), float(end_val)
        if years <= 0 or sv <= 0 or not math.isfinite(sv) or not math.isfinite(ev):
            return None
        res = round(((ev / sv) ** (1.0 / years) - 1) * 100, 4)
        if not math.isfinite(res) or res > 9999.0 or res < -9999.0:
            return None
        return res
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _simple_return(start_val, end_val) -> Optional[float]:
    """Compute simple return %."""
    try:
        sv, ev = float(start_val), float(end_val)
        if sv <= 0 or not math.isfinite(sv) or not math.isfinite(ev):
            return None
        res = round((ev / sv - 1) * 100, 4)
        if not math.isfinite(res) or res > 9999.0 or res < -9999.0:
            return None
        return res
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
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

def compute_rolling_return_stats(nav_series: pd.Series) -> dict:
    """
    Compute rolling return statistics (Avg, Max, Min, % Positive)
    for 1Y (252), 3Y (756), and 5Y (1260) rolling windows.
    Returns a dictionary of stats.
    """
    stats = {}
    if nav_series.empty or len(nav_series) < 252:
        return stats

    for label, window in ROLLING_WINDOWS.items():
        if len(nav_series) < window:
            continue
            
        # Calculate trailing rolling returns
        # using exact day shift if we assume series is daily indexed
        # For simplicity, we assume nav_series is a dense daily business series, 
        # so pct_change(periods=window) works.
        rolling_returns = nav_series.pct_change(periods=window).dropna() * 100
        
        if rolling_returns.empty:
            continue
            
        # If window > 1Y, we typically annualize rolling returns for 3Y, 5Y.
        # But for pct_change, it's cumulative. Let's annualize them.
        years = window / 252.0
        if years > 1.0:
            # CAGR rolling = ( (1 + cumulative_return) ^ (1/years) ) - 1
            # rolling_returns is in %, so convert back to decimal to annualize
            rolling_returns = (((rolling_returns / 100.0 + 1.0) ** (1.0 / years)) - 1.0) * 100

        stats[label] = {
            'avg': round(rolling_returns.mean(), 2),
            'max': round(rolling_returns.max(), 2),
            'min': round(rolling_returns.min(), 2),
            'median': round(rolling_returns.median(), 2),
            'pos_pct': round((rolling_returns > 0).mean() * 100, 1)
        }
        
    return stats

