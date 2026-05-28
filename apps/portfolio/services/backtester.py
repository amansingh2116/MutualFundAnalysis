"""
apps/portfolio/services/backtester.py
======================================
Per-fund investment plan builder + historical NAV replayer.

Each fund in the portfolio gets a list of InvestmentRules — SIP schedules,
lumpsum events, and sell triggers. The simulation engine replays those rules
against actual historical NAV (or index price) data and produces a full
transaction ledger, portfolio value time-series, and computed metrics.

Tactical rebalancing overlays (Trend, MA, Volatility, Composite) are applied
on top of the base plan as independent "what-if" runs for comparison.

Design principles
-----------------
- All computation is pandas/numpy — no Django ORM in hot loops
- Data is fetched from DB at the start; on-demand Yahoo fetch if missing
- Every buy/sell is recorded with exact date, NAV, units, amount
- Tactical overlays pause equity SIPs and redirect to debt parking fund
- No PE data dependency — Strategy 4 stub only, mentioned in conclusion
"""

from __future__ import annotations

import calendar
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import brentq

logger = logging.getLogger("mfanalysis")

RF_ANNUAL = 0.065
TRADING_DAYS = 252

FREQ_TO_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}

STRATEGY_META = {
    "base":      ("Base Plan",          "Your SIP/lumpsum plan run as configured, no tactical overlay."),
    "trend":     ("Trend Filter",       "SIP paused when fund's 12-month return is negative; capital redirected to debt."),
    "ma":        ("MA Filter",          "SIP paused when NAV < 10-month simple moving average; capital redirected to debt."),
    "volatility":("Volatility Control", "SIP paused when 6-month realised volatility exceeds user threshold; capital redirected to debt."),
    "composite": ("Composite Signal",   "SIP paused when both Trend AND MA signals are off simultaneously."),
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES — Input
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class InvestmentRule:
    """A single investment instruction for one fund."""
    rule_type: str              # "sip" | "lumpsum" | "sell_pct"
    # SIP fields
    amount: float = 0.0
    frequency: str = "monthly"  # "monthly" | "quarterly" | "yearly"
    start_date: Optional[date] = None
    end_date: Optional[date] = None   # None → run till backtest end
    step_up_pct: float = 0.0          # annual SIP step-up %
    # Lumpsum fields
    lumpsum_date: Optional[date] = None
    # Sell fields
    sell_pct: float = 100.0           # % of units to sell
    # Trigger (applies to lumpsum buy or sell)
    trigger: Optional[str] = None     # see TRIGGER TYPES below
    trigger_value: Optional[float] = None
    # Internal state (populated during simulation)
    _base_amount: float = field(default=0.0, init=False, repr=False)
    _step_up_year: int = field(default=0, init=False, repr=False)

    # Trigger types supported:
    # "nav_drop_pct"       → buy lumpsum when NAV drops X% from recent 52W high
    # "trailing_stop_pct"  → sell when NAV drops X% from highest since purchase
    # "nav_below_sma"      → pause SIP when NAV < N-month SMA (N = trigger_value)
    # None                 → fire on schedule (SIP) or on lumpsum_date (lumpsum)

    def __post_init__(self):
        self._base_amount = self.amount
        if self.start_date:
            self._step_up_year = self.start_date.year


@dataclass
class FundPlan:
    """Investment plan for a single fund / index."""
    label: str
    source_type: str          # "scheme" | "index"
    source_id: str            # amfi_code (scheme) or index name (index)
    rules: List[InvestmentRule]


@dataclass
class PortfolioPlan:
    """Complete portfolio plan — all funds + rebalancing settings."""
    funds: List[FundPlan]
    rebalance_mode: str           # "none" | "annual" | "threshold"
    rebalance_threshold: float    # drift % before rebalancing (e.g. 5.0)
    rebalance_anchor_month: int   # 1–12 (month for annual rebalance)
    debt_park_source_type: str    # "index" | "scheme"
    debt_park_id: str             # index name or amfi_code for debt parking
    vol_threshold: float          # annualised vol threshold (e.g. 0.20)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    debt_return_pct: float = 7.0


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES — Output
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TxRecord:
    """One simulated transaction in the ledger."""
    date: str
    fund_label: str
    tx_type: str        # "BUY" | "SELL" | "SIP" | "DEBT_PARK" | "REBALANCE"
    nav: float
    units: float
    amount: float
    trigger: Optional[str] = None


@dataclass
class StrategyResult:
    """Metrics for one strategy variant (base or tactical overlay)."""
    strategy_key: str
    strategy_name: str
    description: str
    final_corpus: float
    total_invested: float
    absolute_gain: float
    absolute_return_pct: float
    cagr: Optional[float]
    xirr: Optional[float]
    trailing_1y: Optional[float]
    trailing_3y: Optional[float]
    trailing_5y: Optional[float]
    rolling_5y_min: Optional[float]
    rolling_5y_max: Optional[float]
    rolling_5y_avg: Optional[float]
    volatility_ann: Optional[float]
    max_drawdown: Optional[float]
    sharpe: Optional[float]
    sortino: Optional[float]
    calendar_returns: Dict[int, float]
    downside_quarters: List[Dict]
    dates: List[str]
    portfolio_values: List[float]
    invested_cumulative: List[float]
    equity_ratios: List[float]
    transactions: List[Dict]        # only populated for base strategy
    interpretation: str


@dataclass
class SimulationResult:
    """Full backtest output — base plan + 4 tactical overlays."""
    strategies: List[StrategyResult]
    start_date: str
    end_date: str
    plan_summary: List[Dict]        # serialisable per-fund summary
    data_warnings: List[str]
    conclusion: str


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _load_price_series(source_type: str, source_id: str) -> pd.Series:
    if source_type == "scheme":
        return _load_scheme_nav(source_id)
    elif source_type == "index":
        return _load_index_nav(source_id)
    raise ValueError(f"Unknown source_type: {source_type}")


def _load_scheme_nav(amfi_code: str) -> pd.Series:
    from apps.funds.models import NAVHistory, Scheme
    from apps.funds.services import get_or_fetch_nav_history

    try:
        scheme = Scheme.objects.get(amfi_code=amfi_code)
    except Scheme.DoesNotExist:
        raise ValueError(f"Scheme '{amfi_code}' not found.")

    if NAVHistory.objects.filter(scheme=scheme).count() < 30:
        get_or_fetch_nav_history(scheme)

    qs = NAVHistory.objects.filter(scheme=scheme).values("date", "nav").order_by("date")
    df = pd.DataFrame(list(qs))
    if df.empty:
        raise ValueError(f"No NAV data for scheme {amfi_code}.")
    df["date"] = pd.to_datetime(df["date"])
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    s = df.set_index("date")["nav"].dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def _load_index_nav(index_name: str) -> pd.Series:
    from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV

    try:
        idx = BenchmarkIndex.objects.get(name=index_name)
    except BenchmarkIndex.DoesNotExist:
        raise ValueError(f"Index '{index_name}' not found.")

    count = BenchmarkNAV.objects.filter(index=idx).count()
    if count < 30:
        try:
            from apps.benchmarks.registry import fetch_yahoo_history_for_benchmark
            series, _ = fetch_yahoo_history_for_benchmark(index_name)
            if not series.empty:
                objs = [
                    BenchmarkNAV(index=idx, date=d.date(), close=float(v), source="yfinance")
                    for d, v in series.items()
                ]
                BenchmarkNAV.objects.bulk_create(objs, ignore_conflicts=True)
        except Exception as exc:
            logger.warning("On-demand fetch failed for '%s': %s", index_name, exc)

    qs = BenchmarkNAV.objects.filter(index=idx).values("date", "close").order_by("date")
    df = pd.DataFrame(list(qs))
    if df.empty:
        raise ValueError(f"No price data for index '{index_name}'.")
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    s = df.set_index("date")["close"].dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def _nav_on_or_before(series: pd.Series, d: date) -> Optional[float]:
    ts = pd.Timestamp(d)
    sub = series[series.index <= ts]
    return float(sub.iloc[-1]) if not sub.empty else None


# ═══════════════════════════════════════════════════════════════════════════════
# SIP DATE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def _sip_dates(rule: InvestmentRule, plan_end: date, plan_start: Optional[date] = None) -> List[date]:
    """Generate all SIP investment dates for a rule.
    Falls back to plan_start when rule.start_date is None.
    """
    start = rule.start_date or plan_start
    if not start:
        return []
    end = rule.end_date or plan_end
    if start > end:
        return []
    freq_months = FREQ_TO_MONTHS.get(rule.frequency, 1)
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur)
        m = cur.month - 1 + freq_months
        y = cur.year + m // 12
        m = m % 12 + 1
        last_day = calendar.monthrange(y, m)[1]
        cur = date(y, m, min(cur.day, last_day))
    return dates


