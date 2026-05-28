"""
apps/analytics/scorer.py — Fund Scoring Engine (v1)
====================================================
Category-normalized, multi-factor mutual fund scoring.

Model overview: see docs/SCORING_MODEL.md

Design:
  - Pure Python — no Django ORM calls; takes a runtime snapshot as input
  - Returns a typed ScorecardResult SimpleNamespace
  - Handles all fallbacks gracefully; uses PROVISIONAL/UNRATED states for
    pillars where data is insufficient rather than fabricating scores
  - All weights, thresholds, and normalization constants are documented inline
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

MODEL_VERSION = "1.0"

# Pillar weights — must sum to 1.0
WEIGHTS = {
    "performance":  0.30,
    "risk":         0.28,
    "cost":         0.12,
    "composition":  0.15,
    # Red flag is a penalty layer subtracted from the composite, not a pillar weight
}

# Maximum penalty from red flags (points)
MAX_RED_FLAG_PENALTY = 15

# Minimum data requirement (trading days) for Rated status
MIN_RATED_NAV_DAYS = 756   # ~3 years
MIN_PROVISIONAL_NAV_DAYS = 252  # ~1 year

# Expense ratio thresholds by category type: (excellent, good, average, poor)
ER_THRESHOLDS = {
    "equity_direct":   (0.30, 0.60, 1.00, 1.50),
    "equity_regular":  (0.80, 1.20, 1.75, 2.25),
    "index_direct":    (0.05, 0.15, 0.30, 0.50),
    "index_regular":   (0.10, 0.25, 0.50, 0.80),
    "debt_direct":     (0.20, 0.40, 0.70, 1.00),
    "debt_regular":    (0.50, 0.80, 1.20, 1.50),
    "hybrid_direct":   (0.40, 0.70, 1.10, 1.60),
    "hybrid_regular":  (0.70, 1.00, 1.50, 2.00),
    "default":         (0.50, 1.00, 1.50, 2.00),
}

# ── Pillar status tokens ───────────────────────────────────────────────────────
STATUS_RATED       = "RATED"
STATUS_PROVISIONAL = "PROVISIONAL"
STATUS_UNRATED     = "UNRATED"

# ── Score badge thresholds ─────────────────────────────────────────────────────
def score_badge(score: Optional[float]) -> dict:
    """Return badge label, colour and emoji for a numeric score."""
    if score is None:
        return {"label": "N/A", "color": "gray", "emoji": "⚪"}
    if score >= 75:
        return {"label": "Strong",     "color": "green",  "emoji": "🟢"}
    if score >= 55:
        return {"label": "Good",       "color": "blue",   "emoji": "🔵"}
    if score >= 40:
        return {"label": "Fair",       "color": "yellow", "emoji": "🟡"}
    if score >= 25:
        return {"label": "Weak",       "color": "orange", "emoji": "🟠"}
    return     {"label": "Poor",       "color": "red",    "emoji": "🔴"}


# ── Normalizer ────────────────────────────────────────────────────────────────

def _norm(value: Optional[float], low: float, high: float) -> float:
    """Linearly normalize value to [0, 100]. Clamps output."""
    if value is None or not math.isfinite(value):
        return 0.0
    if high == low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _safe(value) -> Optional[float]:
    """Return float or None, handling Decimal and None."""
    if value is None:
        return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── Category type resolver ────────────────────────────────────────────────────

def _er_category(category: str, is_direct: bool) -> str:
    """Map SEBI category string → expense ratio threshold key."""
    cat = category.lower()
    direct_suffix = "direct" if is_direct else "regular"

    if any(k in cat for k in ("index", "etf", "nifty 50", "sensex", "tracker")):
        return f"index_{direct_suffix}"
    if any(k in cat for k in ("debt", "liquid", "overnight", "short duration",
                               "medium duration", "long duration", "gilt",
                               "credit risk", "banking and psu", "money market",
                               "dynamic bond", "corporate bond", "floater")):
        return f"debt_{direct_suffix}"
    if any(k in cat for k in ("hybrid", "balanced", "aggressive", "conservative",
                               "equity savings", "arbitrage", "multi asset")):
        return f"hybrid_{direct_suffix}"
    if any(k in cat for k in ("equity", "large cap", "mid cap", "small cap",
                               "multi cap", "flexi cap", "elss", "focussed",
                               "thematic", "sectoral")):
        return f"equity_{direct_suffix}"
    return "default"


# ── Portfolio weight normalizer ───────────────────────────────────────────────

def normalize_holding_weights(holdings: list) -> list:
    """
    Detect and correct common weight-unit bugs in holdings data.

    Some data sources return weights:
      - As fractions (0.0843 → should be 8.43%)  — handled by finapi_holdings
      - As percentages already (8.43%)             — correct
      - Occasionally double-multiplied (843%)      — bug we fix here

    Strategy: if sum of all weights >> 100, divide all by 100.
    If sum < 2, multiply all by 100.
    """
    if not holdings:
        return holdings

    total = sum(getattr(h, "weight_pct", 0) or 0 for h in holdings)
    if total <= 0:
        return holdings

    # If sum is wildly over 100 (>150), the weights are in the wrong unit
    if total > 150:
        factor = 100.0 / total
        for h in holdings:
            if hasattr(h, "weight_pct") and h.weight_pct is not None:
                object.__setattr__(h, "weight_pct", round(h.weight_pct * factor, 4)) if hasattr(h, '__dict__') else None
                try:
                    h.weight_pct = round(h.weight_pct * factor, 4)
                except AttributeError:
                    pass
    # If sum < 2, weights are in decimal fraction
    elif total < 2:
        for h in holdings:
            if hasattr(h, "weight_pct") and h.weight_pct is not None:
                try:
                    h.weight_pct = round(h.weight_pct * 100.0, 4)
                except AttributeError:
                    pass

    return holdings


# ── Performance Pillar ────────────────────────────────────────────────────────

def _score_performance(trailing_map: dict, rolling_returns: dict, risk_3y, risk_5y,
                       nav_days: int) -> dict:
    """
    Score performance pillar (0–100).
    Returns dict with score, status, details, interpretation.
    """
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    # ── 3Y CAGR (40%) ────────────────────────────────────────────
    cagr_3y = _safe(getattr(trailing_map.get("3Y"), "cagr_pct", None))
    if cagr_3y is not None:
        s = _norm(cagr_3y, 0, 20)
        details["cagr_3y"] = {"value": cagr_3y, "score": round(s, 1), "label": "3Y CAGR"}
        weighted_sum += s * 0.40
        available_weights += 0.40
    else:
        details["cagr_3y"] = {"value": None, "score": None, "label": "3Y CAGR"}

    # ── 1Y CAGR (20%) ────────────────────────────────────────────
    cagr_1y = _safe(getattr(trailing_map.get("1Y"), "cagr_pct", None))
    if cagr_1y is not None:
        s = _norm(cagr_1y, -5, 30)
        details["cagr_1y"] = {"value": cagr_1y, "score": round(s, 1), "label": "1Y CAGR"}
        weighted_sum += s * 0.20
        available_weights += 0.20
    else:
        details["cagr_1y"] = {"value": None, "score": None, "label": "1Y CAGR"}

    # ── 5Y CAGR (20%) ────────────────────────────────────────────
    cagr_5y = _safe(getattr(trailing_map.get("5Y"), "cagr_pct", None))
    if cagr_5y is not None:
        s = _norm(cagr_5y, 0, 18)
        details["cagr_5y"] = {"value": cagr_5y, "score": round(s, 1), "label": "5Y CAGR"}
        weighted_sum += s * 0.20
        available_weights += 0.20
    else:
        details["cagr_5y"] = {"value": None, "score": None, "label": "5Y CAGR"}

    # ── Rolling Win Rate >0% — 3Y window (10%) ───────────────────
    rolling_3y = rolling_returns.get("3Y") or rolling_returns.get("1Y")
    win_rate = _safe(getattr(rolling_3y, "win_rate_0", None))
    if win_rate is not None:
        s = min(100.0, win_rate)
        details["win_rate"] = {"value": win_rate, "score": round(s, 1), "label": "Rolling Win Rate (>0%)"}
        weighted_sum += s * 0.10
        available_weights += 0.10
    else:
        details["win_rate"] = {"value": None, "score": None, "label": "Rolling Win Rate (>0%)"}

    # ── Excess return vs benchmark (10%) ─────────────────────────
    excess_3y = _safe(getattr(trailing_map.get("3Y"), "excess", None))
    if excess_3y is not None:
        s = _norm(excess_3y, -5, 8)
        details["excess_3y"] = {"value": excess_3y, "score": round(s, 1), "label": "3Y Excess vs Benchmark"}
        weighted_sum += s * 0.10
        available_weights += 0.10
    else:
        details["excess_3y"] = {"value": None, "score": None, "label": "3Y Excess vs Benchmark"}

    # ── Compute final ─────────────────────────────────────────────
    if available_weights < 0.20:   # Need at least 20% of sub-metrics
        return {"score": None, "status": STATUS_UNRATED, "details": details,
                "missing": "Insufficient trailing return data (need at least 1Y CAGR)"}

    # Rescale to full weight range
    raw_score = weighted_sum / available_weights * 100  # normalize missing sub-metrics
    score = round(max(0, min(100, weighted_sum / available_weights * 100)), 1)

    status = STATUS_RATED if available_weights >= 0.80 else STATUS_PROVISIONAL
    missing_note = None if available_weights >= 0.80 else "Some return periods unavailable; score is provisional"

    interp = _interpret_performance(score, cagr_3y, cagr_1y, cagr_5y, excess_3y, win_rate)
    return {"score": score, "status": status, "details": details,
            "missing": missing_note, "interpretation": interp}


def _interpret_performance(score, cagr_3y, cagr_1y, cagr_5y, excess, win_rate):
    parts = []
    if cagr_3y is not None:
        q = "strong" if cagr_3y > 14 else "moderate" if cagr_3y > 8 else "weak"
        parts.append(f"3-year CAGR of {cagr_3y:.1f}% is {q}.")
    if cagr_5y is not None:
        q = "strong" if cagr_5y > 12 else "moderate" if cagr_5y > 7 else "weak"
        parts.append(f"5-year CAGR of {cagr_5y:.1f}% is {q}.")
    if excess is not None:
        tag = "outperformed" if excess > 0 else "underperformed"
        parts.append(f"Fund has {tag} its benchmark by {abs(excess):.1f}% over 3 years.")
    if win_rate is not None:
        parts.append(f"Positive rolling return {win_rate:.0f}% of the time (3Y window).")
    return " ".join(parts) or "Insufficient data to interpret performance."


# ── Risk / Stability Pillar ───────────────────────────────────────────────────

def _score_risk(risk_3y, risk_5y) -> dict:
    """Score risk pillar (0–100)."""
    # Prefer 3Y, fallback to 5Y
    rm = risk_3y or risk_5y
    period_label = "3Y" if risk_3y else ("5Y" if risk_5y else None)
    details = {}

    if rm is None:
        return {"score": None, "status": STATUS_PROVISIONAL,
                "details": details, "missing": "No risk metrics available (need 3Y+ NAV history)",
                "interpretation": "Risk metrics require at least 3 years of NAV data."}

    available_weights = 0.0
    weighted_sum = 0.0

    # ── Sortino (30%) ─────────────────────────────────────────────
    sortino = _safe(rm.sortino_ratio)
    if sortino is not None:
        s = _norm(sortino, 0, 2.5)
        details["sortino"] = {"value": sortino, "score": round(s, 1), "label": f"Sortino Ratio ({period_label})"}
        weighted_sum += s * 0.30
        available_weights += 0.30
    else:
        details["sortino"] = {"value": None, "score": None, "label": f"Sortino Ratio ({period_label})"}

    # ── Max Drawdown (30%) ────────────────────────────────────────
    max_dd = _safe(rm.max_drawdown)
    if max_dd is not None:
        # max_dd is negative (e.g. −30%). Lower absolute value = better.
        s = _norm(max_dd, -50, -5)   # −5% (mild) = 100, −50% (severe) = 0
        details["max_drawdown"] = {"value": max_dd, "score": round(s, 1), "label": f"Max Drawdown ({period_label})"}
        weighted_sum += s * 0.30
        available_weights += 0.30
    else:
        details["max_drawdown"] = {"value": None, "score": None, "label": f"Max Drawdown ({period_label})"}

    # ── Downside Capture (25%) ────────────────────────────────────
    dn_cap = _safe(rm.downside_capture)
    if dn_cap is not None:
        # lower downside capture = better; 80 = fund fell 80% as much as BM
        s = _norm(100 - dn_cap, -30, 30)  # 70 capture (30 less than BM) = 100
        details["downside_capture"] = {"value": dn_cap, "score": round(s, 1), "label": f"Downside Capture ({period_label})"}
        weighted_sum += s * 0.25
        available_weights += 0.25
    else:
        details["downside_capture"] = {"value": None, "score": None, "label": f"Downside Capture ({period_label})"}

    # ── Sharpe (15%) ──────────────────────────────────────────────
    sharpe = _safe(rm.sharpe_ratio)
    if sharpe is not None:
        s = _norm(sharpe, 0, 2.0)
        details["sharpe"] = {"value": sharpe, "score": round(s, 1), "label": f"Sharpe Ratio ({period_label})"}
        weighted_sum += s * 0.15
        available_weights += 0.15
    else:
        details["sharpe"] = {"value": None, "score": None, "label": f"Sharpe Ratio ({period_label})"}

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL,
                "details": details, "missing": "Insufficient risk metrics; need at least Sortino or Max Drawdown",
                "interpretation": "Risk scoring requires at least one of: Sortino Ratio, Max Drawdown."}

    score = round(max(0, min(100, weighted_sum / available_weights * 100)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    missing_note = None if available_weights >= 0.70 else f"Some risk metrics unavailable ({period_label} data used)"

    interp = _interpret_risk(score, max_dd, sortino, dn_cap, sharpe, period_label)
    return {"score": score, "status": status, "details": details,
            "missing": missing_note, "interpretation": interp}


def _interpret_risk(score, max_dd, sortino, dn_cap, sharpe, period):
    parts = []
    if max_dd is not None:
        severity = "mild" if max_dd > -15 else "moderate" if max_dd > -30 else "severe"
        parts.append(f"Maximum drawdown of {max_dd:.1f}% ({period}) is {severity}.")
    if sortino is not None:
        q = "excellent" if sortino > 2 else "good" if sortino > 1 else "below average"
        parts.append(f"Sortino ratio of {sortino:.2f} is {q} (higher = better downside control).")
    if dn_cap is not None:
        q = "excellent" if dn_cap < 80 else "good" if dn_cap < 95 else "poor"
        parts.append(f"Downside capture of {dn_cap:.1f}% is {q} (lower = less market-fall exposure).")
    return " ".join(parts) or "Risk metrics not available."


# ── Cost Pillar ────────────────────────────────────────────────────────────────

def _score_cost(expense_ratio: Optional[float], aum: Optional[float],
                category: str, is_direct: bool) -> dict:
    """Score cost pillar (0–100)."""
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    er_cat = _er_category(category, is_direct)
    thresholds = ER_THRESHOLDS.get(er_cat, ER_THRESHOLDS["default"])
    excellent, good, avg, poor = thresholds

    # ── Expense ratio (70%) ───────────────────────────────────────
    er = _safe(expense_ratio)
    if er is not None and er > 0:
        # normalize: excellent ER → 100, poor ER → 0
        s = _norm(-er, -poor, -excellent)   # invert (lower ER = higher score)
        details["expense_ratio"] = {
            "value": er, "score": round(s, 1), "label": "Expense Ratio",
            "benchmark": f"Category norm: {excellent}–{avg}%",
        }
        weighted_sum += s * 0.70
        available_weights += 0.70
    else:
        details["expense_ratio"] = {"value": None, "score": None, "label": "Expense Ratio",
                                    "benchmark": f"Category norm: {excellent}–{avg}%"}

    # ── AUM size factor (30%) ─────────────────────────────────────
    aum_val = _safe(aum)
    if aum_val is not None and aum_val > 0:
        s = _norm(aum_val, 100, 5000)
        details["aum"] = {"value": aum_val, "score": round(s, 1), "label": "AUM (₹ Cr)"}
        weighted_sum += s * 0.30
        available_weights += 0.30
    else:
        details["aum"] = {"value": None, "score": None, "label": "AUM (₹ Cr)"}

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL,
                "details": details, "missing": "Expense ratio not available",
                "interpretation": "Cost data not available from current data sources for this fund."}

    score = round(max(0, min(100, weighted_sum / available_weights * 100)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    missing_note = None if available_weights >= 0.70 else "AUM or expense ratio data partially unavailable"

    interp = _interpret_cost(score, er, aum_val, excellent, avg, poor, er_cat)
    return {"score": score, "status": status, "details": details,
            "missing": missing_note, "interpretation": interp}


def _interpret_cost(score, er, aum, excellent, avg, poor, er_cat):
    parts = []
    if er is not None:
        if er <= excellent:
            parts.append(f"Expense ratio of {er:.2f}% is excellent for this category.")
        elif er <= avg:
            parts.append(f"Expense ratio of {er:.2f}% is within acceptable range for this category.")
        else:
            parts.append(f"Expense ratio of {er:.2f}% is high; this is a significant drag on returns.")
    if aum is not None:
        if aum >= 5000:
            parts.append(f"AUM of ₹{aum:,.0f} Cr is large, suggesting good investor confidence and scale.")
        elif aum < 100:
            parts.append(f"AUM of ₹{aum:,.0f} Cr is very small; may have liquidity and scale concerns.")
        else:
            parts.append(f"AUM of ₹{aum:,.0f} Cr is adequate.")
    return " ".join(parts) or "Cost data not available."


# ── Composition Pillar ────────────────────────────────────────────────────────

def _score_composition(top_holdings: list, sector_alloc: list,
                       total_count: int, top10_weight: Optional[float]) -> dict:
    """Score composition/portfolio construction pillar (0–100)."""
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    if not top_holdings and not sector_alloc:
        return {"score": None, "status": STATUS_UNRATED,
                "details": details, "missing": "No holdings data available from any source",
                "interpretation": "Portfolio composition cannot be assessed — holdings data is not available."}

    # ── Top-10 concentration (40%) ────────────────────────────────
    t10w = _safe(top10_weight)
    if t10w is not None and t10w <= 100:
        s = _norm(100 - t10w, 10, 60)   # 60% free of top-10 = perfect
        details["top10_weight"] = {"value": t10w, "score": round(s, 1), "label": "Top-10 Concentration (%)"}
        weighted_sum += s * 0.40
        available_weights += 0.40
    else:
        details["top10_weight"] = {"value": top10_weight, "score": None, "label": "Top-10 Concentration (%)"}

    # ── Holdings count (30%) ──────────────────────────────────────
    if total_count is not None and total_count > 0:
        s = _norm(total_count, 5, 50)
        details["holdings_count"] = {"value": total_count, "score": round(s, 1), "label": "Total Holdings"}
        weighted_sum += s * 0.30
        available_weights += 0.30
    else:
        details["holdings_count"] = {"value": total_count, "score": None, "label": "Total Holdings"}

    # ── Sector HHI (30%) ──────────────────────────────────────────
    if sector_alloc:
        weights = [getattr(s, "weight_pct", 0) or 0 for s in sector_alloc]
        total_w = sum(weights)
        if total_w > 0:
            fracs = [w / total_w for w in weights]
            hhi = sum(f * f for f in fracs)   # 0=perfect, 1=monopoly
            s = _norm(1 - hhi, 0.5, 1.0)     # 1 - HHI: higher = more diverse
            details["sector_hhi"] = {"value": round(hhi, 3), "score": round(s, 1), "label": "Sector Diversification (HHI)"}
            weighted_sum += s * 0.30
            available_weights += 0.30
        else:
            details["sector_hhi"] = {"value": None, "score": None, "label": "Sector Diversification (HHI)"}
    else:
        details["sector_hhi"] = {"value": None, "score": None, "label": "Sector Diversification (HHI)"}

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL,
                "details": details, "missing": "Insufficient portfolio data for composition scoring",
                "interpretation": "Holdings data is incomplete; composition score is provisional."}

    score = round(max(0, min(100, weighted_sum / available_weights * 100)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    missing_note = None if available_weights >= 0.70 else "Partial portfolio data; score is provisional"

    interp = _interpret_composition(score, t10w, total_count, details.get("sector_hhi", {}).get("value"))
    return {"score": score, "status": status, "details": details,
            "missing": missing_note, "interpretation": interp}


def _interpret_composition(score, t10w, count, hhi):
    parts = []
    if t10w is not None:
        q = "well-distributed" if t10w < 50 else "moderately concentrated" if t10w < 70 else "highly concentrated"
        parts.append(f"Top-10 holdings account for {t10w:.1f}% of the portfolio — {q}.")
    if count:
        q = "broad" if count > 50 else "focused" if count > 20 else "highly focused"
        parts.append(f"Portfolio holds {count} securities, a {q} portfolio.")
    if hhi is not None:
        q = "well-diversified" if hhi < 0.15 else "moderately concentrated" if hhi < 0.30 else "sector-concentrated"
        parts.append(f"Sector allocation is {q} (HHI={hhi:.2f}).")
    return " ".join(parts) or "Portfolio composition data unavailable."


# ── Red Flags ─────────────────────────────────────────────────────────────────

def _compute_red_flags(snapshot, nav_days: int, expense_ratio, aum,
                       top_holdings, r_squared) -> dict:
    """Compute red flag penalties. Returns dict with flags list and total penalty."""
    flags = []
    total_penalty = 0

    def add_flag(code, label, severity, penalty, note):
        nonlocal total_penalty
        total_penalty += penalty
        flags.append({
            "code": code, "label": label, "severity": severity,
            "penalty": penalty, "note": note,
        })

    # Insufficient NAV history
    if nav_days < MIN_PROVISIONAL_NAV_DAYS:
        add_flag("short_history", "Insufficient NAV History", "critical", 8,
                 f"Only {nav_days} trading days of NAV data. Scores are unreliable with less than 1 year of history.")

    # Missing benchmark
    bm_name = getattr(snapshot, "benchmark_name", None)
    if not bm_name:
        add_flag("no_benchmark", "No Benchmark Mapped", "warning", 3,
                 "No benchmark index is mapped for this category. Relative performance cannot be measured.")

    # Very high expense ratio
    er = _safe(expense_ratio)
    if er and er > 2.5:
        add_flag("high_er_equity", "Very High Expense Ratio (>2.5%)", "warning", 5,
                 f"Expense ratio of {er:.2f}% significantly erodes long-term returns.")
    elif er and er > 1.5:
        add_flag("moderate_er", "High Expense Ratio (>1.5%)", "info", 2,
                 f"Expense ratio of {er:.2f}% is above average. Consider Direct plan alternatives.")

    # Very low AUM
    aum_val = _safe(aum)
    if aum_val is not None and 0 < aum_val < 100:
        add_flag("low_aum", "Very Low AUM (<₹100 Cr)", "warning", 3,
                 f"AUM of ₹{aum_val:.0f} Cr is very small. Risk of scheme closure or liquidity concerns.")

    # Extreme concentration
    if top_holdings:
        max_weight = max((getattr(h, "weight_pct", 0) or 0) for h in top_holdings)
        if max_weight > 50:
            add_flag("extreme_concentration", f"Extreme Single-Stock Concentration ({max_weight:.1f}%)",
                     "critical", 5,
                     f"A single holding represents {max_weight:.1f}% of the portfolio — this is extremely concentrated.")

    # No holdings data
    if not top_holdings:
        add_flag("no_holdings", "Holdings Data Unavailable", "info", 2,
                 "Portfolio composition cannot be verified due to unavailable holdings data.")

    # Benchmark mismatch (low R²)
    r_sq = _safe(r_squared)
    if r_sq is not None and r_sq < 50 and bm_name:
        add_flag("bm_mismatch", "Benchmark Mismatch (Low R²)", "warning", 3,
                 f"R² of {r_sq:.1f}% vs benchmark suggests the mapped benchmark may not be the right peer group for this fund.")

    total_penalty = min(total_penalty, MAX_RED_FLAG_PENALTY)
    return {"flags": flags, "total_penalty": total_penalty}


# ── Overall Confidence ────────────────────────────────────────────────────────

def _overall_confidence(nav_days: int, perf_status: str, risk_status: str,
                         cost_status: str, comp_status: str) -> str:
    if nav_days < MIN_PROVISIONAL_NAV_DAYS:
        return STATUS_UNRATED
    unrated = sum(1 for s in [perf_status, risk_status] if s == STATUS_UNRATED)
    if unrated >= 2:
        return STATUS_UNRATED
    provisional = sum(1 for s in [perf_status, risk_status, cost_status, comp_status]
                      if s in (STATUS_PROVISIONAL, STATUS_UNRATED))
    if provisional >= 3 or nav_days < MIN_RATED_NAV_DAYS:
        return STATUS_PROVISIONAL
    return STATUS_RATED


# ── Category Rank ─────────────────────────────────────────────────────────────

def compute_category_rank(scheme, final_score: Optional[float]) -> dict:
    """
    Score all peers in the same scheme_category and compute rank.
    DB-aware: called separately so the pure scorer stays dependency-free.
    Returns dict with rank, total, percentile.
    """
    if final_score is None:
        return {"rank": None, "total": None, "percentile": None}

    try:
        from apps.funds.models import Scheme
        from apps.analytics.models import TrailingReturn, RiskMetrics
        from django.core.cache import cache

        cache_key = f"category_scores:v1:{scheme.scheme_category}"
        peer_scores = cache.get(cache_key)

        if peer_scores is None:
            peers = Scheme.objects.filter(
                scheme_category=scheme.scheme_category,
                is_active=True,
                plan="GROWTH",
                is_direct=scheme.is_direct,
            ).exclude(pk=scheme.pk).values("pk", "amfi_code", "expense_ratio", "aum_cr")[:100]

            peer_scores = {}
            for peer in peers:
                try:
                    tr = (TrailingReturn.objects
                          .filter(scheme_id=peer["pk"], period="3Y")
                          .order_by("-as_of")
                          .values("cagr_pct", "excess")
                          .first())
                    rm = (RiskMetrics.objects
                          .filter(scheme_id=peer["pk"], period="3Y")
                          .order_by("-as_of")
                          .values("max_drawdown", "sortino_ratio", "sharpe_ratio", "downside_capture")
                          .first())
                    if not tr:
                        continue
                    # Simplified peer score using available pre-computed metrics
                    p_score = 0.0
                    p_score += _norm(_safe(tr.get("cagr_pct")), 0, 20) * 0.35
                    p_score += _norm(_safe(tr.get("excess")), -5, 8) * 0.10
                    if rm:
                        p_score += _norm(_safe(rm.get("max_drawdown")), -50, -5) * 0.25
                        p_score += _norm(_safe(rm.get("sortino_ratio")), 0, 2.5) * 0.20
                        p_score += _norm(_safe(rm.get("sharpe_ratio")), 0, 2.0) * 0.10
                    er = _safe(peer.get("expense_ratio"))
                    if er:
                        p_score -= _norm(er, 0, 3) * 0.05  # small cost penalty
                    peer_scores[peer["amfi_code"]] = round(p_score, 2)
                except Exception:
                    continue

            cache.set(cache_key, peer_scores, 60 * 60 * 6)  # 6 hours

        all_scores = list(peer_scores.values()) + [final_score]
        all_scores_sorted = sorted(all_scores, reverse=True)
        rank = all_scores_sorted.index(final_score) + 1
        total = len(all_scores)
        percentile = round((1 - (rank - 1) / total) * 100, 1)
        return {"rank": rank, "total": total, "percentile": percentile}

    except Exception:
        return {"rank": None, "total": None, "percentile": None}


# ── Main Scorer ────────────────────────────────────────────────────────────────

def score_fund(snapshot) -> SimpleNamespace:
    """
    Score a fund from its runtime snapshot.

    Args:
        snapshot: SimpleNamespace from apps.funds.runtime.get_runtime_snapshot()

    Returns:
        SimpleNamespace with all score fields, interpretations, flags, metadata.
    """
    # ── Extract raw inputs ─────────────────────────────────────────
    scheme      = snapshot.scheme
    nav_series  = getattr(snapshot, "nav_series", None)
    nav_days    = len(nav_series) if nav_series is not None and not nav_series.empty else 0

    trailing_map   = getattr(snapshot, "trailing_map", {})
    rolling_returns = getattr(snapshot, "rolling_returns", {})
    risk_3y        = getattr(snapshot, "risk_3y", None)
    risk_5y        = getattr(snapshot, "risk_5y", None)
    meta           = getattr(snapshot, "meta", None)
    top_holdings   = getattr(snapshot, "top_holdings", [])
    sector_alloc   = getattr(snapshot, "sector_alloc", [])
    top10_weight   = getattr(snapshot, "top10_weight", None)
    total_count    = getattr(snapshot, "total_holdings_count", None)

    expense_ratio = _safe(getattr(meta, "expense_ratio", None)) or _safe(getattr(scheme, "expense_ratio", None))
    aum           = _safe(getattr(meta, "aum", None)) or _safe(getattr(scheme, "aum_cr", None))
    is_direct     = bool(getattr(scheme, "is_direct", False))
    category      = getattr(scheme, "scheme_category", "") or ""
    r_squared     = _safe(getattr(risk_3y, "r_squared", None))

    # Normalize holding weights before scoring (fix double-multiplied percentages)
    if top_holdings:
        top_holdings = normalize_holding_weights(top_holdings)
        # Recompute top10_weight from normalized weights
        top10_weight = round(sum(getattr(h, "weight_pct", 0) or 0 for h in top_holdings[:10]), 2)
        # Guard: if still > 100, it's bad data; use None
        if top10_weight > 100:
            top10_weight = None
        total_count = len(top_holdings)

    # ── Score each pillar ──────────────────────────────────────────
    perf = _score_performance(trailing_map, rolling_returns, risk_3y, risk_5y, nav_days)
    risk = _score_risk(risk_3y, risk_5y)
    cost = _score_cost(expense_ratio, aum, category, is_direct)
    comp = _score_composition(top_holdings, sector_alloc, total_count, top10_weight)
    red  = _compute_red_flags(snapshot, nav_days, expense_ratio, aum, top_holdings, r_squared)

    # ── Weighted composite with missing-pillar redistribution ──────
    pillar_results = [
        ("performance", WEIGHTS["performance"], perf),
        ("risk",        WEIGHTS["risk"],        risk),
        ("cost",        WEIGHTS["cost"],        cost),
        ("composition", WEIGHTS["composition"], comp),
    ]

    available_weight = 0.0
    weighted_sum = 0.0
    for _, w, p in pillar_results:
        if p["score"] is not None:
            weighted_sum += p["score"] * w
            available_weight += w

    if available_weight < 0.10:
        final_score = None
    else:
        # Normalize across available pillars
        raw = weighted_sum / available_weight * 100  # 0–100
        raw_normalized = weighted_sum / available_weight  # already 0–100 since each pillar is 0–100
        final_score = round(max(0, min(100, weighted_sum / available_weight - red["total_penalty"])), 1)
        # Simpler: compute as percentage of available weight, subtract penalty
        composite = weighted_sum / available_weight
        final_score = round(max(0, min(100, composite - red["total_penalty"])), 1)

    # ── Confidence ─────────────────────────────────────────────────
    confidence = _overall_confidence(
        nav_days,
        perf["status"], risk["status"], cost["status"], comp["status"]
    )

    # ── Overall interpretation ─────────────────────────────────────
    overall_badge = score_badge(final_score)
    overall_interp = _interpret_overall(final_score, perf, risk, cost, comp, red, confidence)

    # ── Data coverage note ─────────────────────────────────────────
    missing_pillars = [name for name, _, p in pillar_results if p["score"] is None]
    provisional_pillars = [name for name, _, p in pillar_results
                           if p.get("status") == STATUS_PROVISIONAL and p["score"] is not None]

    return SimpleNamespace(
        # Scores
        final_score      = final_score,
        performance      = perf,
        risk             = risk,
        cost             = cost,
        composition      = comp,
        red_flags        = red,
        # Meta
        confidence       = confidence,
        overall_badge    = overall_badge,
        overall_interpretation = overall_interp,
        missing_pillars  = missing_pillars,
        provisional_pillars = provisional_pillars,
        nav_days         = nav_days,
        model_version    = MODEL_VERSION,
        # Normalized holdings for display
        normalized_top10_weight = top10_weight,
        normalized_total_count  = total_count,
    )


def _interpret_overall(score, perf, risk, cost, comp, red, confidence):
    if score is None:
        return "Insufficient data to generate an overall assessment for this fund."
    badge = score_badge(score)
    parts = [f"Overall score of {score:.0f}/100 — {badge['label']}."]
    if confidence == STATUS_PROVISIONAL:
        parts.append("Note: Score is provisional due to limited data coverage.")
    elif confidence == STATUS_UNRATED:
        parts.append("Warning: Fund lacks sufficient history for a reliable rating.")
    # Highlight standout pillars
    perf_s = perf.get("score")
    risk_s = risk.get("score")
    if perf_s is not None and perf_s >= 75:
        parts.append("Performance is a strong suit.")
    elif perf_s is not None and perf_s < 40:
        parts.append("Performance is a concern.")
    if risk_s is not None and risk_s >= 75:
        parts.append("Downside control is strong.")
    elif risk_s is not None and risk_s < 40:
        parts.append("Risk control needs attention.")
    if red["total_penalty"] >= 8:
        parts.append(f"⚠️ {len(red['flags'])} red flag(s) detected — review before investing.")
    return " ".join(parts)
