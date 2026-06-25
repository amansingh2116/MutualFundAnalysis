"""Derived data helpers for the mutual fund screener."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import logging
import math
import re

from django.utils import timezone

from apps.benchmarks.registry import BENCHMARK_DEFINITIONS, benchmark_for, infer_category

logger = logging.getLogger("mfanalysis")

CATEGORY_GROUPS = ("Debt", "Equity", "Hybrid", "Other", "Solution Oriented")

# ── Extensible basket definitions for "Top Performing Funds" section ──────────
# Add new baskets here freely — no template changes needed.
# Values are kwargs passed directly to FundScreenerSnapshot.objects.filter().
TOP_FUND_BASKETS: dict[str, dict] = {
    "Large Cap":    {"scheme_sub_category": "Large Cap Fund"},
    "Mid Cap":      {"scheme_sub_category": "Mid Cap Fund"},
    "Small Cap":    {"scheme_sub_category": "Small Cap Fund"},
    "Flexi Cap":    {"scheme_sub_category": "Flexi Cap Fund"},
    "ELSS":         {"scheme_sub_category": "ELSS"},
    "Hybrid":       {"category_group": "Hybrid"},
    "Debt":         {"category_group": "Debt"},
    "Index Funds":  {"scheme_sub_category": "Index Funds"},
}

SUB_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Banking and PSU Fund", ("banking and psu", "banking & psu"), "Debt"),
    ("Corporate Bond Fund", ("corporate bond",), "Debt"),
    ("Credit Risk Fund", ("credit risk",), "Debt"),
    ("Dynamic Bond", ("dynamic bond",), "Debt"),
    ("Floater Fund", ("floater",), "Debt"),
    ("Gilt Fund with 10 year constant duration", ("10 year constant", "10 yr constant"), "Debt"),
    ("Gilt Fund", ("gilt", "g-sec", "gsec"), "Debt"),
    ("Liquid Fund", ("liquid fund", "liquid plan"), "Debt"),
    ("Long Duration Fund", ("long duration",), "Debt"),
    ("Low Duration Fund", ("low duration",), "Debt"),
    ("Medium to Long Duration Fund", ("medium to long", "medium and long"), "Debt"),
    ("Medium Duration Fund", ("medium duration",), "Debt"),
    ("Money Market Fund", ("money market",), "Debt"),
    ("Overnight Fund", ("overnight",), "Debt"),
    ("Short Duration Fund", ("short duration", "short term"), "Debt"),
    ("Ultra Short Duration Fund", ("ultra short", "ultrashort"), "Debt"),
    ("Contra Fund", ("contra fund",), "Equity"),
    ("Dividend Yield Fund", ("dividend yield",), "Equity"),
    ("ELSS", ("elss", "tax saver", "tax saving"), "Equity"),
    ("Flexi Cap Fund", ("flexi cap", "flexicap"), "Equity"),
    ("Focused Fund", ("focused fund", "focus fund"), "Equity"),
    ("Large & Mid Cap Fund", ("large & mid", "large and mid"), "Equity"),
    ("Large Cap Fund", ("large cap", "largecap", "bluechip", "blue chip"), "Equity"),
    ("Mid Cap Fund", ("mid cap", "midcap", "mid-cap"), "Equity"),
    ("Multi Cap Fund", ("multi cap", "multicap"), "Equity"),
    ("Sectoral/ Thematic", ("sectoral", "thematic", "theme"), "Equity"),
    ("Small Cap Fund", ("small cap", "smallcap", "small-cap"), "Equity"),
    ("Value Fund", ("value fund", "value and contra"), "Equity"),
    ("Aggressive Hybrid Fund", ("aggressive hybrid", "equity hybrid"), "Hybrid"),
    ("Arbitrage Fund", ("arbitrage",), "Hybrid"),
    ("Conservative Hybrid Fund", ("conservative hybrid",), "Hybrid"),
    ("Dynamic Asset Allocation or Balanced Advantage", ("balanced advantage", "dynamic asset allocation"), "Hybrid"),
    ("Equity Savings", ("equity savings",), "Hybrid"),
    ("Multi Asset Allocation", ("multi asset", "multi-asset"), "Hybrid"),
    ("FoF Domestic", ("fof domestic", "fund of fund domestic"), "Other"),
    ("FoF Overseas", ("fof overseas", "overseas", "international", "global", "nasdaq", "s&p 500"), "Other"),
    ("Gold ETF", ("gold etf", "gold exchange traded"), "Other"),
    ("Index Funds", ("index fund", "index funds"), "Other"),
    ("Other ETFs", ("etf",), "Other"),
    ("Children's Fund", ("children", "child"), "Solution Oriented"),
    ("Retirement Fund", ("retirement",), "Solution Oriented"),
)


def refresh_snapshot_for_scheme(scheme):
    """Build and persist a screener snapshot for one scheme."""
    from apps.analytics.models import RiskMetrics, RollingReturn, TrailingReturn
    from apps.funds.models import FundScreenerSnapshot, NAVHistory

    latest_trailing = _latest_rows_by_key(
        TrailingReturn.objects.filter(scheme=scheme).order_by("period", "-as_of"),
        "period",
    )
    latest_rolling = _latest_rows_by_key(
        RollingReturn.objects.filter(scheme=scheme).order_by("window", "-as_of"),
        "window",
    )
    latest_risk = _latest_rows_by_key(
        RiskMetrics.objects.filter(scheme=scheme).order_by("period", "-as_of"),
        "period",
    )
    
    from apps.analytics.models import CalendarReturn
    calendar_returns = CalendarReturn.objects.filter(scheme=scheme).order_by("-year")
    calendar_returns_json = {}
    for cr in calendar_returns:
        calendar_returns_json[str(cr.year)] = float(cr.return_pct) if cr.return_pct is not None else None

    meta = getattr(scheme, "meta", None)
    first_nav_date = (
        NAVHistory.objects.filter(scheme=scheme).order_by("date").values_list("date", flat=True).first()
    )
    latest_nav_date = scheme.nav_date or (
        NAVHistory.objects.filter(scheme=scheme).order_by("-date").values_list("date", flat=True).first()
    )

    category_text = _category_text(scheme, meta)
    category_group, sub_category = classify_scheme(category_text, scheme.scheme_name)
    benchmark_name = benchmark_for(category_text, scheme.scheme_name) or benchmark_for(sub_category, scheme.scheme_name) or ""
    benchmark_type = classify_benchmark(benchmark_name)
    fund_age_years = _fund_age_years(
        getattr(meta, "start_date", None) or first_nav_date,
        latest_nav_date or timezone.localdate(),
    )

    trailing_1y = latest_trailing.get("1Y")
    trailing_3y = latest_trailing.get("3Y")
    trailing_5y = latest_trailing.get("5Y")
    rolling_3y = latest_rolling.get("3Y")
    rolling_5y = latest_rolling.get("5Y")

    rolling_returns_json = {}
    for period in ("1Y", "3Y", "5Y"):
        row = latest_rolling.get(period)
        if row:
            rolling_returns_json[period] = {
                "avg": float(row.mean_pct) if row.mean_pct is not None else None,
                "max": float(row.max_pct) if row.max_pct is not None else None,
                "min": float(row.min_pct) if row.min_pct is not None else None,
                "pos_pct": float(row.win_rate_0) if row.win_rate_0 is not None else None,
            }

    risk_3y = latest_risk.get("3Y")
    risk_5y = latest_risk.get("5Y")

    volatility = _decimal(getattr(risk_3y, "std_dev_ann", None))
    if volatility is None:
        volatility = _decimal(getattr(meta, "volatility", None))

    sharpe = _decimal(getattr(risk_3y, "sharpe_ratio", None))
    sortino = _decimal(getattr(risk_3y, "sortino_ratio", None))
    drawdown = _decimal(getattr(risk_3y, "max_drawdown", None))

    volatility_5y = _decimal(getattr(risk_5y, "std_dev_ann", None))
    sharpe_5y = _decimal(getattr(risk_5y, "sharpe_ratio", None))
    sortino_5y = _decimal(getattr(risk_5y, "sortino_ratio", None))
    drawdown_5y = _decimal(getattr(risk_5y, "max_drawdown", None))

    excess_1y = _decimal(getattr(trailing_1y, "excess", None))
    excess_3y = _decimal(getattr(trailing_3y, "excess", None))

    analytics_dates = [
        getattr(row, "as_of", None)
        for row in [trailing_1y, trailing_3y, trailing_5y, rolling_3y, risk_3y, risk_5y]
        if row is not None
    ]
    data_as_of = max([d for d in [latest_nav_date, *analytics_dates] if d], default=timezone.localdate())

    snapshot, _ = FundScreenerSnapshot.objects.update_or_create(
        scheme=scheme,
        defaults={
            "fund_name": scheme.scheme_name,
            "fund_house": clean_fund_house(scheme.fund_house),
            "category_group": category_group,
            "scheme_sub_category": sub_category,
            "income_type": infer_income_type(scheme.scheme_name, scheme.plan),
            "plan_type": infer_plan_type(scheme.scheme_name, scheme.is_direct),
            "is_direct": scheme.is_direct,
            "is_etf": is_etf(scheme.scheme_name),
            "benchmark_type": benchmark_type,
            "benchmark_name": benchmark_name,
            "risk_label": risk_label(volatility),
            "aum_cr": _decimal(scheme.aum_cr or getattr(meta, "aum", None)),
            "expense_ratio": _decimal(scheme.expense_ratio or getattr(meta, "expense_ratio", None)),
            "fund_age_years": fund_age_years,
            "returns_1y_pct": _decimal(getattr(trailing_1y, "cagr_pct", None) or getattr(meta, "returns_1y", None)),
            "returns_3y_pct": _decimal(getattr(trailing_3y, "cagr_pct", None) or getattr(meta, "returns_3y", None)),
            "returns_5y_pct": _decimal(getattr(trailing_5y, "cagr_pct", None) or getattr(meta, "returns_5y", None)),
            "cagr_3y_pct": _decimal(getattr(trailing_3y, "cagr_pct", None) or getattr(meta, "returns_3y", None)),
            "rolling_return_3y_pct": _decimal(getattr(rolling_3y, "mean_pct", None)),
            "rolling_return_5y_pct": _decimal(getattr(rolling_5y, "mean_pct", None)),
            "volatility_3y_pct": volatility,
            "volatility_5y_pct": volatility_5y,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": drawdown,
            "sharpe_ratio_5y": sharpe_5y,
            "sortino_ratio_5y": sortino_5y,
            "max_drawdown_5y": drawdown_5y,
            "rolling_returns_json": rolling_returns_json,
            "calendar_returns_json": calendar_returns_json,
            "excess_return_1y": excess_1y,
            "excess_return_3y": excess_3y,
            # Short-period returns from captnemo SchemeMeta
            "returns_1w_pct": _decimal(getattr(meta, "returns_1w", None)),
            "returns_1m_pct": _decimal(getattr(meta, "returns_1m", None)),
            "returns_3m_pct": _decimal(getattr(meta, "returns_3m", None)),
            "returns_6m_pct": _decimal(
                # Try 6M trailing return first, fall back to None (captnemo doesn't provide 6M)
                getattr(
                    latest_trailing.get("6M"), "cagr_pct", None
                )
            ),
            "data_as_of": data_as_of,
            "nav_as_of": latest_nav_date,
            "analytics_as_of": max([d for d in analytics_dates if d], default=None),
            "metadata_as_of": getattr(meta, "last_fetched", None),
            "source_notes": "Scheme + SchemeMeta + latest analytics tables",
        },
    )
    return snapshot


def classify_scheme(category: str, scheme_name: str) -> tuple[str, str]:
    text = f"{category} {scheme_name}".lower()
    for label, patterns, group in SUB_CATEGORY_PATTERNS:
        if any(pattern in text for pattern in patterns):
            return group, label
    if "solution" in text:
        return "Solution Oriented", "Solution Oriented"
    for group in CATEGORY_GROUPS:
        if group.lower() in text:
            return group, _clean_sub_category(category, group) or group
    inferred = infer_category(scheme_name)
    if inferred:
        return classify_scheme(inferred, "")
    return "Other", _clean_sub_category(category, "Other") or "Other"


def classify_benchmark(benchmark_name: str) -> str:
    value = (benchmark_name or "").lower()
    if not value:
        return "Misc"
    if any(term in value for term in ("gold", "silver", "commodity", "commodities")):
        return "Commodity"
    if any(term in value for term in ("nasdaq", "s&p", "msci", "world", "global", "international")):
        return "International"
    if any(term in value for term in ("quality", "momentum", "value", "low volatility", "alpha", "equal weight")):
        return "Strategy based"
    if any(term in value for term in ("bank", "it", "auto", "pharma", "healthcare", "metal", "realty", "energy", "defence", "consumption", "manufacturing", "infra")):
        return "Sectoral"
    if any(term in value for term in ("thematic", "tourism", "digital", "internet", "ev", "new age")):
        return "Thematic"
    if any(term in value for term in ("nifty", "sensex", "bse", "crisil", "g-sec", "sdl", "liquid", "debt")):
        return "Broad based"
    return "Misc"


def benchmark_options() -> list[str]:
    return sorted({definition.name for definition in BENCHMARK_DEFINITIONS.values()})


def clean_fund_house(value: str) -> str:
    return re.sub(r"\s+Mutual\s+Fund\s*$", "", value or "", flags=re.I).strip()


def infer_plan_type(scheme_name: str, is_direct_scheme: bool) -> str:
    if is_etf(scheme_name):
        return "ETF"
    return "Direct" if is_direct_scheme else "Regular"


def infer_income_type(scheme_name: str, plan: str) -> str:
    name = (scheme_name or "").lower()
    if "income" in name:
        return "Income"
    if "idcw" in name or "dividend" in name or plan == "IDCW":
        return "IDCW"
    return "Growth"


def is_etf(scheme_name: str) -> bool:
    return bool(re.search(r"\betf\b|exchange traded", scheme_name or "", flags=re.I))


def risk_label(volatility: Decimal | None) -> str:
    if volatility is None:
        return ""
    if volatility < Decimal("8"):
        return "Low"
    if volatility < Decimal("15"):
        return "Moderate"
    if volatility < Decimal("25"):
        return "High"
    return "Very High"


def _latest_rows_by_key(rows, key: str) -> dict[str, object]:
    result = {}
    for row in rows:
        value = getattr(row, key)
        if value not in result:
            result[value] = row
    return result


def _category_text(scheme, meta) -> str:
    return (
        getattr(meta, "ms_category", "")
        or scheme.scheme_category
        or infer_category(scheme.scheme_name)
        or ""
    )


def _clean_sub_category(category: str, group: str) -> str:
    value = (category or "").strip()
    value = re.sub(r"\s+Scheme\s*$", "", value, flags=re.I)
    value = re.sub(rf"^{re.escape(group)}\s*[-:]\s*", "", value, flags=re.I)
    return value.strip()


def _fund_age_years(start: date | None, end: date | None) -> Decimal | None:
    if not start or not end or end <= start:
        return None
    return Decimal(str(round((end - start).days / 365.25, 1)))


def _decimal(value) -> Decimal | None:
    if value in ("", None):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ── Model score persistence ─────────────────────────────────────────────────────────────

def compute_and_save_model_score(scheme) -> None:
    """
    Run the full scorer (score_fund) using DB-only portfolio data (Option B).

    Portfolio data source: apps.holdings DB tables only — no mstarpy subprocess.
    Composition pillar will be UNRATED for funds with no local holdings data,
    but Performance (35%) + Risk (30%) + Cost (15%) = 80% weight always scored.

    Saves result to apps.funds.models.FundModelScore (one row per scheme).
    Safe to call concurrently — uses update_or_create.
    """
    from apps.funds.models import FundModelScore
    from apps.funds.runtime import get_portfolio_snapshot, fetch_db_trailing_returns, fetch_db_risk_metrics
    from apps.analytics.scorer import score_fund, MODEL_VERSION

    try:
        # Build a minimal snapshot using DB data only (no API calls)
        from types import SimpleNamespace
        from apps.analytics.models import TrailingReturn, RiskMetrics, RollingReturn

        # Trailing returns
        trailing_rows = fetch_db_trailing_returns(scheme)
        trailing_map = {r.period: r for r in trailing_rows}

        # Rolling returns
        rolling_rows = _latest_rows_by_key(
            RollingReturn.objects.filter(scheme=scheme).order_by("window", "-as_of"),
            "window",
        )

        # Risk metrics
        risk_dict = fetch_db_risk_metrics(scheme)
        risk_3y = risk_dict.get("3Y")
        risk_5y = risk_dict.get("5Y")

        # Portfolio from DB only (Holding + SectorAllocation tables)
        from apps.funds.runtime import fetch_db_portfolio
        portfolio = fetch_db_portfolio(scheme)
        raw_holdings = portfolio.get("holdings", [])
        raw_sectors  = portfolio.get("sectors", [])

        # Build a NAV series stub (just count for nav_days)
        from apps.funds.models import NAVHistory
        nav_count = NAVHistory.objects.filter(scheme=scheme).count()
        import pandas as pd
        nav_series = pd.Series(range(nav_count), dtype=float) if nav_count else pd.Series(dtype=float)

        meta = getattr(scheme, 'meta', None)
        benchmark_name = getattr(scheme, 'scheme_category', '')

        # Top10 weight from DB holdings
        top10_weight = round(
            sum(getattr(h, "weight_pct", 0) or 0 for h in raw_holdings[:10]), 2
        ) or None
        if top10_weight and top10_weight > 100:
            top10_weight = None

        db_snapshot = SimpleNamespace(
            scheme=scheme,
            nav_series=nav_series,
            trailing_returns=trailing_rows,
            trailing_map=trailing_map,
            rolling_returns=rolling_rows,
            risk_3y=risk_3y,
            risk_5y=risk_5y,
            meta=meta or SimpleNamespace(
                expense_ratio=getattr(scheme, 'expense_ratio', None),
                aum=getattr(scheme, 'aum_cr', None),
            ),
            top_holdings=raw_holdings,
            sector_alloc=raw_sectors,
            top10_weight=top10_weight,
            total_holdings_count=len(raw_holdings),
            benchmark_name=benchmark_name,
        )

        result = score_fund(db_snapshot)

        badge = getattr(result.overall_badge, 'get', lambda k, v: v)('label', '') \
            if isinstance(result.overall_badge, dict) else str(result.overall_badge)

        FundModelScore.objects.update_or_create(
            scheme=scheme,
            defaults={
                'score_version':      MODEL_VERSION,
                'final_score':        _decimal(result.final_score),
                'confidence':         result.confidence or '',
                'score_badge':        result.overall_badge.get('label', '') if isinstance(result.overall_badge, dict) else '',
                'score_performance':  _decimal(result.performance.get('score')),
                'score_risk':         _decimal(result.risk.get('score')),
                'score_cost':         _decimal(result.cost.get('score')),
                'score_composition':  _decimal(result.composition.get('score')),
                'score_manager':      _decimal(result.manager.get('score')) if hasattr(result, 'manager') and result.manager else None,
                'score_debt':         _decimal(result.debt.get('score')) if hasattr(result, 'debt') and result.debt else None,
                'perf_status':        result.performance.get('status', ''),
                'risk_status':        result.risk.get('status', ''),
                'cost_status':        result.cost.get('status', ''),
                'comp_status':        result.composition.get('status', ''),
                'manager_status':     result.manager.get('status', '') if hasattr(result, 'manager') and result.manager else '',
                'debt_status':        result.debt.get('status', '') if hasattr(result, 'debt') and result.debt else '',
                'red_flags_json':     result.red_flags.get('flags', []),
                'red_flag_penalty':   _decimal(result.red_flags.get('total_penalty')),
                'overall_interpretation': result.overall_interpretation or '',
                'nav_days':           result.nav_days,
            },
        )
    except Exception as exc:
        logger.warning("[%s] model score compute failed: %s", scheme.amfi_code, exc)


# ── Quartile rank computation ────────────────────────────────────────────────────────────

def compute_quartile_ranks_for_category(sub_category: str) -> int:
    """
    Compute Q1-Q4 quartile ranks + numeric ranks for all funds in a sub-category.
    Updates FundScreenerSnapshot rows in bulk.

    Metrics ranked (higher = better, except volatility where lower = better):
      - returns_1y_pct, returns_3y_pct, returns_5y_pct   (higher = better → Q1)
      - volatility_3y_pct                                  (lower = better → Q1)
      - sharpe_ratio, sortino_ratio                        (higher = better → Q1)
      - model score from FundModelScore                    (higher = better → Q1)

    Returns the number of funds ranked.
    """
    import numpy as np
    from apps.funds.models import FundScreenerSnapshot, FundModelScore

    snapshots = list(
        FundScreenerSnapshot.objects.filter(
            scheme_sub_category=sub_category,
            is_direct=True,
        ).select_related('scheme').only(
            'id', 'scheme_id',
            'returns_1y_pct', 'returns_3y_pct', 'returns_5y_pct',
            'volatility_3y_pct', 'sharpe_ratio', 'sortino_ratio',
        )
    )
    if not snapshots:
        return 0

    n = len(snapshots)

    # Fetch model scores as a dict: scheme_id -> final_score
    scheme_ids = [s.scheme_id for s in snapshots]
    score_map = dict(
        FundModelScore.objects.filter(scheme_id__in=scheme_ids)
        .values_list('scheme_id', 'final_score')
    )

    def _float_or_nan(val):
        if val is None:
            return float('nan')
        try:
            f = float(val)
            return f if math.isfinite(f) else float('nan')
        except (TypeError, ValueError):
            return float('nan')

    def _rank_and_quartile(values: list[float], higher_is_better: bool = True):
        """
        Return (rank_list, quartile_list) where ranks start at 1.
        NaN values get rank=None, quartile=None.
        """
        indexed = [(v, i) for i, v in enumerate(values)]
        valid = [(v, i) for v, i in indexed if not math.isnan(v)]
        if not valid:
            return [None] * len(values), [None] * len(values)

        # Sort: descending for higher-is-better, ascending for lower-is-better
        valid_sorted = sorted(valid, key=lambda x: x[0], reverse=higher_is_better)
        rank_map = {}  # original_index -> rank
        for rank_pos, (_, orig_idx) in enumerate(valid_sorted, start=1):
            rank_map[orig_idx] = rank_pos

        total_valid = len(valid)
        ranks = []
        quartiles = []
        for i, v in enumerate(values):
            if math.isnan(v):
                ranks.append(None)
                quartiles.append(None)
            else:
                r = rank_map[i]
                ranks.append(r)
                # Quartile: divide ranked valid funds into 4 equal groups
                q = min(4, math.ceil(r / total_valid * 4)) if total_valid > 0 else None
                quartiles.append(q)
        return ranks, quartiles

    # Extract metric arrays
    ret1y  = [_float_or_nan(s.returns_1y_pct)  for s in snapshots]
    ret3y  = [_float_or_nan(s.returns_3y_pct)  for s in snapshots]
    ret5y  = [_float_or_nan(s.returns_5y_pct)  for s in snapshots]
    vol    = [_float_or_nan(s.volatility_3y_pct) for s in snapshots]
    sharpe = [_float_or_nan(s.sharpe_ratio)     for s in snapshots]
    sortino= [_float_or_nan(s.sortino_ratio)    for s in snapshots]
    scores = [_float_or_nan(score_map.get(s.scheme_id)) for s in snapshots]

    ranks_1y,  q_1y  = _rank_and_quartile(ret1y,   higher_is_better=True)
    ranks_3y,  q_3y  = _rank_and_quartile(ret3y,   higher_is_better=True)
    ranks_5y,  q_5y  = _rank_and_quartile(ret5y,   higher_is_better=True)
    _,         q_vol  = _rank_and_quartile(vol,    higher_is_better=False)
    _,         q_shr  = _rank_and_quartile(sharpe, higher_is_better=True)
    _,         q_srt  = _rank_and_quartile(sortino,higher_is_better=True)
    _,         q_scr  = _rank_and_quartile(scores, higher_is_better=True)

    # Bulk-update all snapshots
    to_update = []
    for i, snap in enumerate(snapshots):
        snap.quartile_return_1y   = q_1y[i]
        snap.quartile_return_3y   = q_3y[i]
        snap.quartile_return_5y   = q_5y[i]
        snap.quartile_volatility  = q_vol[i]
        snap.quartile_sharpe      = q_shr[i]
        snap.quartile_sortino     = q_srt[i]
        snap.quartile_model_score = q_scr[i]
        snap.rank_return_1y       = ranks_1y[i]
        snap.rank_return_3y       = ranks_3y[i]
        snap.rank_return_5y       = ranks_5y[i]
        snap.rank_count_in_cat    = n
        to_update.append(snap)

    FundScreenerSnapshot.objects.bulk_update(
        to_update,
        fields=[
            'quartile_return_1y', 'quartile_return_3y', 'quartile_return_5y',
            'quartile_volatility', 'quartile_sharpe', 'quartile_sortino',
            'quartile_model_score',
            'rank_return_1y', 'rank_return_3y', 'rank_return_5y',
            'rank_count_in_cat',
        ],
        batch_size=200,
    )
    return n