def _amount_on_date(rule: InvestmentRule, sip_start: date, d: date) -> float:
    """Return SIP amount on a specific date, applying annual step-up."""
    if rule.step_up_pct <= 0:
        return rule.amount
    years_elapsed = d.year - sip_start.year
    return rule.amount * ((1 + rule.step_up_pct / 100) ** years_elapsed)


# ═══════════════════════════════════════════════════════════════════════════════
# TRIGGER EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

def _check_lumpsum_trigger(rule: InvestmentRule, series: pd.Series, d: date,
                            fired_dates: set) -> bool:
    """Return True if a trigger-based lumpsum should fire on date d."""
    if d in fired_dates:
        return False
    if rule.trigger == "nav_drop_pct":
        # Buy when NAV drops X% from 52-week high
        ts = pd.Timestamp(d)
        window_start = ts - pd.Timedelta(days=365)
        window = series[(series.index >= window_start) & (series.index <= ts)]
        if window.empty:
            return False
        peak = float(window.max())
        current = float(window.iloc[-1])
        drop_pct = (peak - current) / peak * 100
        return drop_pct >= (rule.trigger_value or 10)
    return False


def _check_sell_trigger(rule: InvestmentRule, series: pd.Series, d: date,
                         cost_basis_date: Optional[date]) -> bool:
    """Return True if a trailing-stop sell trigger fires."""
    if rule.trigger != "trailing_stop_pct":
        return False
    ts = pd.Timestamp(d)
    start = pd.Timestamp(cost_basis_date) if cost_basis_date else series.index[0]
    window = series[(series.index >= start) & (series.index <= ts)]
    if len(window) < 2:
        return False
    peak = float(window.max())
    current = float(window.iloc[-1])
    drop_pct = (peak - current) / peak * 100
    return drop_pct >= (rule.trigger_value or 15)


