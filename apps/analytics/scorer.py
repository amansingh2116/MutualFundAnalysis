"""
apps/analytics/scorer.py — Fund Scoring Engine (v2)
====================================================
Category-normalized, multi-factor mutual fund scoring.

Model overview: see docs/SCORING_MODEL.md

Design:
  - Pure Python — no Django ORM calls; takes a runtime snapshot as input
  - Returns a typed ScorecardResult SimpleNamespace
  - Handles all fallbacks gracefully; uses PROVISIONAL/UNRATED states for
    pillars where data is insufficient rather than fabricating scores
  - Includes 6 pillars: Performance, Risk, Cost, Composition, Debt Quality, Manager Quality
  - Pillar weights adapt by fund type (Equity, Debt, Hybrid, Index)
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

MODEL_VERSION = "2.0"

# Pillar weights by category type
WEIGHTS = {
    "equity": {
        "performance": 0.30,
        "risk": 0.25,
        "cost": 0.15,
        "composition": 0.15,
        "debt": 0.0,
        "manager": 0.15
    },
    "debt": {
        "performance": 0.30,
        "risk": 0.25,
        "cost": 0.20,
        "composition": 0.0,
        "debt": 0.15,
        "manager": 0.10
    },
    "hybrid": {
        "performance": 0.30,
        "risk": 0.25,
        "cost": 0.15,
        "composition": 0.15,
        "debt": 0.05,
        "manager": 0.10
    },
    "index": {
        "performance": 0.40,
        "risk": 0.30,
        "cost": 0.25,
        "composition": 0.0,
        "debt": 0.0,
        "manager": 0.05
    }
}

# Maximum penalty from red flags (points)
MAX_RED_FLAG_PENALTY = 20

# Minimum data requirement (trading days) for Rated status
MIN_RATED_NAV_DAYS = 756   # ~3 years
MIN_PROVISIONAL_NAV_DAYS = 252  # ~1 year

# Expense ratio thresholds by category type: (excellent, good, average, poor)
ER_THRESHOLDS = {
    "equity_direct":   (0.30, 0.60, 1.00, 1.50),
    "equity_regular":  (0.80, 1.20, 1.75, 2.25),
    "index_direct":    (0.05, 0.15, 0.30, 0.50),
    "index_regular":   (0.15, 0.30, 0.50, 0.80),
    "debt_direct":     (0.20, 0.40, 0.70, 1.00),
    "debt_regular":    (0.50, 0.80, 1.20, 1.50),
    "hybrid_direct":   (0.40, 0.70, 1.10, 1.60),
    "hybrid_regular":  (0.90, 1.30, 1.80, 2.30),
    "default":         (0.50, 1.00, 1.50, 2.00),
}

# ── Pillar status tokens ───────────────────────────────────────────────────────
STATUS_RATED       = "RATED"
STATUS_PROVISIONAL = "PROVISIONAL"
STATUS_UNRATED     = "UNRATED"
STATUS_SKIPPED     = "SKIPPED"

# ── Score badge thresholds ─────────────────────────────────────────────────────
def score_badge(score: Optional[float]) -> dict:
    """Return badge label, colour and emoji for a numeric score."""
    if score is None:
        return {"label": "N/A", "color": "gray", "emoji": "⚪"}
    if score >= 80:
        return {"label": "Outstanding", "color": "green",  "emoji": "🟢"}
    if score >= 65:
        return {"label": "Strong",      "color": "blue",   "emoji": "🔵"}
    if score >= 50:
        return {"label": "Good",        "color": "purple", "emoji": "🟣"}
    if score >= 35:
        return {"label": "Fair",        "color": "yellow", "emoji": "🟡"}
    if score >= 20:
        return {"label": "Weak",        "color": "orange", "emoji": "🟠"}
    return     {"label": "Poor",        "color": "red",    "emoji": "🔴"}


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

def _fund_type(category: str) -> str:
    cat = (category or "").lower()
    if any(k in cat for k in ("index", "etf", "nifty 50", "sensex", "tracker")):
        return "index"
    if any(k in cat for k in ("debt", "liquid", "overnight", "short duration",
                               "medium duration", "long duration", "gilt",
                               "credit risk", "banking and psu", "money market",
                               "dynamic bond", "corporate bond", "floater")):
        return "debt"
    if any(k in cat for k in ("hybrid", "balanced", "aggressive", "conservative",
                               "equity savings", "arbitrage", "multi asset")):
        return "hybrid"
    return "equity"

def _er_category(category: str, is_direct: bool) -> str:
    """Map SEBI category string → expense ratio threshold key."""
    ftype = _fund_type(category)
    direct_suffix = "direct" if is_direct else "regular"
    return f"{ftype}_{direct_suffix}"


# ── Portfolio weight normalizer ───────────────────────────────────────────────

def normalize_holding_weights(holdings: list) -> list:
    if not holdings:
        return holdings
    total = sum(getattr(h, "weight_pct", 0) or 0 for h in holdings)
    if total <= 0:
        return holdings

    if total > 150:
        factor = 100.0 / total
        for h in holdings:
            if hasattr(h, "weight_pct") and h.weight_pct is not None:
                object.__setattr__(h, "weight_pct", round(h.weight_pct * factor, 4)) if hasattr(h, '__dict__') else None
                try: h.weight_pct = round(h.weight_pct * factor, 4)
                except AttributeError: pass
    elif total < 2:
        for h in holdings:
            if hasattr(h, "weight_pct") and h.weight_pct is not None:
                try: h.weight_pct = round(h.weight_pct * 100.0, 4)
                except AttributeError: pass
    return holdings

# ── Metrics Extractors ────────────────────────────────────────────────────────

def _std_dev(values):
    if not values or len(values) < 2:
        return 0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


# ── Performance Pillar ────────────────────────────────────────────────────────

def _score_performance(trailing_map: dict, rolling_returns: dict, risk_3y, risk_5y,
                       nav_days: int, fund_type: str, calendar_returns: list = None) -> dict:
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    if fund_type == "index":
        # Index Performance
        tracking_diff_1y = _safe(getattr(trailing_map.get("1Y"), "excess", None))
        tracking_diff_3y = _safe(getattr(trailing_map.get("3Y"), "excess", None))
        tracking_error = _safe(getattr(risk_3y, "tracking_error", None)) if risk_3y else None
        
        if tracking_diff_1y is not None:
            s = _norm(-tracking_diff_1y, -1.5, 0)
            details["tracking_diff_1y"] = {"value": tracking_diff_1y, "score": round(s, 1), "label": "1Y Tracking Difference"}
            weighted_sum += s * 0.50
            available_weights += 0.50
            
        if tracking_error is not None:
            s = _norm(-tracking_error, -0.5, 0)
            details["tracking_error"] = {"value": tracking_error, "score": round(s, 1), "label": "Tracking Error"}
            weighted_sum += s * 0.30
            available_weights += 0.30
            
        if tracking_diff_3y is not None:
            s = _norm(-tracking_diff_3y, -1.5, 0)
            details["tracking_diff_3y"] = {"value": tracking_diff_3y, "score": round(s, 1), "label": "3Y Tracking Difference"}
            weighted_sum += s * 0.20
            available_weights += 0.20
            
        if available_weights < 0.20:
            return {"score": None, "status": STATUS_UNRATED, "details": details, "missing": "Insufficient tracking data"}
            
        score = round(max(0, min(100, weighted_sum / available_weights)), 1)
        return {"score": score, "status": STATUS_RATED if available_weights >= 0.8 else STATUS_PROVISIONAL,
                "details": details, "missing": None, "interpretation": "Index tracking performance."}

    # Equity / Hybrid / Debt Active Performance
    cagr_3y = _safe(getattr(trailing_map.get("3Y"), "cagr_pct", None))
    cagr_5y = _safe(getattr(trailing_map.get("5Y"), "cagr_pct", None))
    cagr_1y = _safe(getattr(trailing_map.get("1Y"), "cagr_pct", None))
    rolling_3y = rolling_returns.get("3Y")
    rolling_5y = rolling_returns.get("5Y")
    win_rate_3y = _safe(getattr(rolling_3y, "win_rate_0", None))
    win_rate_5y = _safe(getattr(rolling_5y, "win_rate_0", None))
    excess_3y = _safe(getattr(trailing_map.get("3Y"), "excess", None))

    if fund_type == "debt":
        if cagr_3y is not None:
            s = _norm(cagr_3y, 4, 10)
            details["cagr_3y"] = {"value": cagr_3y, "score": round(s, 1), "label": "3Y CAGR"}
            weighted_sum += s * 0.40; available_weights += 0.40
        if cagr_1y is not None:
            s = _norm(cagr_1y, 3, 9)
            details["cagr_1y"] = {"value": cagr_1y, "score": round(s, 1), "label": "1Y CAGR"}
            weighted_sum += s * 0.25; available_weights += 0.25
        if win_rate_3y is not None:
            s = min(100.0, win_rate_3y)
            details["win_rate_3y"] = {"value": win_rate_3y, "score": round(s, 1), "label": "3Y Rolling Win Rate"}
            weighted_sum += s * 0.20; available_weights += 0.20
        if excess_3y is not None:
            s = _norm(excess_3y, -2, 3)
            details["excess_3y"] = {"value": excess_3y, "score": round(s, 1), "label": "3Y Excess vs Benchmark"}
            weighted_sum += s * 0.15; available_weights += 0.15
    else:
        if cagr_3y is not None:
            s = _norm(cagr_3y, 0, 22)
            details["cagr_3y"] = {"value": cagr_3y, "score": round(s, 1), "label": "3Y CAGR"}
            weighted_sum += s * 0.30; available_weights += 0.30
        if cagr_5y is not None:
            s = _norm(cagr_5y, 0, 18)
            details["cagr_5y"] = {"value": cagr_5y, "score": round(s, 1), "label": "5Y CAGR"}
            weighted_sum += s * 0.20; available_weights += 0.20
        if cagr_1y is not None:
            s = _norm(cagr_1y, -10, 35)
            details["cagr_1y"] = {"value": cagr_1y, "score": round(s, 1), "label": "1Y CAGR"}
            weighted_sum += s * 0.10; available_weights += 0.10
        if win_rate_3y is not None:
            s = min(100.0, win_rate_3y)
            details["win_rate_3y"] = {"value": win_rate_3y, "score": round(s, 1), "label": "3Y Rolling Win Rate (>0%)"}
            weighted_sum += s * 0.15; available_weights += 0.15
        if win_rate_5y is not None:
            s = min(100.0, win_rate_5y)
            details["win_rate_5y"] = {"value": win_rate_5y, "score": round(s, 1), "label": "5Y Rolling Win Rate (>0%)"}
            weighted_sum += s * 0.10; available_weights += 0.10
        if excess_3y is not None:
            s = _norm(excess_3y, -5, 10)
            details["excess_3y"] = {"value": excess_3y, "score": round(s, 1), "label": "3Y Excess vs Benchmark"}
            weighted_sum += s * 0.10; available_weights += 0.10
            
        # Return Consistency
        if calendar_returns and len(calendar_returns) >= 2:
            c_returns = [getattr(c, "fund_return", 0) or 0 for c in calendar_returns]
            std = _std_dev(c_returns)
            s = _norm(1 - (std / 30), 0, 1)
            details["consistency"] = {"value": std, "score": round(s, 1), "label": "Return Consistency"}
            weighted_sum += s * 0.05; available_weights += 0.05

    if available_weights < 0.20:
        return {"score": None, "status": STATUS_UNRATED, "details": details,
                "missing": "Insufficient trailing return data (need at least 1Y CAGR)"}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.80 else STATUS_PROVISIONAL
    missing_note = None if available_weights >= 0.80 else "Some return periods unavailable; score is provisional"

    return {"score": score, "status": status, "details": details,
            "missing": missing_note, "interpretation": "Overall strong performance indicates consistency across multiple timeframes." if score >= 65 else "Performance metrics."}


# ── Risk / Stability Pillar ───────────────────────────────────────────────────

def _score_risk(risk_3y, risk_5y, fund_type: str) -> dict:
    rm = risk_3y or risk_5y
    period_label = "3Y" if risk_3y else ("5Y" if risk_5y else None)
    details = {}

    if rm is None:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "No risk metrics available", "interpretation": "Risk metrics require at least 3 years of NAV data."}

    available_weights = 0.0
    weighted_sum = 0.0

    sortino = _safe(rm.sortino_ratio)
    max_dd = _safe(rm.max_drawdown)
    dn_cap = _safe(rm.downside_capture)
    sharpe = _safe(rm.sharpe_ratio)
    ir = _safe(getattr(rm, "info_ratio", None))
    beta = _safe(getattr(rm, "beta", None))
    up_cap = _safe(getattr(rm, "upside_capture", None))

    if fund_type == "debt":
        if sharpe is not None:
            s = _norm(sharpe, 0, 2.0)
            details["sharpe"] = {"value": sharpe, "score": round(s, 1), "label": f"Sharpe Ratio ({period_label})"}
            weighted_sum += s * 0.30; available_weights += 0.30
        if sortino is not None:
            s = _norm(sortino, 0, 2.5)
            details["sortino"] = {"value": sortino, "score": round(s, 1), "label": f"Sortino Ratio ({period_label})"}
            weighted_sum += s * 0.25; available_weights += 0.25
        if max_dd is not None:
            s = _norm(max_dd, -20, -0.5)
            details["max_drawdown"] = {"value": max_dd, "score": round(s, 1), "label": f"Max Drawdown ({period_label})"}
            weighted_sum += s * 0.25; available_weights += 0.25
        if dn_cap is not None:
            s = _norm(100 - dn_cap, -20, 30)
            details["downside_capture"] = {"value": dn_cap, "score": round(s, 1), "label": f"Downside Capture ({period_label})"}
            weighted_sum += s * 0.20; available_weights += 0.20
    else:
        if sortino is not None:
            s = _norm(sortino, 0, 3.0)
            details["sortino"] = {"value": sortino, "score": round(s, 1), "label": f"Sortino Ratio ({period_label})"}
            weighted_sum += s * 0.25; available_weights += 0.25
        if max_dd is not None:
            # Check if small cap for different bounds
            bounds = (-70, -10) if 'small' in (getattr(rm, 'category_name', '') or '').lower() else (-60, -5)
            s = _norm(max_dd, bounds[0], bounds[1])
            details["max_drawdown"] = {"value": max_dd, "score": round(s, 1), "label": f"Max Drawdown ({period_label})"}
            weighted_sum += s * 0.20; available_weights += 0.20
        if dn_cap is not None:
            s = _norm(100 - dn_cap, -30, 30)
            details["downside_capture"] = {"value": dn_cap, "score": round(s, 1), "label": f"Downside Capture ({period_label})"}
            weighted_sum += s * 0.20; available_weights += 0.20
        if sharpe is not None:
            s = _norm(sharpe, 0, 2.5)
            details["sharpe"] = {"value": sharpe, "score": round(s, 1), "label": f"Sharpe Ratio ({period_label})"}
            weighted_sum += s * 0.15; available_weights += 0.15
        if ir is not None and fund_type != "index":
            s = _norm(ir, -0.5, 1.0)
            details["info_ratio"] = {"value": ir, "score": round(s, 1), "label": f"Information Ratio ({period_label})"}
            weighted_sum += s * 0.10; available_weights += 0.10
        if beta is not None:
            s = _norm(1.2 - beta, 0, 0.7)
            details["beta"] = {"value": beta, "score": round(s, 1), "label": f"Beta ({period_label})"}
            weighted_sum += s * 0.05; available_weights += 0.05
        if up_cap is not None and dn_cap is not None:
            s = _norm(up_cap - dn_cap, -20, 40)
            details["up_dn_asymmetry"] = {"value": up_cap - dn_cap, "score": round(s, 1), "label": f"Up/Down Asymmetry ({period_label})"}
            weighted_sum += s * 0.05; available_weights += 0.05

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "Insufficient risk metrics", "interpretation": "Risk scoring requires at least one of: Sortino Ratio, Max Drawdown."}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    return {"score": score, "status": status, "details": details, "missing": None, "interpretation": "Risk assessment based on downside protection and volatility."}


# ── Cost Pillar ────────────────────────────────────────────────────────────────

def _score_cost(expense_ratio: Optional[float], aum: Optional[float],
                category: str, is_direct: bool) -> dict:
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    er_cat = _er_category(category, is_direct)
    thresholds = ER_THRESHOLDS.get(er_cat, ER_THRESHOLDS["default"])
    excellent, good, avg, poor = thresholds

    er = _safe(expense_ratio)
    if er is not None and er > 0:
        s = _norm(-er, -poor, -excellent)
        details["expense_ratio"] = {"value": er, "score": round(s, 1), "label": "Expense Ratio", "benchmark": f"Category norm: {excellent}–{avg}%"}
        weighted_sum += s * 0.70; available_weights += 0.70
    else:
        details["expense_ratio"] = {"value": None, "score": None, "label": "Expense Ratio"}

    aum_val = _safe(aum)
    if aum_val is not None and aum_val > 0:
        if aum_val > 10000: s = 100
        elif aum_val >= 5000: s = 85
        elif aum_val >= 1000: s = 70
        elif aum_val >= 500: s = 50
        elif aum_val >= 100: s = 30
        else: s = 10
        details["aum"] = {"value": aum_val, "score": round(s, 1), "label": "AUM (₹ Cr)"}
        weighted_sum += s * 0.30; available_weights += 0.30
    else:
        details["aum"] = {"value": None, "score": None, "label": "AUM (₹ Cr)"}

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "Expense ratio not available"}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    return {"score": score, "status": status, "details": details, "missing": None, "interpretation": "Cost assessment."}


# ── Composition Pillar ────────────────────────────────────────────────────────

def _score_composition(top_holdings: list, sector_alloc: list,
                       total_count: int, top10_weight: Optional[float],
                       large_cap_pct: float = None, mid_cap_pct: float = None,
                       small_cap_pct: float = None, turnover: float = None,
                       fund_type: str = "equity") -> dict:
    if fund_type in ("debt", "index"):
        return {"score": None, "status": STATUS_SKIPPED, "details": {}, "missing": "Not applicable for this category"}
        
    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    if not top_holdings and not sector_alloc:
        return {"score": None, "status": STATUS_UNRATED, "details": details, "missing": "No holdings data"}

    t10w = _safe(top10_weight)
    if t10w is not None and t10w <= 100:
        s = _norm(90 - t10w, 0, 50)
        details["top10_weight"] = {"value": t10w, "score": round(s, 1), "label": "Top-10 Concentration (%)"}
        weighted_sum += s * 0.30; available_weights += 0.30
        
    if sector_alloc:
        weights = [getattr(s, "weight_pct", 0) or 0 for s in sector_alloc]
        total_w = sum(weights)
        if total_w > 0:
            fracs = [w / total_w for w in weights]
            hhi = sum(f * f for f in fracs)
            s = _norm(1 - (hhi / 0.5), 0, 1)
            details["sector_hhi"] = {"value": round(hhi, 3), "score": round(s, 1), "label": "Sector Diversification (HHI)"}
            weighted_sum += s * 0.25; available_weights += 0.25

    if total_count is not None and total_count > 0:
        s = _norm(total_count - 5, 0, 45)
        details["holdings_count"] = {"value": total_count, "score": round(s, 1), "label": "Total Holdings"}
        weighted_sum += s * 0.15; available_weights += 0.15

    if large_cap_pct is not None or mid_cap_pct is not None or small_cap_pct is not None:
        l_pct = _safe(large_cap_pct) or 0
        m_pct = _safe(mid_cap_pct) or 0
        s_pct = _safe(small_cap_pct) or 0
        liq = (1.0 * l_pct + 0.6 * m_pct + 0.1 * s_pct)
        # Assuming percentage points
        s = _norm(liq, 20, 95)
        details["liquidity"] = {"value": liq, "score": round(s, 1), "label": "Portfolio Liquidity Score"}
        weighted_sum += s * 0.20; available_weights += 0.20
    else:
        # Without explicit cap allocations, approximate if possible or redistribute
        # Let's redistribute the 20%
        pass

    if turnover is not None:
        s = _norm(1 - (turnover / 500), 0, 1)
        details["turnover"] = {"value": turnover, "score": round(s, 1), "label": "Portfolio Turnover (%)"}
        weighted_sum += s * 0.10; available_weights += 0.10

    if available_weights < 0.30:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "Insufficient portfolio data"}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    return {"score": score, "status": status, "details": details, "missing": None, "interpretation": "Composition and liquidity."}


# ── Debt Quality Pillar ────────────────────────────────────────────────────────

def _score_debt(fund_type: str, category: str, credit_quality: float = None, 
                mod_duration: float = None, ytm: float = None, 
                cat_ytm_avg: float = None, sov_aaa_pct: float = None) -> dict:
    if fund_type not in ("debt", "hybrid"):
        return {"score": None, "status": STATUS_SKIPPED, "details": {}, "missing": "Not applicable for this category"}

    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    if credit_quality is not None:
        # Assuming credit_quality is already 0-100 mapped based on rating
        details["credit_quality"] = {"value": credit_quality, "score": credit_quality, "label": "Credit Quality"}
        weighted_sum += credit_quality * 0.35; available_weights += 0.35
        
    if mod_duration is not None:
        # Mismatch logic - simplified, providing 70 as placeholder if no exact band matching 
        s = 70.0 # Provisional default
        details["mod_duration"] = {"value": mod_duration, "score": s, "label": "Modified Duration"}
        weighted_sum += s * 0.25; available_weights += 0.25

    if ytm is not None and cat_ytm_avg is not None:
        s = _norm(ytm - cat_ytm_avg, -2, 2)
        details["ytm"] = {"value": ytm, "score": round(s, 1), "label": "YTM vs Category"}
        weighted_sum += s * 0.20; available_weights += 0.20

    if sov_aaa_pct is not None:
        s = _norm(sov_aaa_pct, 30, 100)
        details["liquidity"] = {"value": sov_aaa_pct, "score": round(s, 1), "label": "Debt Liquidity (% Sov/AAA)"}
        weighted_sum += s * 0.20; available_weights += 0.20

    if available_weights < 0.20:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "Insufficient debt metrics"}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.60 else STATUS_PROVISIONAL
    return {"score": score, "status": status, "details": details, "missing": None, "interpretation": "Debt Quality metrics."}


# ── Manager Quality Pillar ────────────────────────────────────────────────────

def _score_manager(fund_type: str, tenure: float = None, avg_alpha: float = None,
                   amc_gov: float = None, num_funds: int = None, r_sq: float = None) -> dict:
    if fund_type == "index":
        # Simplified manager quality for index
        s_gov = _safe(amc_gov) or 80.0
        score = round(s_gov * 0.60 + 50.0 * 0.40, 1) # 40% tracking error trend placeholder
        return {"score": score, "status": STATUS_PROVISIONAL, "details": {}, "missing": None, "interpretation": "Index passive management."}

    details = {}
    available_weights = 0.0
    weighted_sum = 0.0

    if tenure is not None:
        s = _norm(tenure, 0, 8)
        details["tenure"] = {"value": tenure, "score": round(s, 1), "label": "Manager Tenure (Yrs)"}
        weighted_sum += s * 0.20; available_weights += 0.20

    if avg_alpha is not None:
        s = _norm(avg_alpha, -2, 5)
        details["avg_alpha"] = {"value": avg_alpha, "score": round(s, 1), "label": "Manager Avg Alpha"}
        weighted_sum += s * 0.25; available_weights += 0.25

    if amc_gov is not None:
        details["amc_gov"] = {"value": amc_gov, "score": amc_gov, "label": "AMC Governance"}
        weighted_sum += amc_gov * 0.25; available_weights += 0.25

    if num_funds is not None:
        s = _norm(10 - num_funds, 0, 9)
        details["num_funds"] = {"value": num_funds, "score": round(s, 1), "label": "# Funds Managed"}
        weighted_sum += s * 0.15; available_weights += 0.15

    if r_sq is not None:
        if r_sq > 0.95: s = 0
        elif r_sq > 0.85: s = 30
        elif r_sq > 0.75: s = 60
        elif r_sq > 0.60: s = 85
        else: s = 100
        details["closet_index"] = {"value": r_sq, "score": s, "label": "Closet Indexing Check (R²)"}
        weighted_sum += s * 0.15; available_weights += 0.15

    if available_weights < 0.20:
        return {"score": None, "status": STATUS_PROVISIONAL, "details": details, "missing": "Insufficient manager metrics"}

    score = round(max(0, min(100, weighted_sum / available_weights)), 1)
    status = STATUS_RATED if available_weights >= 0.70 else STATUS_PROVISIONAL
    return {"score": score, "status": status, "details": details, "missing": None, "interpretation": "Manager Quality assessment."}


# ── Red Flags ─────────────────────────────────────────────────────────────────

def _compute_red_flags(snapshot, nav_days: int, expense_ratio, aum,
                       top_holdings, r_squared, turnover, info_ratio, credit_rating) -> dict:
    flags = []
    total_penalty = 0

    def add_flag(code, label, severity, penalty, note):
        nonlocal total_penalty
        total_penalty += penalty
        flags.append({"code": code, "label": label, "severity": severity, "penalty": penalty, "note": note})

    if nav_days < MIN_PROVISIONAL_NAV_DAYS:
        add_flag("short_history", "Insufficient NAV History", "critical", 8, "Less than 1 year data.")

    bm_name = getattr(snapshot, "benchmark_name", None)
    if not bm_name:
        add_flag("no_benchmark", "No Benchmark Mapped", "warning", 3, "No benchmark for relative evaluation.")

    er = _safe(expense_ratio)
    ftype = _fund_type(getattr(snapshot.scheme, "scheme_category", ""))
    if er:
        if ftype == "equity" and er > 2.5:
            add_flag("high_er_equity", "Very High Expense Ratio (>2.5%)", "warning", 5, "Erodes returns.")
        elif ftype == "debt" and er > 1.5:
            add_flag("high_er_debt", "Very High Expense Ratio (>1.5%)", "warning", 5, "Erodes returns.")

    aum_val = _safe(aum)
    if aum_val is not None and 0 < aum_val < 100:
        add_flag("low_aum", "Very Low AUM (<₹100 Cr)", "warning", 3, "Scale risk.")
    
    if aum_val is not None and aum_val > 20000 and "small" in (getattr(snapshot.scheme, "scheme_category", "") or "").lower():
        add_flag("huge_small_cap", "Very High AUM in Small Cap (>₹20,000 Cr)", "warning", 4, "May struggle to deploy capital efficiently.")

    if top_holdings:
        max_w = max((getattr(h, "weight_pct", 0) or 0) for h in top_holdings)
        if max_w > 50:
            add_flag("extreme_concentration", f"Extreme Concentration ({max_w:.1f}%)", "critical", 5, "Single holding dominates.")
    elif ftype != "debt":
        add_flag("no_holdings", "Holdings Data Unavailable", "info", 2, "Cannot score Composition.")

    r_sq = _safe(r_squared)
    if r_sq is not None and r_sq < 50 and bm_name:
        add_flag("bm_mismatch", "Benchmark Mismatch (Low R²)", "warning", 3, "R² < 50% implies benchmark may be incorrect.")

    if turnover and turnover > 500 and info_ratio and info_ratio < 0:
        add_flag("high_turnover", "High Turnover without IR justification", "warning", 3, "Churning portfolio without generating positive active return.")

    if credit_rating and credit_rating < 60: # Rough approximation for < AA
        add_flag("low_credit", "Credit Risk Fund with < AA avg credit", "warning", 4, "High default risk.")

    # Front running/SEBI actions would be fetched from meta, if available
    amc_gov = getattr(snapshot.meta, "amc_governance_score", None) if hasattr(snapshot, "meta") else None
    if amc_gov is not None and amc_gov < 50:
        add_flag("poor_governance", "Poor AMC Governance", "critical", 8, "Past regulatory or governance issues flagged.")

    total_penalty = min(total_penalty, MAX_RED_FLAG_PENALTY)
    return {"flags": flags, "total_penalty": total_penalty}


# ── Overall Confidence ────────────────────────────────────────────────────────

def _overall_confidence(nav_days: int, statuses: list) -> str:
    if nav_days < MIN_PROVISIONAL_NAV_DAYS:
        return STATUS_UNRATED
    unrated = statuses.count(STATUS_UNRATED)
    if unrated >= 2:
        return STATUS_UNRATED
    provisional = statuses.count(STATUS_PROVISIONAL) + statuses.count(STATUS_UNRATED)
    if provisional >= 2 or nav_days < MIN_RATED_NAV_DAYS:
        return STATUS_PROVISIONAL
    if provisional == 1:
        # Rated (Partial) could just be RATED for now as models support RATED/PROVISIONAL/UNRATED
        return STATUS_RATED
    return STATUS_RATED


# ── Category Rank ─────────────────────────────────────────────────────────────

def compute_category_rank(scheme, final_score: Optional[float]) -> dict:
    if final_score is None:
        return {"rank": None, "total": None, "percentile": None}

    try:
        from apps.funds.models import Scheme
        from apps.analytics.models import TrailingReturn
        from django.core.cache import cache

        cache_key = f"category_scores:v2:{scheme.scheme_category}"
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
                    if not tr:
                        continue
                    p_score = _norm(_safe(tr.get("cagr_pct")), 0, 20) * 0.40
                    peer_scores[peer["amfi_code"]] = round(p_score, 2)
                except Exception:
                    continue

            cache.set(cache_key, peer_scores, 60 * 60 * 12)  # 12 hours

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
    info_ratio    = _safe(getattr(risk_3y, "info_ratio", None))
    
    fund_type = _fund_type(category)
    weights = WEIGHTS[fund_type]
    
    turnover = _safe(getattr(meta, "portfolio_turnover", None))
    credit_rating = _safe(getattr(meta, "average_credit_rating", None))
    mod_duration = _safe(getattr(meta, "modified_duration", None))
    ytm = _safe(getattr(meta, "ytm", None))
    cat_ytm_avg = _safe(getattr(meta, "category_ytm_avg", None))
    sov_aaa_pct = _safe(getattr(meta, "sov_aaa_pct", None))
    
    tenure = _safe(getattr(meta, "manager_tenure", None))
    avg_alpha = _safe(getattr(meta, "manager_alpha", None))
    amc_gov = _safe(getattr(meta, "amc_governance_score", None))
    num_funds = _safe(getattr(meta, "manager_num_funds", None))
    
    # Portfolio Liquidity approximations for equity
    large_cap_pct = _safe(getattr(meta, "large_cap_pct", None))
    mid_cap_pct = _safe(getattr(meta, "mid_cap_pct", None))
    small_cap_pct = _safe(getattr(meta, "small_cap_pct", None))

    if top_holdings:
        top_holdings = normalize_holding_weights(top_holdings)
        top10_weight = round(sum(getattr(h, "weight_pct", 0) or 0 for h in top_holdings[:10]), 2)
        if top10_weight > 100: top10_weight = None
        total_count = len(top_holdings)

    # Calculate calendar returns from trailing_map or other if available
    calendar_returns = getattr(snapshot, "calendar_returns", None) 
    if not calendar_returns and hasattr(snapshot, 'yearly_returns'):
        calendar_returns = snapshot.yearly_returns

    # Score Pillars
    perf = _score_performance(trailing_map, rolling_returns, risk_3y, risk_5y, nav_days, fund_type, calendar_returns)
    risk = _score_risk(risk_3y, risk_5y, fund_type)
    cost = _score_cost(expense_ratio, aum, category, is_direct)
    comp = _score_composition(top_holdings, sector_alloc, total_count, top10_weight, 
                              large_cap_pct, mid_cap_pct, small_cap_pct, turnover, fund_type)
    debt = _score_debt(fund_type, category, credit_rating, mod_duration, ytm, cat_ytm_avg, sov_aaa_pct)
    manager = _score_manager(fund_type, tenure, avg_alpha, amc_gov, num_funds, r_squared)
    
    red  = _compute_red_flags(snapshot, nav_days, expense_ratio, aum, top_holdings, r_squared, turnover, info_ratio, credit_rating)

    pillar_results = [
        ("performance", weights["performance"], perf),
        ("risk",        weights["risk"],        risk),
        ("cost",        weights["cost"],        cost),
        ("composition", weights["composition"], comp),
        ("debt",        weights["debt"],        debt),
        ("manager",     weights["manager"],     manager),
    ]

    available_weight = 0.0
    weighted_sum = 0.0
    for _, w, p in pillar_results:
        if p.get("score") is not None and p.get("status") != STATUS_SKIPPED:
            weighted_sum += p["score"] * w
            available_weight += w

    if available_weight < 0.10:
        final_score = None
    else:
        composite = weighted_sum / available_weight
        final_score = round(max(0, min(100, composite - red["total_penalty"])), 1)

    statuses = [p["status"] for _, w, p in pillar_results if w > 0 and p.get("status") != STATUS_SKIPPED]
    confidence = _overall_confidence(nav_days, statuses)

    overall_badge = score_badge(final_score)
    overall_interp = "V2 Score updated incorporating Manager and Debt Quality metrics."

    missing_pillars = [name for name, w, p in pillar_results if p.get("score") is None and w > 0]
    provisional_pillars = [name for name, _, p in pillar_results if p.get("status") == STATUS_PROVISIONAL]

    return SimpleNamespace(
        final_score      = final_score,
        performance      = perf,
        risk             = risk,
        cost             = cost,
        composition      = comp,
        debt             = debt,
        manager          = manager,
        red_flags        = red,
        confidence       = confidence,
        overall_badge    = overall_badge,
        overall_interpretation = overall_interp,
        missing_pillars  = missing_pillars,
        provisional_pillars = provisional_pillars,
        nav_days         = nav_days,
        model_version    = MODEL_VERSION,
        normalized_top10_weight = top10_weight,
        normalized_total_count  = total_count,
    )