def _sma_signal(series: pd.Series, d: date, months: int) -> bool:
    """Return True if NAV > N-month SMA (equity ON signal)."""
    ts = pd.Timestamp(d)
    window_start = ts - pd.DateOffset(months=months)
    window = series[(series.index >= window_start) & (series.index <= ts)]
    if len(window) < 5:
        return True  # default to ON if insufficient data
    sma = float(window.mean())
    current = _nav_on_or_before(series, d)
    return current is not None and current > sma


def _trend_signal(series: pd.Series, d: date) -> bool:
    """Return True if 12M trailing return > 0."""
    ts = pd.Timestamp(d)
    past = ts - pd.DateOffset(months=12)
    sub = series[series.index <= ts]
    past_sub = series[series.index <= past]
    if sub.empty or past_sub.empty:
        return True
    return float(sub.iloc[-1]) > float(past_sub.iloc[-1])


def _vol_signal(series: pd.Series, d: date, threshold: float) -> bool:
    """Return True if 6M realised vol < threshold (annualised)."""
    ts = pd.Timestamp(d)
    window_start = ts - pd.DateOffset(months=6)
    window = series[(series.index >= window_start) & (series.index <= ts)]
    if len(window) < 10:
        return True
    rets = window.pct_change().dropna()
    if rets.empty:
        return True
    vol = rets.std() * math.sqrt(TRADING_DAYS)
    return vol < threshold


def _get_equity_signal(strategy_key: str, series: pd.Series, d: date,
                        vol_threshold: float) -> bool:
    """Return True if equity should be ON for this strategy on date d."""
    if strategy_key == "base":
        return True
    if strategy_key == "trend":
        return _trend_signal(series, d)
    if strategy_key == "ma":
        return _sma_signal(series, d, months=10)
    if strategy_key == "volatility":
        return _vol_signal(series, d, vol_threshold)
    if strategy_key == "composite":
        t = _trend_signal(series, d)
        m = _sma_signal(series, d, months=10)
        return (int(t) + int(m)) / 2 > 0.5
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# CORE SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

def _make_synthetic_debt_series(plan_start: date, plan_end: date,
                                annual_return: float = 0.07) -> pd.Series:
    """Create a synthetic daily price series at a fixed annual growth rate."""
    dates = pd.date_range(start=plan_start, end=plan_end, freq='D')
    daily_r = (1 + annual_return) ** (1 / 365) - 1
    values = [100.0 * (1 + daily_r) ** i for i in range(len(dates))]
    return pd.Series(values, index=dates)


def _simulate_strategy(
    plan: PortfolioPlan,
    price_map: Dict[str, pd.Series],
    debt_series: Optional[pd.Series],
    strategy_key: str,
    plan_start: date,
    plan_end: date,
) -> StrategyResult:
    """
    Replay the portfolio plan against historical NAV for one strategy variant.
    """
    meta = STRATEGY_META.get(strategy_key, (strategy_key, ""))
    strategy_name, strategy_desc = meta

    # ── Per-fund state ────────────────────────────────────────────────────────
    fund_state: Dict[str, Dict] = {}
    for fp in plan.funds:
        fund_state[fp.source_id] = {
            "units": 0.0,
            "cost_basis_date": None,
            "trigger_fired_dates": set(),
        }
    debt_units = 0.0

    total_invested = 0.0
    tx_ledger: List[TxRecord] = []
    cf_list: List[Tuple[date, float]] = []

    # ── Pre-build event lookup: date → list[(fund_plan, rule, sip_start)] ─────
    # Key insight: we pre-generate all SIP dates here so the main loop just
    # does a dict lookup — no fragile in-loop month arithmetic.
    from collections import defaultdict
    event_lookup: Dict[date, List[tuple]] = defaultdict(list)

    for fp in plan.funds:
        for rule in fp.rules:
            if rule.rule_type == "sip":
                sip_start = rule.start_date or plan_start
                for sip_date in _sip_dates(rule, plan_end, plan_start):
                    if plan_start <= sip_date <= plan_end:
                        event_lookup[sip_date].append((fp, rule, sip_start))
            elif rule.rule_type == "lumpsum" and rule.lumpsum_date and not rule.trigger:
                if plan_start <= rule.lumpsum_date <= plan_end:
                    event_lookup[rule.lumpsum_date].append((fp, rule, None))

    # Chart dates (weekly) + all event dates
    chart_dates_pd = pd.date_range(start=plan_start, end=plan_end, freq="W")
    chart_dates = [ts.date() for ts in chart_dates_pd]
    if not chart_dates or chart_dates[-1] != plan_end:
        chart_dates.append(plan_end)
    chart_dates_set = set(chart_dates)

    all_dates = sorted(chart_dates_set | set(event_lookup.keys()))

    # ── Trigger-based lumpsum tracking ───────────────────────────────────────
    trigger_lumpsum_fired: Dict[str, set] = {fp.source_id: set() for fp in plan.funds}

    # ── Target weights for rebalancing ───────────────────────────────────────
    total_sip = sum(r.amount for fp in plan.funds for r in fp.rules if r.rule_type == "sip")
    target_weights: Dict[str, float] = {}
    if total_sip > 0:
        for fp in plan.funds:
            fp_sip = sum(r.amount for r in fp.rules if r.rule_type == "sip")
            target_weights[fp.source_id] = fp_sip / total_sip
    else:
        equal_w = 1.0 / len(plan.funds) if plan.funds else 1.0
        for fp in plan.funds:
            target_weights[fp.source_id] = equal_w

    last_rebalance_year = plan_start.year - 1

    # ── Main simulation loop ──────────────────────────────────────────────────
    chart_values: List[float] = []
    chart_invested: List[float] = []
    chart_equity_ratio: List[float] = []
    chart_date_strs: List[str] = []

    for d in all_dates:
        is_chart_date = d in chart_dates_set

        # ── Process scheduled SIP / lumpsum events ────────────────────────────
        for fp, rule, sip_start in event_lookup.get(d, []):
            series = price_map.get(fp.source_id)
            if series is None:
                continue
            nav = _nav_on_or_before(series, d)
            if nav is None or nav <= 0:
                continue

            state = fund_state[fp.source_id]
            invest_amount = (_amount_on_date(rule, sip_start, d)
                             if rule.rule_type == "sip" else rule.amount)
            if invest_amount <= 0:
                continue

            # Tactical overlay: check equity signal for SIPs
            if rule.rule_type == "sip" and strategy_key != "base":
                eq_on = _get_equity_signal(strategy_key, series, d, plan.vol_threshold)
                if not eq_on:
                    # Redirect to debt parking
                    if debt_series is not None:
                        debt_nav = _nav_on_or_before(debt_series, d)
                        if debt_nav and debt_nav > 0:
                            debt_units += invest_amount / debt_nav
                            total_invested += invest_amount
                            cf_list.append((d, -invest_amount))
                    continue

            # Invest in the fund
            units_bought = invest_amount / nav
            state["units"] += units_bought
            total_invested += invest_amount
            cf_list.append((d, -invest_amount))
            if state["cost_basis_date"] is None:
                state["cost_basis_date"] = d
            if strategy_key == "base":
                tx_type = "SIP" if rule.rule_type == "sip" else "BUY"
                tx_ledger.append(TxRecord(
                    date=d.isoformat(), fund_label=fp.label,
                    tx_type=tx_type, nav=nav, units=units_bought, amount=invest_amount
                ))

        # ── Trigger-based lumpsums (checked every date) ───────────────────────
        for fp in plan.funds:
            series = price_map.get(fp.source_id)
            if series is None:
                continue
            nav = _nav_on_or_before(series, d)
            if nav is None or nav <= 0:
                continue
            state = fund_state[fp.source_id]
            for rule in fp.rules:
                if rule.rule_type != "lumpsum" or rule.trigger != "nav_drop_pct":
                    continue
                if _check_lumpsum_trigger(rule, series, d, trigger_lumpsum_fired[fp.source_id]):
                    trigger_lumpsum_fired[fp.source_id].add(d)
                    invest_amount = rule.amount
                    if invest_amount > 0:
                        units_bought = invest_amount / nav
                        state["units"] += units_bought
                        total_invested += invest_amount
                        cf_list.append((d, -invest_amount))
                        if state["cost_basis_date"] is None:
                            state["cost_basis_date"] = d
                        if strategy_key == "base":
                            tx_ledger.append(TxRecord(
                                date=d.isoformat(), fund_label=fp.label,
                                tx_type="BUY", nav=nav, units=units_bought,
                                amount=invest_amount, trigger="nav_drop_pct"
                            ))

        # ── Sell triggers (checked every date) ───────────────────────────────
        for fp in plan.funds:
            series = price_map.get(fp.source_id)
            if series is None:
                continue
            nav = _nav_on_or_before(series, d)
            if nav is None or nav <= 0:
                continue
            state = fund_state[fp.source_id]
            for rule in fp.rules:
                if rule.rule_type != "sell_pct":
                    continue
                should_sell = False
                if rule.trigger == "trailing_stop_pct":
                    should_sell = _check_sell_trigger(rule, series, d, state["cost_basis_date"])
                elif rule.end_date and d == rule.end_date and state["units"] > 0:
                    should_sell = True
                if should_sell and state["units"] > 0:
                    units_to_sell = state["units"] * (rule.sell_pct / 100)
                    proceeds = units_to_sell * nav
                    state["units"] -= units_to_sell
                    cf_list.append((d, proceeds))
                    if strategy_key == "base":
                        tx_ledger.append(TxRecord(
                            date=d.isoformat(), fund_label=fp.label,
                            tx_type="SELL", nav=nav, units=units_to_sell,
                            amount=proceeds, trigger=rule.trigger
                        ))

        # ── Annual rebalancing ────────────────────────────────────────────────
        if (plan.rebalance_mode == "annual"
                and d.month == plan.rebalance_anchor_month
                and d.year > last_rebalance_year):
            _rebalance(fund_state, debt_units, plan.funds, price_map, debt_series,
                       target_weights, d, tx_ledger if strategy_key == "base" else None)
            last_rebalance_year = d.year
        elif plan.rebalance_mode == "threshold":
            _maybe_threshold_rebalance(
                fund_state, debt_units, plan.funds, price_map, debt_series,
                target_weights, d, plan.rebalance_threshold,
                tx_ledger if strategy_key == "base" else None
            )

        # ── Portfolio valuation ───────────────────────────────────────────────
        if is_chart_date:
            pv = _portfolio_value(fund_state, debt_units, plan.funds, price_map, debt_series, d)
            equity_val = _equity_value(fund_state, plan.funds, price_map, d)
            chart_date_strs.append(d.isoformat())
            chart_values.append(round(pv, 2))
            chart_invested.append(round(total_invested, 2))
            eq_ratio = (equity_val / pv * 100) if pv > 0 else 0.0
            chart_equity_ratio.append(round(eq_ratio, 1))

    # ── Final corpus ──────────────────────────────────────────────────────────
    final_corpus = chart_values[-1] if chart_values else 0.0
    if final_corpus > 0:
        cf_list.append((plan_end, final_corpus))

    # ── Metrics ───────────────────────────────────────────────────────────────
    xirr_val = _compute_xirr(cf_list)
    port_series = pd.Series(chart_values, index=pd.to_datetime(chart_date_strs))
    cagr = _series_cagr(port_series, total_invested)
    trailing_1y = _trailing_return(port_series, 365)
    trailing_3y = _trailing_return(port_series, 365 * 3)
    trailing_5y = _trailing_return(port_series, 365 * 5)
    r5min, r5max, r5avg = _rolling_5y_stats(port_series)
    vol = _annualised_vol(port_series)
    max_dd = _max_drawdown(port_series)
    sharpe = _sharpe(port_series)
    sortino = _sortino(port_series)
    cal_rets = _calendar_returns(port_series)
    downside_q = _downside_quarters(port_series)
    abs_gain = final_corpus - total_invested
    abs_ret = (abs_gain / total_invested * 100) if total_invested > 0 else 0
    interp = _interpret(strategy_name, cagr, vol, max_dd, xirr_val)

    return StrategyResult(
        strategy_key=strategy_key,
        strategy_name=strategy_name,
        description=strategy_desc,
        final_corpus=round(final_corpus, 2),
        total_invested=round(total_invested, 2),
        absolute_gain=round(abs_gain, 2),
        absolute_return_pct=round(abs_ret, 2),
        cagr=cagr,
        xirr=xirr_val,
        trailing_1y=trailing_1y,
        trailing_3y=trailing_3y,
        trailing_5y=trailing_5y,
        rolling_5y_min=r5min,
        rolling_5y_max=r5max,
        rolling_5y_avg=r5avg,
        volatility_ann=vol,
        max_drawdown=max_dd,
        sharpe=sharpe,
        sortino=sortino,
        calendar_returns=cal_rets,
        downside_quarters=downside_q,
        dates=chart_date_strs,
        portfolio_values=chart_values,
        invested_cumulative=chart_invested,
        equity_ratios=chart_equity_ratio,
        transactions=[
            {
                "date": t.date, "fund": t.fund_label, "type": t.tx_type,
                "nav": round(t.nav, 4), "units": round(t.units, 4),
                "amount": round(t.amount, 2), "trigger": t.trigger or "",
            }
            for t in tx_ledger
        ],
        interpretation=interp,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REBALANCING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _portfolio_value(fund_state, debt_units, funds, price_map, debt_series, d):
    total = 0.0
    for fp in funds:
        nav = _nav_on_or_before(price_map.get(fp.source_id, pd.Series(dtype=float)), d)
        if nav:
            total += fund_state[fp.source_id]["units"] * nav
    if debt_series is not None:
        dnav = _nav_on_or_before(debt_series, d)
        if dnav:
            total += debt_units * dnav
    return total


def _equity_value(fund_state, funds, price_map, d):
    total = 0.0
    for fp in funds:
        nav = _nav_on_or_before(price_map.get(fp.source_id, pd.Series(dtype=float)), d)
        if nav:
            total += fund_state[fp.source_id]["units"] * nav
    return total


def _rebalance(fund_state, debt_units, funds, price_map, debt_series,
               target_weights, d, tx_ledger):
    total_val = _portfolio_value(fund_state, debt_units, funds, price_map, debt_series, d)
    if total_val <= 0:
        return
    for fp in funds:
        series = price_map.get(fp.source_id)
        if series is None:
            continue
        nav = _nav_on_or_before(series, d)
        if not nav or nav <= 0:
            continue
        target_val = total_val * target_weights.get(fp.source_id, 0)
        current_val = fund_state[fp.source_id]["units"] * nav
        delta_val = target_val - current_val
        if abs(delta_val) < 100:  # ignore tiny drift
            continue
        delta_units = delta_val / nav
        fund_state[fp.source_id]["units"] += delta_units
        if tx_ledger is not None:
            tx_ledger.append(TxRecord(
                date=d.isoformat(), fund_label=fp.label,
                tx_type="REBALANCE", nav=nav, units=abs(delta_units),
                amount=abs(delta_val),
            ))


def _maybe_threshold_rebalance(fund_state, debt_units, funds, price_map, debt_series,
                                target_weights, d, threshold_pct, tx_ledger):
    total_val = _portfolio_value(fund_state, debt_units, funds, price_map, debt_series, d)
    if total_val <= 0:
        return
    for fp in funds:
        series = price_map.get(fp.source_id)
        if series is None:
            continue
        nav = _nav_on_or_before(series, d)
        if not nav or nav <= 0:
            continue
        current_val = fund_state[fp.source_id]["units"] * nav
        current_pct = current_val / total_val * 100
        target_pct = target_weights.get(fp.source_id, 0) * 100
        if abs(current_pct - target_pct) >= threshold_pct:
            _rebalance(fund_state, debt_units, funds, price_map, debt_series,
                       target_weights, d, tx_ledger)
            break  # one rebalance per date is enough


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _cagr(start_val: float, end_val: float, years: float) -> Optional[float]:
    try:
        if years <= 0 or start_val <= 0:
            return None
        return round(((end_val / start_val) ** (1.0 / years) - 1) * 100, 2)
    except Exception:
        return None


def _series_cagr(series: pd.Series, total_invested: float) -> Optional[float]:
    if series.empty or total_invested <= 0:
        return None
    non_zero = series[series > 0]
    if len(non_zero) < 2:
        return None
    years = (non_zero.index[-1] - non_zero.index[0]).days / 365.25
    return _cagr(float(non_zero.iloc[0]), float(non_zero.iloc[-1]), years)


def _trailing_return(series: pd.Series, days: int) -> Optional[float]:
    if len(series) < 2:
        return None
    end_ts = series.index[-1]
    start_ts = end_ts - pd.Timedelta(days=days)
    sub = series[series.index >= start_ts]
    if len(sub) < 2:
        return None
    return _cagr(float(sub.iloc[0]), float(sub.iloc[-1]), days / 365.25)


def _rolling_5y_stats(series: pd.Series):
    window = 52 * 5
    if len(series) < window + 10:
        return None, None, None
    re = series.iloc[window:]
    rs = series.iloc[:-window].copy()
    rs.index = re.index
    mask = (rs.values > 0) & (re.values > 0)
    cagrs = ((re.values[mask] / rs.values[mask]) ** (1/5) - 1) * 100
    cagrs = cagrs[np.isfinite(cagrs)]
    if len(cagrs) < 4:
        return None, None, None
    return round(float(np.min(cagrs)), 2), round(float(np.max(cagrs)), 2), round(float(np.mean(cagrs)), 2)


def _annualised_vol(series: pd.Series) -> Optional[float]:
    if len(series) < 10:
        return None
    rets = series.pct_change().dropna()
    if rets.empty:
        return None
    return round(float(rets.std() * math.sqrt(52) * 100), 2)


def _max_drawdown(series: pd.Series) -> Optional[float]:
    if series.empty:
        return None
    # Only compute drawdown over periods where portfolio has value
    pos = series[series > 0]
    if len(pos) < 2:
        return None
    running_max = pos.cummax()
    dd = (pos - running_max) / running_max * 100
    return round(float(dd.min()), 2)


def _sharpe(series: pd.Series) -> Optional[float]:
    if len(series) < 52:
        return None
    rets = series.pct_change().dropna()
    rf_w = RF_ANNUAL / 52
    excess = rets - rf_w
    if excess.std() == 0:
        return None
    return round(float(excess.mean() / excess.std() * math.sqrt(52)), 2)


def _sortino(series: pd.Series) -> Optional[float]:
    if len(series) < 52:
        return None
    rets = series.pct_change().dropna()
    rf_w = RF_ANNUAL / 52
    excess = rets - rf_w
    down = rets[rets < rf_w]
    if len(down) < 5 or down.std() == 0:
        return None
    return round(float(excess.mean() * math.sqrt(52) / (down.std() * math.sqrt(52))), 2)


def _calendar_returns(series: pd.Series) -> Dict[int, float]:
    result = {}
    if series.empty:
        return result
    for year in series.index.year.unique():
        yr = series[series.index.year == year]
        yr_pos = yr[yr > 0]  # only non-zero values
        if len(yr_pos) < 5:
            continue
        first_val = float(yr_pos.iloc[0])
        last_val = float(yr_pos.iloc[-1])
        if first_val <= 0:
            continue
        result[int(year)] = round((last_val / first_val - 1) * 100, 2)
    return result


def _downside_quarters(series: pd.Series) -> List[Dict]:
    results = []
    if series.empty:
        return results
    quarterly = series.resample("QS").last()
    if len(quarterly) < 2:
        return results
    for i in range(1, len(quarterly)):
        sv = float(quarterly.iloc[i - 1])
        ev = float(quarterly.iloc[i])
        if sv <= 0:
            continue
        ret = (ev / sv - 1) * 100
        if ret >= 0:
            continue
        qstart = quarterly.index[i - 1]
        results.append({
            "quarter": f"Q{(qstart.month - 1) // 3 + 1} {qstart.year}",
            "start_date": qstart.strftime("%Y-%m-%d"),
            "portfolio_return": round(ret, 2),
        })
    return results


def _compute_xirr(cf_list: List[Tuple[date, float]]) -> Optional[float]:
    if len(cf_list) < 2:
        return None
    dates = [cf[0] for cf in cf_list]
    amounts = [cf[1] for cf in cf_list]
    if all(a <= 0 for a in amounts) or all(a >= 0 for a in amounts):
        return None
    def xnpv(rate):
        t0 = dates[0]
        return sum(cf / (1 + rate) ** ((d - t0).days / 365.0) for cf, d in zip(amounts, dates))
    try:
        rate = brentq(xnpv, -0.9999, 100.0, maxiter=500)
        return round(float(rate) * 100, 2) if math.isfinite(rate) else None
    except Exception:
        return None


def _interpret(name, cagr, vol, max_dd, xirr):
    parts = []
    if cagr is not None:
        parts.append(f"CAGR of {cagr:.1f}%.")
    if vol is not None:
        level = "low" if vol < 12 else ("moderate" if vol < 20 else "high")
        parts.append(f"Annualised volatility {vol:.1f}% ({level}).")
    if max_dd is not None:
        parts.append(f"Maximum drawdown {max_dd:.1f}%.")
    if xirr is not None:
        parts.append(f"SIP XIRR {xirr:.1f}%.")
    return " ".join(parts) if parts else "Insufficient data."


def _generate_conclusion(strategies: List[StrategyResult]) -> str:
    if not strategies:
        return ""
    base = next((s for s in strategies if s.strategy_key == "base"), strategies[0])
    best = max(strategies, key=lambda s: s.cagr or 0)
    lines = [f"### Portfolio Backtest Conclusion\n"]
    lines.append(f"**Base plan CAGR**: {base.cagr:.1f}% with XIRR of {base.xirr:.1f}%." if base.cagr and base.xirr else "")
    if best.strategy_key != "base" and best.cagr and base.cagr:
        diff = best.cagr - base.cagr
        lines.append(f"**Best overlay**: {best.strategy_name} added {diff:+.1f}% CAGR vs the base plan.")
    safest = min(strategies, key=lambda s: abs(s.max_drawdown or 100))
    if safest:
        lines.append(f"**Least drawdown**: {safest.strategy_name} ({safest.max_drawdown:.1f}%).")
    lines.append("\n> Past performance does not guarantee future results. Strategy 4 (PE-based) is disabled — PE time-series data not yet ingested.")
    return "\n".join(l for l in lines if l)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run_plan_simulation(plan: PortfolioPlan) -> SimulationResult:
    """
    Run all strategy variants on the portfolio plan.
    Returns a SimulationResult with base + 4 tactical overlays.
    """
    warnings: List[str] = []

    # Load price data for all funds
    price_map: Dict[str, pd.Series] = {}
    for fp in plan.funds:
        try:
            price_map[fp.source_id] = _load_price_series(fp.source_type, fp.source_id)
        except Exception as exc:
            warnings.append(f"No data for '{fp.label}': {exc}")
            logger.warning("Price load failed for %s: %s", fp.source_id, exc)

    if not price_map:
        raise ValueError("No price data could be loaded for any fund in the plan.")

    # Load debt parking series — fall back to synthetic if unavailable
    debt_series: Optional[pd.Series] = None
    if plan.debt_park_id and plan.debt_park_source_type:
        try:
            debt_series = _load_price_series(plan.debt_park_source_type, plan.debt_park_id)
        except Exception as exc:
            warnings.append(
                f"Debt fund '{plan.debt_park_id}' unavailable ({exc}). "
                f"Using {plan.debt_return_pct}% p.a. synthetic debt model for parked capital."
            )

    # Determine date range from EQUITY funds only (debt must not constrain it)
    equity_series_list = list(price_map.values())
    data_starts = [s.index[0].date() for s in equity_series_list if not s.empty]
    data_ends   = [s.index[-1].date() for s in equity_series_list if not s.empty]

    plan_start = plan.start_date
    plan_end   = plan.end_date or date.today()

    if data_starts:
        earliest_equity = max(data_starts)
        if plan_start is None or plan_start < earliest_equity:
            plan_start = earliest_equity
    if data_ends:
        latest_equity = min(data_ends)
        if plan_end > latest_equity:
            plan_end = latest_equity

    if plan_start is None or plan_start >= plan_end:
        raise ValueError("No overlapping date range available across selected funds.")

    # Build synthetic debt series if not loaded
    if debt_series is None:
        debt_series = _make_synthetic_debt_series(plan_start, plan_end, annual_return=plan.debt_return_pct / 100.0)
        if not plan.debt_park_id:
            warnings.append(f"No debt parking fund selected — parked capital earns synthetic {plan.debt_return_pct}% p.a.")


    years = (plan_end - plan_start).days / 365.25
    if years < 1:
        warnings.append("Less than 1 year of data available. Results may not be meaningful.")
    elif years < 5:
        warnings.append(f"Only {years:.1f} years of data — 5-year rolling stats may be unavailable.")

    # Run all strategies
    strategy_keys = ["base", "trend", "ma", "volatility", "composite"]
    results: List[StrategyResult] = []
    for key in strategy_keys:
        try:
            result = _simulate_strategy(plan, price_map, debt_series, key, plan_start, plan_end)
            results.append(result)
        except Exception as exc:
            logger.error("Strategy '%s' failed: %s", key, exc, exc_info=True)
            warnings.append(f"Overlay '{STRATEGY_META[key][0]}' could not be computed: {exc}")

    conclusion = _generate_conclusion(results)

    plan_summary = []
    for fp in plan.funds:
        sip_rules = [r for r in fp.rules if r.rule_type == "sip"]
        lump_rules = [r for r in fp.rules if r.rule_type == "lumpsum"]
        plan_summary.append({
            "label": fp.label,
            "source_type": fp.source_type,
            "source_id": fp.source_id,
            "sip_count": len(sip_rules),
            "lump_count": len(lump_rules),
            "monthly_sip": sum(r.amount for r in sip_rules if r.frequency == "monthly"),
        })

    return SimulationResult(
        strategies=results,
        start_date=plan_start.isoformat(),
        end_date=plan_end.isoformat(),
        plan_summary=plan_summary,
        data_warnings=warnings,
        conclusion=conclusion,
    )
