"""
apps/funds/report.py — Comprehensive PDF Fund Report Generator

Stack: Playwright (headless Chromium) + Plotly + kaleido (chart PNG export)

Report Sections:
  1. Cover Page
  2. Executive Summary
  3. Returns Analysis (Trailing + Calendar)
  4. Rolling Returns Analysis
  5. Risk & Risk-Adjusted Returns
  6. Market Regimes & Crisis Periods
  7. Portfolio Composition
  8. Costs & Fund Mechanics
  9. Fund Scorecard (Model Analysis)
  10. Manager & Disclaimer
"""
from __future__ import annotations

import base64
import json
import logging
import traceback as _tb
from datetime import date
from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from django.http import HttpResponse
from django.template.loader import render_to_string

logger = logging.getLogger("mfanalysis")

# ── Color palette ─────────────────────────────────────────────────────────────
C_INDIGO  = "#6366f1"
C_VIOLET  = "#8b5cf6"
C_AMBER   = "#f59e0b"
C_GREEN   = "#22c55e"
C_RED     = "#ef4444"
C_TEAL    = "#14b8a6"
C_SLATE   = "#64748b"
C_BORDER  = "#e2e8f0"
C_TEXT    = "#1e293b"
C_EMERALD = "#10b981"
C_ORANGE  = "#f97316"

CHART_FONT   = dict(family="Arial, sans-serif", size=10, color=C_TEXT)
CHART_LAYOUT = dict(
    font=CHART_FONT,
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=35, r=20, t=35, b=35),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                font=dict(size=9)),
    xaxis=dict(gridcolor=C_BORDER, showgrid=True, gridwidth=0.5),
    yaxis=dict(gridcolor=C_BORDER, showgrid=True, gridwidth=0.5),
)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _flt(val, default=None) -> Optional[float]:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _pct(val, decimals=2, default="—") -> str:
    v = _flt(val)
    return f"{v:.{decimals}f}%" if v is not None else default


def _fig_to_b64(fig, width=680, height=260) -> str:
    try:
        png_bytes = fig.to_image(format="png", width=width, height=height, scale=2)
        return base64.b64encode(png_bytes).decode("utf-8")
    except Exception as exc:
        logger.warning("Chart export failed: %s", exc)
        return ""


def _safe_chart(func, *args, **kwargs) -> str:
    """Run a chart function; return '' on any error so the report still generates."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        logger.warning("Chart '%s' skipped — %s\n%s",
                       func.__name__, exc, _tb.format_exc())
        return ""


def _badge_color(badge) -> str:
    """Accept either a string badge label or the full badge dict from scorer."""
    if isinstance(badge, dict):
        badge = badge.get("label", "")
    return {
        "Outstanding": "#059669", "Strong": "#22c55e",
        "Good": "#6366f1", "Fair": "#f59e0b",
        "Weak": "#ef4444", "Poor": "#dc2626",
    }.get(str(badge) if badge else "", C_SLATE)


# ── Chart builders ────────────────────────────────────────────────────────────

def _chart_trailing_returns(trailing, cat_snap) -> str:
    """Grouped bar: Fund vs Benchmark vs Category Avg for each period."""
    periods, fund_vals, bm_vals, cat_vals = [], [], [], []
    cat_map = {}
    if cat_snap:
        cat_map = {
            "1Y": _flt(cat_snap.avg_return_1y),
            "3Y": _flt(cat_snap.avg_return_3y),
            "5Y": _flt(cat_snap.avg_return_5y),
        }
    for r in (trailing or []):
        p = getattr(r, "period", None) or ""
        cv = _flt(getattr(r, "cagr_pct", None))
        bv = _flt(getattr(r, "bm_cagr", None))
        if cv is not None and p:
            periods.append(p)
            fund_vals.append(cv)
            bm_vals.append(bv)
            cat_vals.append(cat_map.get(p))
    if not periods:
        return ""
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Fund", x=periods, y=fund_vals, marker_color=C_INDIGO,
                         text=[f"{v:.1f}%" for v in fund_vals], textposition="outside",
                         textfont=dict(size=9)))
    if any(v is not None for v in bm_vals):
        bm_c = [v if v is not None else 0 for v in bm_vals]
        fig.add_trace(go.Bar(name="Benchmark", x=periods, y=bm_c, marker_color=C_SLATE,
                             text=[f"{v:.1f}%" if v is not None else "" for v in bm_vals],
                             textposition="outside", textfont=dict(size=9)))
    if any(v is not None for v in cat_vals):
        cat_c = [v if v is not None else 0 for v in cat_vals]
        fig.add_trace(go.Bar(name="Category Avg", x=periods, y=cat_c, marker_color=C_AMBER,
                             text=[f"{v:.1f}%" if v is not None else "" for v in cat_vals],
                             textposition="outside", textfont=dict(size=9)))
    fig.update_layout(**CHART_LAYOUT, title_text="Trailing Returns — CAGR (%)",
                      barmode="group", yaxis_title="Return (%)", height=270)
    return _fig_to_b64(fig, 680, 270)


def _chart_calendar_returns(calendar, cat_snap) -> str:
    """Colored bar chart with benchmark dot line and category avg dash line."""
    years, fund_vals, bm_vals, cat_vals = [], [], [], []
    cat_cal = {}
    if cat_snap and cat_snap.calendar_returns_json:
        try:
            raw = cat_snap.calendar_returns_json
            if isinstance(raw, str):
                raw = json.loads(raw)
            cat_cal = {str(k): _flt(v.get("avg") if isinstance(v, dict) else v)
                       for k, v in raw.items()}
        except Exception:
            pass
    for r in sorted(calendar or [], key=lambda x: getattr(x, "year", 0)):
        yr = str(getattr(r, "year", ""))
        cv = _flt(getattr(r, "return_pct", None))
        if cv is None:
            cv = _flt(getattr(r, "fund_return", None))
        bv = _flt(getattr(r, "bm_return", None))
        if cv is not None and yr:
            years.append(yr)
            fund_vals.append(cv)
            bm_vals.append(bv)
            cat_vals.append(cat_cal.get(yr))
    if not years:
        return ""
    colors = [C_GREEN if v >= 0 else C_RED for v in fund_vals]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Fund", x=years, y=fund_vals, marker_color=colors,
                         text=[f"{v:.1f}%" for v in fund_vals],
                         textposition="outside", textfont=dict(size=8)))
    if any(v is not None for v in bm_vals):
        fig.add_trace(go.Scatter(name="Benchmark", x=years, y=bm_vals,
                                 mode="lines+markers",
                                 line=dict(color=C_SLATE, width=1.5, dash="dot"),
                                 marker=dict(size=4)))
    if any(v is not None for v in cat_vals):
        fig.add_trace(go.Scatter(name="Category Avg", x=years, y=cat_vals,
                                 mode="lines+markers",
                                 line=dict(color=C_AMBER, width=1.5, dash="dash"),
                                 marker=dict(size=4)))
    fig.add_hline(y=0, line_color=C_SLATE, line_width=0.8)
    fig.update_layout(**CHART_LAYOUT, title_text="Calendar Year Returns (%)",
                      yaxis_title="Return (%)", height=270)
    return _fig_to_b64(fig, 680, 270)


def _chart_nav_growth(nav_series, benchmark_series) -> str:
    """Growth of Rs.1 lakh invested — fund vs benchmark (full history)."""
    try:
        if nav_series is None or nav_series.empty:
            return ""
        nav = nav_series
        base = float(nav.iloc[0])
        nav_growth = (nav / base) * 100000
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[d.date().isoformat() for d in nav.index],
            y=nav_growth.values,
            mode="lines", name="Fund (₹1L invested)",
            line=dict(color=C_INDIGO, width=2),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.08)",
        ))
        if benchmark_series is not None and not benchmark_series.empty:
            bm = benchmark_series[benchmark_series.index >= nav.index[0]]
            if not bm.empty:
                bm_base = float(bm.iloc[0])
                bm_growth = (bm / bm_base) * 100000
                fig.add_trace(go.Scatter(
                    x=[d.date().isoformat() for d in bm.index],
                    y=bm_growth.values,
                    mode="lines", name="Benchmark (₹1L invested)",
                    line=dict(color=C_SLATE, width=1.5, dash="dash"),
                ))
        fig.update_layout(**CHART_LAYOUT, title_text="Growth of ₹1,00,000 Since Inception",
                          yaxis_title="Portfolio Value (₹)", height=260)
        return _fig_to_b64(fig, 680, 260)
    except Exception as exc:
        logger.warning("NAV growth chart failed: %s", exc)
        return ""


def _chart_rolling_timeseries(nav_series, bm_series) -> str:
    """3Y rolling returns plotted over time as an area chart (legacy alias)."""
    return _chart_rolling_timeseries_window(nav_series, bm_series, "3Y")


def _chart_rolling_timeseries_window(nav_series, bm_series, window="3Y") -> str:
    """Rolling returns for a specific window plotted over time as an area chart.
    Computes the timeseries directly from nav_series and bm_series."""
    import pandas as pd
    color_map = {
        "1Y": C_EMERALD, "2Y": C_TEAL, "3Y": C_INDIGO,
        "5Y": C_VIOLET, "7Y": C_AMBER,
    }
    days_map = {"1Y": 252, "2Y": 504, "3Y": 756, "5Y": 1260, "7Y": 1764}
    days = days_map.get(window)
    if not days:
        return ""
    try:
        if nav_series is None or len(nav_series) < days + 5:
            return ""
        daily = nav_series.resample("B").ffill().dropna()
        if len(daily) <= days:
            return ""
        rolling = ((daily / daily.shift(days)) ** (252 / days) - 1) * 100
        rolling = rolling.dropna()
        if rolling.empty:
            return ""
        col = color_map.get(window, C_INDIGO)
        fill_col = col.lstrip("#")
        r_int, g_int, b_int = int(fill_col[0:2], 16), int(fill_col[2:4], 16), int(fill_col[4:6], 16)
        fill_rgba = f"rgba({r_int},{g_int},{b_int},0.10)"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=rolling.index, y=rolling.values, mode="lines",
            name=f"{window} Rolling Return",
            line=dict(color=col, width=1.8),
            fill="tozeroy", fillcolor=fill_rgba,
        ))
        if bm_series is not None and not bm_series.empty:
            bm_daily = bm_series.resample("B").ffill().dropna()
            if len(bm_daily) > days:
                bm_rolling = ((bm_daily / bm_daily.shift(days)) ** (252 / days) - 1) * 100
                bm_rolling = bm_rolling.dropna()
                if not bm_rolling.empty:
                    fig.add_trace(go.Scatter(
                        x=bm_rolling.index, y=bm_rolling.values, mode="lines",
                        name="Benchmark",
                        line=dict(color=C_SLATE, width=1.2, dash="dash"),
                    ))
        fig.add_hline(y=0, line_color=C_RED, line_width=0.8, line_dash="dash")
        fig.update_layout(**CHART_LAYOUT,
                          title_text=f"{window} Rolling Return Over Time (%)",
                          yaxis_title=f"Rolling {window} Return (%)", height=220)
        return _fig_to_b64(fig, 680, 220)
    except Exception:
        return ""


def _chart_quarterly_perf(quarterly) -> str:
    """Grouped bar chart: best 6 quarters (green) and worst 6 quarters (red)."""
    if not quarterly:
        return ""
    upside   = (quarterly.get("upside") or [])[:8]
    downside = (quarterly.get("downside") or [])[:8]
    if not upside and not downside:
        return ""
    labels, fund_vals, bm_vals, colors = [], [], [], []
    for q in downside:  # worst first
        labels.append(q["quarter"])
        fund_vals.append(q["fund_return"])
        bm_vals.append(q.get("benchmark_return"))
        colors.append(C_RED)
    for q in upside[::-1]:  # best last (reversed so highest is rightmost)
        labels.append(q["quarter"])
        fund_vals.append(q["fund_return"])
        bm_vals.append(q.get("benchmark_return"))
        colors.append(C_GREEN)
    if not labels:
        return ""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Fund Return", x=labels, y=fund_vals,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in fund_vals],
        textposition="outside", textfont=dict(size=8),
    ))
    bm_clean = [v if v is not None else 0 for v in bm_vals]
    if any(v != 0 for v in bm_clean):
        fig.add_trace(go.Scatter(
            name="Benchmark", x=labels, y=bm_clean,
            mode="markers", marker=dict(color=C_SLATE, size=5, symbol="diamond"),
        ))
    fig.add_hline(y=0, line_color=C_SLATE, line_width=0.8)
    fig.update_layout(**CHART_LAYOUT,
                      title_text="Best & Worst Quarters — Fund Return (%)",
                      barmode="group", yaxis_title="Quarterly Return (%)", height=250)
    return _fig_to_b64(fig, 680, 250)


def _chart_tech_riskometer(tf_data: dict, label: str = "Daily") -> str:
    """Semi-circle gauge showing Buy/Sell/Neutral signal balance for a timeframe."""
    if not tf_data:
        return ""
    try:
        sum_c = tf_data.get("sum_counts", tf_data) if isinstance(tf_data, dict) else {}
        buy   = int(sum_c.get("buy", 0) or sum_c.get("buy_count", 0) or 0)
        sell  = int(sum_c.get("sell", 0) or sum_c.get("sell_count", 0) or 0)
        neut  = int(sum_c.get("neutral", 0) or sum_c.get("neutral_count", 0) or 0)
        total = buy + sell + neut
        if total == 0:
            return ""
        # Score: 0 = full sell, 50 = neutral, 100 = full buy
        score = round((buy / total) * 100)
        rating = sum_c.get("rating", tf_data.get("overall_action", "Neutral"))

        # Color based on score
        if score >= 60:
            needle_color = C_GREEN
        elif score <= 40:
            needle_color = C_RED
        else:
            needle_color = C_AMBER

        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": f"{label} Signals<br><span style='font-size:10px'>{rating}</span>",
                   "font": {"size": 11, "color": "#1e293b"}},
            number={"suffix": "% Buy", "font": {"size": 13, "color": needle_color}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1,
                         "tickvals": [0, 25, 50, 75, 100],
                         "ticktext": ["Sell", "Weak Sell", "Neutral", "Weak Buy", "Buy"],
                         "tickfont": {"size": 8}},
                "bar": {"color": needle_color, "thickness": 0.3},
                "bgcolor": "white",
                "borderwidth": 1,
                "bordercolor": "#e2e8f0",
                "steps": [
                    {"range": [0, 33],  "color": "rgba(239,68,68,0.12)"},
                    {"range": [33, 67], "color": "rgba(251,191,36,0.10)"},
                    {"range": [67, 100],"color": "rgba(34,197,94,0.12)"},
                ],
                "threshold": {
                    "line": {"color": "#475569", "width": 2},
                    "thickness": 0.75,
                    "value": 50,
                },
                "shape": "angular",
            },
        ))
        layout_dict = dict(CHART_LAYOUT)
        layout_dict.update(dict(
            height=190,
            margin=dict(l=20, r=20, t=50, b=10),
            annotations=[
                dict(x=0.17, y=-0.08, text=f"<b>🟢 Buy: {buy}</b>",
                     font=dict(size=8, color=C_GREEN), showarrow=False, xref="paper", yref="paper"),
                dict(x=0.50, y=-0.08, text=f"<b>⚫ Neutral: {neut}</b>",
                     font=dict(size=8, color="#64748b"), showarrow=False, xref="paper", yref="paper"),
                dict(x=0.83, y=-0.08, text=f"<b>🔴 Sell: {sell}</b>",
                     font=dict(size=8, color=C_RED), showarrow=False, xref="paper", yref="paper"),
            ],
        ))
        fig.update_layout(**layout_dict)
        return _fig_to_b64(fig, 210, 190)
    except Exception as exc:
        logger.warning("Technical riskometer chart failed: %s", exc)
        return ""


def _chart_rolling_boxplot(rolling) -> str:
    """Box plot distribution for 1Y, 2Y, 3Y, 5Y, 7Y rolling windows (side-by-side)."""
    traces = []
    colors = {"1Y": C_INDIGO, "2Y": C_VIOLET, "3Y": C_TEAL, "5Y": C_AMBER, "7Y": C_EMERALD}
    for window in ["1Y", "2Y", "3Y", "5Y", "7Y"]:
        r = (rolling or {}).get(window)
        if not r:
            continue
        mn  = _flt(getattr(r, "min_pct", None))
        med = _flt(getattr(r, "median_pct", None))
        mx  = _flt(getattr(r, "max_pct", None))
        avg = _flt(getattr(r, "mean_pct", None))
        std = _flt(getattr(r, "std_dev", 5.0)) or 5.0
        if med is None:
            continue
        # Approximate 25th (Q1) and 75th (Q3) percentiles using std dev if exact non-stored
        q1 = round(med - 0.6745 * std, 2)
        q3 = round(med + 0.6745 * std, 2)
        if mn is not None and q1 < mn:
            q1 = mn
        if mx is not None and q3 > mx:
            q3 = mx
        low_fence = round(mn, 2) if mn is not None else round(q1 - 1, 2)
        up_fence  = round(mx, 2) if mx is not None else round(q3 + 1, 2)
        traces.append(go.Box(
            name=f"{window}",
            x=[f"{window}"],
            q1=[q1], median=[round(med, 2)], q3=[q3],
            lowerfence=[low_fence],
            upperfence=[up_fence],
            mean=[round(avg, 2) if avg is not None else round(med, 2)],
            marker_color=colors.get(window, C_INDIGO),
            showlegend=False,
        ))
    if not traces:
        return ""
    fig = go.Figure(data=traces)
    fig.update_layout(**CHART_LAYOUT,
                      title_text="Rolling Return Distribution (Min / Q1 / Median / Q3 / Max)",
                      xaxis_title="Rolling Window",
                      yaxis_title="Return (%)",
                      boxmode="group", height=250)
    return _fig_to_b64(fig, 680, 250)


def _chart_drawdown(drawdown) -> str:
    """Historical drawdown from rolling peak — area chart."""
    if not drawdown:
        return ""
    pairs = [(getattr(d, "date", None), _flt(getattr(d, "drawdown", None)))
             for d in drawdown]
    pairs = [(d, v) for d, v in pairs if d and v is not None]
    if len(pairs) < 5:
        return ""
    dates, vals = zip(*pairs)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(dates), y=list(vals), mode="lines",
                             name="Drawdown %",
                             line=dict(color=C_RED, width=1),
                             fill="tozeroy", fillcolor="rgba(239,68,68,0.12)"))
    fig.update_layout(**CHART_LAYOUT,
                      title_text="Historical Drawdown from Peak (%)",
                      yaxis_title="Drawdown (%)", height=220)
    return _fig_to_b64(fig, 680, 220)


def _chart_yearly_risk(yearly_risk) -> str:
    """Dual-axis: bar for volatility, line for Sharpe ratio per year."""
    if not yearly_risk:
        return ""
    rows = [y for y in (yearly_risk or [])[-8:]
            if _flt(getattr(y, "volatility_pct", None)) is not None]
    if not rows:
        return ""
    years   = [str(getattr(y, "year", "")) for y in rows]
    vols    = [_flt(getattr(y, "volatility_pct", None)) or 0 for y in rows]
    sharpes = [_flt(getattr(y, "sharpe", None)) for y in rows]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=years, y=vols, name="Volatility (%)",
                         marker_color=C_INDIGO, opacity=0.7), secondary_y=False)
    if any(s is not None for s in sharpes):
        fig.add_trace(go.Scatter(x=years, y=sharpes, name="Sharpe Ratio",
                                 mode="lines+markers",
                                 line=dict(color=C_AMBER, width=2),
                                 marker=dict(size=5)), secondary_y=True)
    fig.update_layout(font=CHART_FONT, paper_bgcolor="white", plot_bgcolor="white",
                      margin=dict(l=35, r=35, t=35, b=35),
                      legend=dict(orientation="h", y=1.02, x=1, xanchor="right",
                                  font=dict(size=9)),
                      title_text="Yearly Volatility vs. Sharpe Ratio", height=240)
    fig.update_yaxes(title_text="Volatility (%)", gridcolor=C_BORDER, secondary_y=False)
    fig.update_yaxes(title_text="Sharpe Ratio", gridcolor=C_BORDER, secondary_y=True)
    return _fig_to_b64(fig, 680, 240)


def _chart_sector_alloc(sector_alloc) -> str:
    """Horizontal bar chart for sector weights."""
    if not sector_alloc:
        return ""
    items = sorted(
        [(getattr(s, "sector", ""), _flt(getattr(s, "weight_pct", 0)) or 0)
         for s in sector_alloc[:15]],
        key=lambda x: x[1], reverse=True
    )
    sectors = [i[0] for i in items]
    weights = [i[1] for i in items]
    palette = [C_INDIGO, C_VIOLET, C_TEAL, C_AMBER, "#f97316", C_GREEN,
               "#e879f9", "#06b6d4", "#84cc16", "#f43f5e",
               C_SLATE, "#0ea5e9", "#a855f7", "#10b981", "#eab308"]
    colors = palette[:len(sectors)]
    h = max(200, len(sectors) * 24 + 60)
    fig = go.Figure(go.Bar(x=weights, y=sectors, orientation="h",
                           marker_color=colors,
                           text=[f"{w:.1f}%" for w in weights],
                           textposition="outside", textfont=dict(size=9)))
    fig.update_layout(**CHART_LAYOUT, title_text="Sector Allocation (%)",
                      xaxis_title="Weight (%)", height=h)
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _fig_to_b64(fig, 680, h)


def _chart_asset_alloc(asset_alloc) -> str:
    """Donut chart for asset class allocation."""
    if not asset_alloc:
        return ""
    labels = [getattr(a, "label", "") for a in asset_alloc]
    vals   = [_flt(getattr(a, "weight_pct", 0)) or 0 for a in asset_alloc]
    if not any(v > 0 for v in vals):
        return ""
    cmap = {"Equity": C_INDIGO, "Debt": C_TEAL, "Cash": C_AMBER,
            "Other": C_SLATE, "Gold": "#f59e0b", "Real Estate": "#84cc16"}
    colors = [cmap.get(l, C_VIOLET) for l in labels]
    fig = go.Figure(go.Pie(labels=labels, values=vals, hole=0.55,
                           marker=dict(colors=colors, line=dict(color="white", width=2)),
                           textfont=dict(size=9), textinfo="label+percent"))
    fig.update_layout(font=CHART_FONT, paper_bgcolor="white",
                      margin=dict(l=10, r=10, t=30, b=10), height=240,
                      showlegend=True,
                      legend=dict(orientation="v", x=1, y=0.5, font=dict(size=9)),
                      title_text="Asset Allocation",
                      title_font=dict(size=10))
    return _fig_to_b64(fig, 380, 240)


def _chart_pillar_scores(score_data: dict) -> str:
    """Horizontal bar for each of the 6 model pillars."""
    pillars = ["Performance", "Risk", "Cost", "Composition", "Manager", "Debt Quality"]
    keys    = ["performance", "risk", "cost", "composition", "manager", "debt"]
    vals, colors = [], []
    for k in keys:
        p = score_data.get(k) or {}
        s = _flt(p.get("score"))
        vals.append(s if s is not None else 0)
        colors.append(
            C_GREEN  if s and s >= 75 else
            C_INDIGO if s and s >= 55 else
            C_AMBER  if s and s >= 40 else
            C_RED    if s is not None and s < 40 else C_SLATE
        )
    fig = go.Figure(go.Bar(x=vals, y=pillars, orientation="h",
                           marker_color=colors,
                           text=[f"{v:.0f}" if v else "N/A" for v in vals],
                           textposition="outside", textfont=dict(size=9)))
    fig.update_layout(**CHART_LAYOUT, title_text="Pillar Scores (out of 100)", height=220)
    fig.update_xaxes(range=[0, 115])
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _fig_to_b64(fig, 600, 220)


def _chart_score_gauge(score) -> str:
    """Gauge chart for the overall model score."""
    if score is None:
        return ""
    color = (C_GREEN if score >= 75 else C_INDIGO if score >= 55
             else C_AMBER if score >= 40 else C_RED)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={"x": [0, 1], "y": [0, 1]},
        number={"suffix": "/100", "font": {"size": 24, "color": color}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1,
                     "tickcolor": C_TEXT, "tickfont": {"size": 9}},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "white",
            "borderwidth": 1, "bordercolor": C_BORDER,
            "steps": [
                {"range": [0, 40],   "color": "rgba(239,68,68,0.10)"},
                {"range": [40, 55],  "color": "rgba(245,158,11,0.10)"},
                {"range": [55, 75],  "color": "rgba(99,102,241,0.10)"},
                {"range": [75, 100], "color": "rgba(34,197,94,0.10)"},
            ],
            "threshold": {
                "line": {"color": color, "width": 3},
                "thickness": 0.75, "value": score
            },
        },
        title={"text": "Overall Model Score", "font": {"size": 11, "color": C_TEXT}},
    ))
    fig.update_layout(font=CHART_FONT, paper_bgcolor="white",
                      margin=dict(l=20, r=20, t=20, b=20), height=220)
    return _fig_to_b64(fig, 320, 220)



# ── Technical Indicators ───────────────────────────────────────────────────────

def _compute_technical_indicators(nav_series) -> dict:
    """
    Compute technical indicators (Moving Averages + Oscillators) for Daily, Weekly, Monthly
    timeframes, matching the JS logic in detail.html renderTechnicalSection.
    Returns dict: {timeframe: {oscillators, moving_averages, osc_counts, ma_counts, sum_counts}}
    """
    try:
        import numpy as np
        import pandas as pd

        if nav_series is None or nav_series.empty or len(nav_series) < 30:
            return {}

        def _resample(series, freq):
            if freq == "daily":
                return series
            elif freq == "weekly":
                return series.resample("W").last().dropna()
            elif freq == "monthly":
                return series.resample("ME").last().dropna()
            return series

        def _sma(arr, n):
            """Simple Moving Average."""
            result = [None] * len(arr)
            for i in range(n - 1, len(arr)):
                result[i] = float(np.mean(arr[i - n + 1:i + 1]))
            return result

        def _ema(arr, n):
            """Exponential Moving Average."""
            result = [None] * len(arr)
            k = 2.0 / (n + 1)
            for i, v in enumerate(arr):
                if i == 0:
                    result[i] = v
                else:
                    prev = result[i - 1] if result[i - 1] is not None else v
                    result[i] = v * k + prev * (1 - k)
            return result

        def _rsi(arr, period=14):
            gains, losses = [], []
            for i in range(1, len(arr)):
                diff = arr[i] - arr[i - 1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            if len(gains) < period:
                return None
            avg_g = float(np.mean(gains[:period]))
            avg_l = float(np.mean(losses[:period]))
            for i in range(period, len(gains)):
                avg_g = (avg_g * (period - 1) + gains[i]) / period
                avg_l = (avg_l * (period - 1) + losses[i]) / period
            if avg_l == 0:
                return 100.0
            rs = avg_g / avg_l
            return round(100 - 100 / (1 + rs), 2)

        def _stoch_k(arr, period=14):
            if len(arr) < period:
                return None
            window = arr[-period:]
            lo, hi = min(window), max(window)
            if hi == lo:
                return 50.0
            return round((arr[-1] - lo) / (hi - lo) * 100, 2)

        def _macd_hist(arr, fast=12, slow=26, signal=9):
            if len(arr) < slow:
                return None
            e_fast = _ema(arr, fast)
            e_slow = _ema(arr, slow)
            macd_line = [
                (f - s) if f is not None and s is not None else None
                for f, s in zip(e_fast, e_slow)
            ]
            macd_valid = [v for v in macd_line if v is not None]
            if len(macd_valid) < signal:
                return None
            sig = _ema(macd_valid, signal)
            return round(macd_valid[-1] - sig[-1], 4) if sig[-1] is not None else None

        def _cci(arr, period=20):
            if len(arr) < period:
                return None
            window = arr[-period:]
            tp_mean = float(np.mean(window))
            md = float(np.mean([abs(p - tp_mean) for p in window])) or 1e-9
            return round((arr[-1] - tp_mean) / (0.015 * md), 2)

        def _momentum(arr, period=10):
            if len(arr) <= period:
                return None
            base = arr[-period - 1]
            if base == 0:
                return None
            return round((arr[-1] - base) / base * 100, 2)

        def _awesome_osc(arr):
            s5 = _sma(arr, 5)[-1]
            s34 = _sma(arr, 34)[-1]
            if s5 is None or s34 is None:
                return None
            return round(s5 - s34, 4)

        def _williams_r(arr, period=14):
            k = _stoch_k(arr, period)
            if k is None:
                return None
            return round(k - 100, 2)

        def _bull_bear(arr):
            e13 = _ema(arr, 13)[-1]
            if e13 is None:
                return None
            return round(arr[-1] - e13, 4)

        def _adx_approx(arr, period=14):
            if len(arr) < period:
                return None
            rets = [abs((arr[i] / arr[i - 1] - 1) * 100) for i in range(1, len(arr))]
            window_rets = rets[-period:]
            std = float(np.std(window_rets)) if len(window_rets) > 1 else 0
            return round(std * (252 ** 0.5), 2)

        def _action(val, buy_thresh, sell_thresh, lower_is_buy=False):
            if val is None:
                return "Neutral"
            if lower_is_buy:
                if val <= buy_thresh:
                    return "Buy"
                if val >= sell_thresh:
                    return "Sell"
            else:
                if val >= buy_thresh:
                    return "Buy"
                if val <= sell_thresh:
                    return "Sell"
            return "Neutral"

        def _get_counts(items):
            buy = sum(1 for i in items if i["action"] == "Buy")
            sell = sum(1 for i in items if i["action"] == "Sell")
            neu = sum(1 for i in items if i["action"] == "Neutral")
            total = buy + neu + sell or 1
            score = round(((buy - sell) / total) * 100)
            rating = "Neutral"
            if score >= 50:
                rating = "Strong Buy"
            elif score >= 15:
                rating = "Buy"
            elif score <= -50:
                rating = "Strong Sell"
            elif score <= -15:
                rating = "Sell"
            return {"buy": buy, "neutral": neu, "sell": sell,
                    "score": score, "rating": rating}

        result = {}
        for tf in ["daily", "weekly", "monthly"]:
            s = _resample(nav_series, tf)
            if len(s) < 30:
                continue
            arr = s.values.tolist()
            n = len(arr)
            cur = arr[-1]

            rsi_v   = _rsi(arr, 14)
            stoch_v = _stoch_k(arr, 14)
            cci_v   = _cci(arr, 20)
            macd_v  = _macd_hist(arr, 12, 26, 9)
            mom_v   = _momentum(arr, 10)
            ao_v    = _awesome_osc(arr)
            wr_v    = _williams_r(arr, 14)
            bbp_v   = _bull_bear(arr)
            adx_v   = _adx_approx(arr, 14)

            def _fmt(v):
                return f"{v:.2f}" if v is not None else "—"

            oscillators = [
                {"name": "RSI (14)",              "value": _fmt(rsi_v),   "action": _action(rsi_v, 50, 50)},
                {"name": "Stochastic %K (14)",    "value": _fmt(stoch_v), "action": _action(stoch_v, 20, 80, lower_is_buy=True)},
                {"name": "CCI (20)",              "value": _fmt(cci_v),   "action": _action(cci_v, 100, -100)},
                {"name": "MACD Histogram",        "value": _fmt(macd_v),  "action": _action(macd_v, 0, 0)},
                {"name": "Momentum (10)",         "value": _fmt(mom_v),   "action": _action(mom_v, 0, 0)},
                {"name": "Awesome Oscillator",    "value": _fmt(ao_v),    "action": _action(ao_v, 0, 0)},
                {"name": "Williams %R (14)",      "value": _fmt(wr_v),    "action": _action(wr_v, -80, -20, lower_is_buy=True)},
                {"name": "Bull Bear Power",       "value": _fmt(bbp_v),   "action": _action(bbp_v, 0, 0)},
                {"name": "ADX Approx (14)",       "value": _fmt(adx_v),   "action": _action(adx_v, 25, 15)},
            ]

            moving_averages = []
            for p in [10, 20, 50, 100, 200]:
                if n >= p:
                    sma_v = _sma(arr, p)[-1]
                    ema_v = _ema(arr, p)[-1]
                    if sma_v is not None:
                        moving_averages.append({
                            "name": f"SMA ({p})", "value": _fmt(sma_v),
                            "action": _action(cur - sma_v if sma_v else None, 0, 0),
                        })
                    if ema_v is not None:
                        moving_averages.append({
                            "name": f"EMA ({p})", "value": _fmt(ema_v),
                            "action": _action(cur - ema_v if ema_v else None, 0, 0),
                        })
            # VWMA approx (SMA 20) and Hull approx (EMA 9)
            vwma = _sma(arr, 20)[-1]
            hull = _ema(arr, 9)[-1]
            if vwma is not None:
                moving_averages.append({
                    "name": "VWMA (20)", "value": _fmt(vwma),
                    "action": _action(cur - vwma, 0, 0),
                })
            if hull is not None:
                moving_averages.append({
                    "name": "Hull MA (9)", "value": _fmt(hull),
                    "action": _action(cur - hull, 0, 0),
                })

            osc_counts = _get_counts(oscillators)
            ma_counts  = _get_counts(moving_averages)
            sum_counts = _get_counts(oscillators + moving_averages)

            result[tf] = {
                "oscillators":    oscillators,
                "moving_averages": moving_averages,
                "osc_counts":     osc_counts,
                "ma_counts":      ma_counts,
                "sum_counts":     sum_counts,
            }
        return result
    except Exception as exc:
        logger.warning("Technical indicators computation failed: %s", exc)
        return {}


# ── Commentary generators ─────────────────────────────────────────────────────

def _commentary_trailing(trailing, cat_snap) -> str:

    if not trailing:
        return "Trailing return data is not available for this fund."
    beat_bm = sum(1 for r in trailing
                  if _flt(getattr(r, "excess", None)) is not None
                  and (_flt(getattr(r, "excess", None)) or 0) > 0)
    total   = sum(1 for r in trailing if _flt(getattr(r, "excess", None)) is not None)
    tr_map  = {getattr(r, "period", ""): r for r in trailing}
    r3 = tr_map.get("3Y")
    parts = []
    if total > 0:
        if beat_bm == total:
            parts.append(
                f"The fund has demonstrated consistent benchmark outperformance, "
                f"beating its declared benchmark across all {total} measured trailing periods.")
        elif beat_bm > total // 2:
            parts.append(
                f"The fund has outperformed its benchmark in {beat_bm} of {total} trailing periods, "
                f"showing a tendency towards active alpha generation.")
        else:
            parts.append(
                f"The fund has trailed its benchmark in most measured periods "
                f"({total - beat_bm} of {total}), which may reflect sector positioning or "
                f"market-style headwinds.")
    if r3:
        cagr3 = _flt(getattr(r3, "cagr_pct", None))
        exc3  = _flt(getattr(r3, "excess", None))
        if cagr3 is not None:
            sign = "above" if exc3 and exc3 > 0 else "below"
            parts.append(
                f"The 3-year CAGR stands at {cagr3:.2f}%"
                + (f", {abs(exc3):.2f}% {sign} its benchmark." if exc3 is not None else "."))
    if cat_snap and r3:
        cat3  = _flt(cat_snap.avg_return_3y)
        cagr3 = _flt(getattr(r3, "cagr_pct", None))
        if cat3 and cagr3 is not None:
            diff = cagr3 - cat3
            vs = "outperforming" if diff > 0 else "underperforming"
            parts.append(
                f"Versus the sub-category average of {cat3:.2f}%, "
                f"the fund is {vs} peers by {abs(diff):.2f}% on a 3-year basis.")
    return " ".join(parts) or "Trailing return data is partially available."


def _commentary_risk(risk_3y, cat_snap) -> str:
    if not risk_3y:
        return "3-year risk metrics are not available for this fund."
    sharpe  = _flt(getattr(risk_3y, "sharpe", None))
    beta    = _flt(getattr(risk_3y, "beta", None))
    alpha   = _flt(getattr(risk_3y, "alpha", None))
    max_dd  = _flt(getattr(risk_3y, "max_drawdown", None))
    parts = []
    if sharpe is not None:
        cat_sh = _flt(getattr(cat_snap, "avg_sharpe", None)) if cat_snap else None
        if cat_sh and sharpe > cat_sh * 1.1:
            parts.append(
                f"With a Sharpe ratio of {sharpe:.2f} vs. a category average of {cat_sh:.2f}, "
                f"this fund delivers significantly better risk-adjusted returns than peers.")
        elif sharpe >= 0.8:
            parts.append(
                f"The Sharpe ratio of {sharpe:.2f} indicates solid risk-adjusted returns — "
                f"the fund adequately compensates investors for the volatility it carries.")
        elif sharpe >= 0.4:
            parts.append(
                f"The Sharpe ratio of {sharpe:.2f} is moderate, reflecting adequate but "
                f"not exceptional risk-adjusted performance.")
        else:
            parts.append(
                f"The Sharpe ratio of {sharpe:.2f} is low, suggesting returns have not "
                f"sufficiently rewarded investors for the risks taken.")
    if beta is not None:
        if beta > 1.1:
            parts.append(
                f"A beta of {beta:.2f} means the fund amplifies market movements — "
                f"larger gains in bull markets but steeper drawdowns in corrections.")
        elif beta < 0.85:
            parts.append(
                f"A beta of {beta:.2f} signals a defensive posture — typically falls less "
                f"than the market in downturns, though may lag in strong rallies.")
        else:
            parts.append(
                f"With a beta of {beta:.2f}, the fund broadly tracks market movements.")
    if max_dd is not None:
        parts.append(
            f"The maximum drawdown of {max_dd:.1f}% represents the worst peak-to-trough "
            f"decline investors must be prepared to weather during market stress.")
    if alpha is not None:
        if alpha > 1.5:
            parts.append(
                f"Jensen's Alpha of {alpha:.2f}% confirms the fund generates returns "
                f"meaningfully above what pure market exposure would explain.")
        elif alpha < -1.5:
            parts.append(
                f"A negative alpha of {alpha:.2f}% suggests the fund manager has not "
                f"added sufficient value beyond passive market exposure.")
    return " ".join(parts) or "Risk metrics are available in the tables above."


def _commentary_cost(meta, cat_snap) -> str:
    exp     = _flt(getattr(meta, "expense_ratio", None))
    cat_exp = _flt(getattr(cat_snap, "avg_expense_ratio", None)) if cat_snap else None
    turn    = _flt(getattr(meta, "portfolio_turnover", None))
    cat_t   = _flt(getattr(cat_snap, "avg_turnover", None)) if cat_snap else None
    parts = []
    if exp is not None:
        if cat_exp and exp > cat_exp * 1.15:
            parts.append(
                f"The expense ratio of {exp:.2f}% is above the category average "
                f"({cat_exp:.2f}%), acting as a persistent drag on net returns. "
                f"Over a 10-year horizon, a 0.5% extra cost can erode ~5% of corpus.")
        elif exp < 0.5:
            parts.append(
                f"The expense ratio of {exp:.2f}% is among the lowest in its class, "
                f"giving this fund a structural cost advantage over peers.")
        else:
            cmp = f" vs. category average {cat_exp:.2f}%." if cat_exp else "."
            parts.append(f"The expense ratio of {exp:.2f}%{cmp}")
    if turn is not None:
        if turn > 100:
            parts.append(
                f"Portfolio turnover of {turn:.0f}% is high — frequent trading elevates "
                f"transaction costs and can create tax inefficiency for investors.")
        elif turn < 20:
            parts.append(
                f"Low turnover of {turn:.0f}% signals a buy-and-hold philosophy — "
                f"minimal churn is beneficial for long-term compounding.")
        else:
            cmp2 = f" (category avg: {cat_t:.0f}%)." if cat_t else "."
            parts.append(f"Portfolio turnover of {turn:.0f}%{cmp2}")
    return " ".join(parts) or "Cost details are available in the table above."


def _commentary_portfolio(sector_alloc, top10_weight, total_count) -> str:
    parts = []
    if top10_weight is not None:
        if top10_weight > 60:
            parts.append(
                f"Top-10 holdings account for {top10_weight:.1f}% of AUM — a highly "
                f"concentrated approach where returns are driven by a handful of stocks.")
        elif top10_weight > 40:
            parts.append(
                f"Top-10 at {top10_weight:.1f}% indicates moderate concentration, "
                f"balancing conviction bets with diversification.")
        else:
            parts.append(
                f"Top-10 at {top10_weight:.1f}% indicates a well-spread portfolio "
                f"with low single-stock concentration risk.")
    if total_count:
        parts.append(f"Total portfolio positions: {total_count}.")
    if sector_alloc:
        top_s = sector_alloc[0]
        w = _flt(getattr(top_s, "weight_pct", 0)) or 0
        parts.append(
            f"Largest sector allocation: {getattr(top_s, 'sector', 'N/A')} ({w:.1f}%).")
    return " ".join(parts) or "Portfolio details are available in the tables above."


def _commentary_score(score_data: dict, cat_snap) -> str:
    score   = score_data.get("final_score")
    badge   = score_data.get("overall_badge", "")
    interp  = score_data.get("overall_interpretation", "")
    cat_avg = _flt(getattr(cat_snap, "avg_model_score", None)) if cat_snap else None
    parts = []
    if score is not None:
        tier = ("outstanding" if score >= 80 else "strong" if score >= 65 else
                "good" if score >= 50 else "fair" if score >= 35 else "weak")
        parts.append(
            f"The fund scores {score:.0f}/100, placing it in the '{badge}' tier ({tier}). "
            + (interp or ""))
        if cat_avg:
            diff = score - cat_avg
            vs = "above" if diff > 0 else "below"
            parts.append(
                f"This is {abs(diff):.1f} points {vs} the sub-category average "
                f"of {cat_avg:.0f}/100.")
    flags   = (score_data.get("red_flags") or {}).get("flags", [])
    penalty = (score_data.get("red_flags") or {}).get("total_penalty", 0)
    if flags:
        parts.append(
            f"Red flags applied: {len(flags)} item(s) deducted {penalty} penalty "
            f"points from the composite score.")
    return " ".join(parts) or "Detailed scorecard is available above."


def _suitability_text(meta, risk_3y) -> str:
    cat = str(getattr(meta, "scheme_category", "") or "").lower()
    if "small" in cat:
        return ("HIGH RISK | 7+ Year Horizon. Small-cap funds can deliver exceptional "
                "long-term returns but experience significant volatility and deep drawdowns "
                "during corrections. Not suitable for short-term goals.")
    elif "mid" in cat:
        return ("MODERATE-HIGH RISK | 5-7 Year Horizon. Mid-cap exposure provides growth "
                "potential with more volatility than large-caps. Suitable as a portfolio "
                "satellite alongside large-cap core holdings.")
    elif "large" in cat:
        return ("MODERATE RISK | 3-5 Year Horizon. Large-cap funds offer relatively stable "
                "equity exposure. Appropriate as a core equity holding for most investors.")
    elif "debt" in cat or "bond" in cat or "credit" in cat:
        return ("CONSERVATIVE | Review Duration & Credit Quality. Debt funds carry interest "
                "rate risk and credit risk. Review the portfolio's average maturity and "
                "credit ratings before investing.")
    elif "hybrid" in cat or "balanced" in cat:
        return ("MODERATE RISK | 3-5 Year Horizon. Balanced equity-debt mix suitable for "
                "investors transitioning from pure debt to equity exposure.")
    elif "index" in cat or "etf" in cat:
        return ("LOW COST | Market-Return Seeker. Index funds/ETFs are ideal for cost-conscious "
                "investors seeking market-matching returns. Low expense ratios eliminate "
                "manager risk.")
    else:
        return ("Review the fund's category, past volatility, and personal financial goals "
                "before investing. Consult a SEBI-registered investment advisor if needed.")


def _build_research_narratives(ctx: dict) -> dict:
    """
    Generate dynamic, metrics-driven institutional research commentary, key takeaways,
    section-by-section interpretations, and an analyst recommendation verdict.
    """
    scheme = ctx.get("scheme")
    meta = ctx.get("meta")
    cat_name = ctx.get("category_name", "Mutual Fund Category")
    bm_name = ctx.get("benchmark_name", "Benchmark")
    sd = ctx.get("score_data", {})
    risk3 = ctx.get("risk_3y") or ctx.get("risk_5y")
    rolling_1y = ctx.get("rolling_1y")
    rolling_3y = ctx.get("rolling_3y")
    rolling_5y = ctx.get("rolling_5y")
    trailing = ctx.get("trailing_returns", [])
    calendar = ctx.get("calendar_returns", [])
    crisis = ctx.get("crisis_periods", [])
    regimes = ctx.get("market_regimes", [])
    peers = ctx.get("peers_data", [])
    tech = ctx.get("tech_indicators", {})
    drawdown = ctx.get("drawdown")
    top_holdings = ctx.get("top_holdings", [])
    sector_alloc = ctx.get("sector_alloc", [])
    top10_wt = ctx.get("top10_weight")

    score = _flt(sd.get("final_score")) if sd and "final_score" in sd else _flt(sd.get("overall_score"), 50.0)
    if score is None:
        score = 50.0
    percentile = _flt(sd.get("rank_percentile"), 50.0) or 50.0

    # 1. Executive Verdict Determination
    if score >= 75:
        verdict_action = "STRONG BUY / OUTPERFORM"
        verdict_badge = "Strong Buy"
        verdict_color = "#059669"
        verdict_tagline = "Top-tier category performer demonstrating robust alpha generation, disciplined risk control, and superior rolling consistency."
        horizon = "3 to 5+ Years"
        investor_profile = "Growth & Aggressive investors seeking core long-term capital appreciation."
        strategy = "Systematic Investment Plan (SIP) or staggered Lumpsum deployment on market pullbacks."
    elif score >= 60:
        verdict_action = "BUY / ACCUMULATE"
        verdict_badge = "Buy"
        verdict_color = "#16a34a"
        verdict_tagline = "Solid core holding with consistent benchmark beating capability and healthy risk-adjusted return efficiency."
        horizon = "3+ Years"
        investor_profile = "Growth-oriented investors building long-term equity portfolio allocation."
        strategy = "Regular SIP allocation for long-term wealth compounding."
    elif score >= 45:
        verdict_action = "HOLD / NEUTRAL"
        verdict_badge = "Hold"
        verdict_color = "#d97706"
        verdict_tagline = "Balanced performance aligned with category averages. Suitable to hold for existing investors."
        horizon = "3+ Years"
        investor_profile = "Existing fund holders seeking category-aligned market performance."
        strategy = "Maintain current SIP position; evaluate higher-alpha alternatives for incremental capital deployment."
    else:
        verdict_action = "UNDERPERFORM / REBALANCE"
        verdict_badge = "Underperform"
        verdict_color = "#dc2626"
        verdict_tagline = "Lagging relative returns or elevated risk metrics vs peer group. Rebalancing review recommended."
        horizon = "1 to 2 Years Review"
        investor_profile = "Caution advised for prospective new investors."
        strategy = "Pause incremental SIP contributions and evaluate peer category leaders."

    # 2. Extract Key Performance Metrics
    cagr_1y = None; cagr_3y = None; cagr_5y = None; ex_bm_3y = None; ex_cat_3y = None
    for tr in trailing:
        p = getattr(tr, "period", "")
        if p == "1Y": cagr_1y = _flt(getattr(tr, "cagr_pct", None))
        elif p == "3Y":
            cagr_3y = _flt(getattr(tr, "cagr_pct", None))
            ex_bm_3y = _flt(getattr(tr, "excess_bm", None))
            ex_cat_3y = _flt(getattr(tr, "excess_cat", None))
        elif p == "5Y": cagr_5y = _flt(getattr(tr, "cagr_pct", None))

    pos_cal_years = sum(1 for cr in calendar if (getattr(cr, "fund_return", 0) or 0) > 0)
    total_cal_years = len(calendar)

    r3_win0 = _flt(getattr(rolling_3y, "win_rate_0", None)) if rolling_3y else None
    r3_win8 = _flt(getattr(rolling_3y, "win_rate_8", None)) if rolling_3y else None
    r3_min = _flt(getattr(rolling_3y, "min_pct", None)) if rolling_3y else None
    r3_max = _flt(getattr(rolling_3y, "max_pct", None)) if rolling_3y else None

    alpha_val = _flt(getattr(risk3, "alpha", None)) if risk3 else None
    beta_val = _flt(getattr(risk3, "beta", None)) if risk3 else None
    sharpe_val = _flt(getattr(risk3, "sharpe_ratio", None)) if risk3 else None
    vol_val = _flt(getattr(risk3, "std_dev", None)) if risk3 else None
    max_dd = _flt(getattr(drawdown, "max_drawdown_pct", None)) or (_flt(getattr(risk3, "max_drawdown", None)) if risk3 else None)

    daily_rating = tech.get("daily", {}).get("sum_counts", {}).get("rating", "Neutral")
    weekly_rating = tech.get("weekly", {}).get("sum_counts", {}).get("rating", "Neutral")
    monthly_rating = tech.get("monthly", {}).get("sum_counts", {}).get("rating", "Neutral")

    # Strengths & Monitorables
    strengths = []
    if cagr_3y is not None and cagr_3y >= 15:
        strengths.append(f"Delivered a strong 3-Year CAGR of {cagr_3y:.2f}%, outpacing long-term inflation and wealth creation hurdles.")
    if alpha_val is not None and alpha_val > 1.5:
        strengths.append(f"Generates positive annual Alpha (+{alpha_val:.2f}%), proving fund manager stock-selection efficacy.")
    if r3_win0 is not None and r3_win0 >= 90:
        strengths.append(f"Exceptional 3-Year Rolling Return Win Rate of {r3_win0:.1f}%, indicating near-zero historical capital loss risk across 3Y holding windows.")
    if sharpe_val is not None and sharpe_val > 1.0:
        strengths.append(f"Favorable Sharpe Ratio ({sharpe_val:.2f}) confirms superior risk-adjusted reward per unit of volatility.")
    if not strengths:
        strengths.append("Established track record with disciplined portfolio management.")
        strengths.append("Well-balanced sector and asset allocation profile.")

    concerns = []
    if vol_val is not None and vol_val > 18:
        concerns.append(f"Higher annualized volatility ({vol_val:.2f}%), requiring investors to tolerate short-term price fluctuations.")
    if alpha_val is not None and alpha_val < 0:
        concerns.append(f"Negative Alpha ({alpha_val:.2f}%), indicating lag against benchmark index on a risk-adjusted basis.")
    if max_dd is not None and abs(max_dd) > 25:
        concerns.append(f"Significant historical drawdown peak ({abs(max_dd):.1f}%), highlighting vulnerability during steep market corrections.")
    if not concerns:
        concerns.append("Performance remains vulnerable to broader macro-economic shifts and interest rate cycles.")
        concerns.append("Dependent on key fund manager execution and continuity.")

    cagr_3y_str = f"{cagr_3y:.2f}%" if cagr_3y is not None else "N/A"
    ex_bm_3y_str = f"{ex_bm_3y:+.2f}%" if ex_bm_3y is not None else "N/A"
    r3_win0_str = f"{r3_win0:.1f}%" if r3_win0 is not None else "N/A"
    r3_win8_str = f"{r3_win8:.1f}%" if r3_win8 is not None else "N/A"
    r3_min_str = f"{r3_min:.2f}%" if r3_min is not None else "N/A"
    r3_max_str = f"{r3_max:.2f}%" if r3_max is not None else "N/A"
    vol_val_str = f"{vol_val:.2f}%" if vol_val is not None else "N/A"
    sharpe_val_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "N/A"
    alpha_val_str = f"{alpha_val:+.2f}%" if alpha_val is not None else "N/A"
    beta_val_str = f"{beta_val:.2f}" if beta_val is not None else "N/A"

    return {
        "verdict_action": verdict_action,
        "verdict_badge": verdict_badge,
        "verdict_color": verdict_color,
        "verdict_tagline": verdict_tagline,
        "horizon": horizon,
        "investor_profile": investor_profile,
        "strategy": strategy,
        "strengths": strengths,
        "concerns": concerns,
        "scorecard_text": f"{scheme.scheme_name} achieves an overall quantitative score of {score:.1f}/100, placing in the top {max(1, 100 - int(percentile))}% percentile of its peer group. This proprietary score synthesizes four analytical pillars: Performance ({sd.get('performance_badge','—')}), Risk ({sd.get('risk_badge','—')}), Consistency ({sd.get('consistency_badge','—')}), and Cost ({sd.get('cost_badge','—')}).",
        "perf_text": f"Over the 3-year horizon, the fund delivered an annualized CAGR of {cagr_3y_str}" + (f" vs {bm_name}'s benchmark return, generating an excess alpha spread of {ex_bm_3y_str}." if ex_bm_3y is not None else ".") + f" Across {total_cal_years} calendar years evaluated, the fund achieved positive annual returns in {pos_cal_years} of {total_cal_years} years.",
        "rolling_text": f"Rolling returns eliminate point-to-point bias by evaluating every possible investment timeframe. For 3-year holding periods, the fund achieved a {r3_win0_str} win-rate for positive returns and a {r3_win8_str} win-rate for beating an 8% inflation/hurdle rate. Historical 3Y rolling returns ranged between {r3_min_str} (minimum) and {r3_max_str} (maximum).",
        "risk_text": f"The fund exhibits an annualized volatility (Standard Deviation) of {vol_val_str} and a Sharpe Ratio of {sharpe_val_str}. An Alpha of {alpha_val_str} demonstrates the portfolio manager's stock selection skill over market movements, while a Beta of {beta_val_str} measures systematic market sensitivity.",
        "portfolio_text": f"The portfolio holds {len(top_holdings)} key stocks, with top 10 holdings accounting for {top10_wt:.1f}% of total assets." if top10_wt else "The portfolio features a well-diversified allocation across market capitalization and sector exposures.",
        "peer_text": f"Compared against peer funds in {cat_name}, the scheme demonstrates competitive standing across Sharpe ratio, Alpha generation, and fee efficiency.",
        "tech_text": f"Technical analysis indicates multi-timeframe trend alignment: Daily signals reflect '{daily_rating}', Weekly signals indicate '{weekly_rating}', and Monthly signals show '{monthly_rating}'.",
    }


# ── Main context builder ──────────────────────────────────────────────────────

def build_report_context(request, scheme) -> dict:
    """Assembles the full context dict for the 10-page report template."""
    from apps.funds.runtime import get_runtime_snapshot
    from apps.analytics.scorer import score_fund, compute_category_rank
    from apps.funds.models import FundScreenerSnapshot, CategorySnapshot

    today   = date.today()
    runtime = get_runtime_snapshot(scheme)
    meta    = runtime.meta

    # ── Score ──────────────────────────────────────────────────────────
    score_data = {}
    try:
        result    = score_fund(runtime)
        rank_info = compute_category_rank(scheme, result.final_score)

        def _pj(p):
            return {
                "score": p.get("score"), "status": p.get("status"),
                "interpretation": p.get("interpretation"),
                "missing": p.get("missing"), "details": p.get("details", {}),
            }

        badge_dict = result.overall_badge if isinstance(result.overall_badge, dict) else {}
        badge_label = badge_dict.get("label", "") or str(result.overall_badge or "")

        score_data = {
            "final_score": result.final_score,
            "confidence": result.confidence,
            "overall_badge": badge_label,       # string: "Strong", "Good", etc.
            "overall_badge_color": badge_dict.get("color", ""),
            "overall_badge_emoji": badge_dict.get("emoji", ""),
            "overall_interpretation": result.overall_interpretation,
            "model_version": result.model_version,
            "nav_days": result.nav_days,
            "missing_pillars": result.missing_pillars,
            "provisional_pillars": result.provisional_pillars,
            "performance": _pj(result.performance),
            "risk": _pj(result.risk),
            "cost": _pj(result.cost),
            "composition": _pj(result.composition),
            "manager": _pj(result.manager),
            "debt": _pj(result.debt),
            "red_flags": result.red_flags,
            "rank": rank_info,
        }
    except Exception as exc:
        logger.warning("Score computation failed for report: %s", exc)

    # ── Category snapshot ───────────────────────────────────────────────
    cat_snap, cat_name = None, ""
    try:
        sub_cat = (
            FundScreenerSnapshot.objects
            .filter(scheme=scheme)
            .values_list("scheme_sub_category", flat=True).first()
        ) or scheme.scheme_category or ""
        cat_name = sub_cat
        if sub_cat:
            cat_snap = CategorySnapshot.objects.filter(
                scheme_sub_category__iexact=sub_cat
            ).first()
    except Exception:
        pass

    # Fetch DB models for metadata & risk fallbacks
    from apps.funds.models import SchemeMeta
    sm = SchemeMeta.objects.filter(scheme=scheme).first()
    snap = FundScreenerSnapshot.objects.filter(scheme=scheme).first()

    # Fallbacks for meta fields
    sip_min_val = _flt(getattr(meta, "sip_min", None)) or _flt(getattr(sm, "sip_min", None)) or _flt(getattr(snap, "sip_min", None))
    lump_min_val = _flt(getattr(meta, "lump_min", None)) or _flt(getattr(sm, "lump_min", None)) or _flt(getattr(snap, "lump_min", None))
    exit_load_val = getattr(meta, "exit_load", None) or getattr(sm, "exit_load", None) or "1% if redeemed within 365 days, Nil thereafter"
    lock_in_val = getattr(meta, "lock_in_period", None) or getattr(sm, "lock_in_period", None) or getattr(snap, "lock_in_days", None) or 0

    if meta:
        meta.sip_min = sip_min_val
        meta.min_sip = sip_min_val
        meta.lump_min = lump_min_val
        meta.min_lumpsum = lump_min_val
        meta.exit_load = exit_load_val
        meta.lock_in = lock_in_val
        # AUM and alpha fallbacks for peer comparison row
        if not _flt(getattr(meta, "aum", None)) and snap:
            meta.aum = _flt(getattr(snap, "aum_cr", None))
        if not _flt(getattr(meta, "alpha_3y", None)) and snap:
            meta.alpha_3y = _flt(getattr(snap, "alpha_3y", None))
        if not _flt(getattr(meta, "expense_ratio", None)) and snap:
            meta.expense_ratio = _flt(getattr(snap, "expense_ratio", None))

    # Gather runtime data
    trailing     = runtime.trailing_returns
    calendar     = runtime.calendar_returns
    rolling      = runtime.rolling_returns
    drawdown     = runtime.drawdown
    yearly_risk  = runtime.yearly_risk
    sector_alloc = runtime.sector_alloc
    asset_alloc  = runtime.asset_alloc

    # ── Risk metrics wrapper with fallback to snapshot ───────────────────────
    class _RiskWrapper:
        def __init__(self, runtime_risk, snap_obj, period="3Y"):
            self._r = runtime_risk
            self._s = snap_obj
            self._p = period

        def _val(self, r_attr, s_attr):
            v = _flt(getattr(self._r, r_attr, None)) if self._r else None
            if v is None and self._s:
                v = _flt(getattr(self._s, s_attr, None))
            return v

        @property
        def sharpe(self):
            return self._val("sharpe_ratio", "sharpe_ratio_5y" if self._p == "5Y" else "sharpe_ratio")

        @property
        def sharpe_ratio(self):
            return self.sharpe

        @property
        def volatility(self):
            v = _flt(getattr(self._r, "volatility", None)) or _flt(getattr(self._r, "std_dev_ann", None)) or _flt(getattr(self._r, "std_dev", None)) if self._r else None
            if v is None and self._s:
                v = _flt(getattr(self._s, "volatility_3y_pct" if self._p == "3Y" else "volatility_5y_pct", None)) or _flt(getattr(self._s, "volatility_3y", None))
            return v

        @property
        def std_dev(self):
            return self.volatility

        @property
        def volatility_pct(self):
            return self.volatility


        @property
        def sortino(self):
            return self._val("sortino_ratio", "sortino_ratio_5y" if self._p == "5Y" else "sortino_ratio")

        @property
        def sortino_ratio(self):
            return self.sortino

        @property
        def max_drawdown(self):
            return self._val("max_drawdown", "max_drawdown_5y" if self._p == "5Y" else "max_drawdown")

        @property
        def beta(self):
            return self._val("beta", "beta_5y" if self._p == "5Y" else "beta_3y")

        @property
        def alpha(self):
            return self._val("alpha_ann", "alpha_5y" if self._p == "5Y" else "alpha_3y")

        @property
        def alpha_ann(self):
            return self.alpha

        @property
        def r_squared(self):
            return self._val("r_squared", "r_squared_5y" if self._p == "5Y" else "r_squared_3y")

        @property
        def tracking_error(self):
            return self._val("tracking_error", "tracking_error_5y" if self._p == "5Y" else "tracking_error_3y")

        @property
        def info_ratio(self):
            return self._val("info_ratio", "info_ratio_5y" if self._p == "5Y" else "info_ratio_3y")

        @property
        def information_ratio(self):
            return self.info_ratio

        @property
        def upside_capture(self):
            return self._val("upside_capture", "upside_capture_3y")

        @property
        def downside_capture(self):
            return self._val("downside_capture", "downside_capture_3y")

        def __getattr__(self, name):
            if self._r:
                return getattr(self._r, name, None)
            return None

    risk_3y = _RiskWrapper(runtime.risk_3y, snap, "3Y")
    risk_5y = _RiskWrapper(runtime.risk_5y, snap, "5Y")

    # ── Charts ──────────────────────────────────────────────────────────
    charts = {
        "nav_growth":       _safe_chart(_chart_nav_growth, runtime.nav_series, runtime.benchmark_series),
        "trailing_returns": _safe_chart(_chart_trailing_returns, trailing, cat_snap),
        "calendar_returns": _safe_chart(_chart_calendar_returns, calendar, cat_snap),
        "rolling_ts":       _safe_chart(_chart_rolling_timeseries, runtime.nav_series, runtime.benchmark_series),
        "rolling_1y":       _safe_chart(_chart_rolling_timeseries_window, runtime.nav_series, runtime.benchmark_series, "1Y"),
        "rolling_3y":       _safe_chart(_chart_rolling_timeseries_window, runtime.nav_series, runtime.benchmark_series, "3Y"),
        "rolling_5y":       _safe_chart(_chart_rolling_timeseries_window, runtime.nav_series, runtime.benchmark_series, "5Y"),
        "rolling_box":      _safe_chart(_chart_rolling_boxplot, rolling),
        "quarterly_perf":   _safe_chart(_chart_quarterly_perf, runtime.quarterly_performance),
        "drawdown":         _safe_chart(_chart_drawdown, drawdown),
        "yearly_risk":      _safe_chart(_chart_yearly_risk, yearly_risk),
        "sector":           _safe_chart(_chart_sector_alloc, sector_alloc),
        "asset":            _safe_chart(_chart_asset_alloc, asset_alloc),
        "pillar_scores":    _safe_chart(_chart_pillar_scores, score_data) if score_data else "",
        "score_gauge":      _safe_chart(_chart_score_gauge, score_data.get("final_score")) if score_data else "",
    }


    # ── Commentary ────────────────────────────────────────────────────────
    commentary = {
        "trailing":    _commentary_trailing(trailing, cat_snap),
        "risk":        _commentary_risk(risk_3y, cat_snap),
        "cost":        _commentary_cost(meta, cat_snap),
        "portfolio":   _commentary_portfolio(sector_alloc, runtime.top10_weight,
                                              runtime.total_holdings_count),
        "score":       _commentary_score(score_data, cat_snap),
        "suitability": _suitability_text(meta, risk_3y),
    }

    # ── Performance KPIs ─────────────────────────────────────────────────
    tr_map = {getattr(r, "period", ""): r for r in (trailing or [])}

    def _r(period, attr):
        r = tr_map.get(period)
        return _flt(getattr(r, attr, None)) if r else None

    perf_kpis = [
        {"label": "1Y Return", "fund": _r("1Y", "cagr_pct"),
         "cat": _flt(getattr(cat_snap, "avg_return_1y", None)) if cat_snap else None,
         "period": "1Y"},
        {"label": "3Y CAGR",   "fund": _r("3Y", "cagr_pct"),
         "cat": _flt(getattr(cat_snap, "avg_return_3y", None)) if cat_snap else None,
         "period": "3Y"},
        {"label": "5Y CAGR",   "fund": _r("5Y", "cagr_pct"),
         "cat": _flt(getattr(cat_snap, "avg_return_5y", None)) if cat_snap else None,
         "period": "5Y"},
    ]

    # ── Enrich trailing returns ──────────────────────────────────────
    cat_return_map = {}
    if cat_snap:
        cat_return_map = {
            "1Y": _flt(getattr(cat_snap, "avg_return_1y", None)),
            "3Y": _flt(getattr(cat_snap, "avg_return_3y", None)),
            "5Y": _flt(getattr(cat_snap, "avg_return_5y", None)),
        }

    class _TR:
        def __init__(self, original, cat_avg):
            self._o = original
            cagr = _flt(getattr(original, "cagr_pct", None))
            self.excess_cat = (cagr - cat_avg) if (cagr is not None and cat_avg is not None) else None

        def __getattr__(self, name):
            return getattr(self._o, name)

    trailing_enriched = [
        _TR(r, cat_return_map.get(getattr(r, "period", "")))
        for r in (trailing or [])
    ]

    # ── Enrich calendar returns ──────────────────────────────────────
    class _CR:
        def __init__(self, original):
            self._o = original
            f = _flt(getattr(original, "return_pct", None))
            if f is None:
                f = _flt(getattr(original, "fund_return", None))
            b = _flt(getattr(original, "bm_return", None))
            self.fund_return = f
            self.bm_return = b
            self.excess = (f - b) if (f is not None and b is not None) else None

        def __getattr__(self, name):
            return getattr(self._o, name)

    calendar_enriched = [_CR(r) for r in (calendar or [])][-12:]

    # ── Enrich rolling returns with category stats ───────────────────
    cat_rolling = (cat_snap.rolling_returns_json or {}) if cat_snap else {}
    rolling_enriched = {}
    for window, r in (rolling or {}).items():
        c_stat = cat_rolling.get(window, {})
        c_avg    = _flt(c_stat.get("avg") or c_stat.get("mean"))
        c_median = _flt(c_stat.get("median"))
        c_min    = _flt(c_stat.get("min"))
        c_max    = _flt(c_stat.get("max"))
        class _RR:
            def __init__(self, orig, cat_avg_val, cat_min_val, cat_max_val, cat_median_val):
                self._o = orig
                self.cat_avg    = cat_avg_val
                self.cat_min    = cat_min_val
                self.cat_max    = cat_max_val
                self.cat_median = cat_median_val
            def __getattr__(self, name):
                return getattr(self._o, name)
        rolling_enriched[window] = _RR(r, c_avg, c_min, c_max, c_median)

    # ── Enrich yearly risk ────────────────────────────────────────────
    class _YR:
        def __init__(self, original):
            self._o = original
            self.return_pct = _flt(getattr(original, "fund_cagr", None)) or _flt(getattr(original, "return_pct", None))
            self.volatility_pct = _flt(getattr(original, "std_dev", None)) or _flt(getattr(original, "volatility_pct", None))

        def __getattr__(self, name):
            return getattr(self._o, name)

    yearly_risk_enriched = [_YR(y) for y in (yearly_risk or [])][-8:]

    # ── Enrich market regimes ─────────────────────────────────────────
    class _MR:
        def __init__(self, original):
            self._o = original
            cagr = _flt(getattr(original, "avg_cagr", None)) or _flt(getattr(original, "fund_return", None))
            self.fund_return = cagr
            cw = getattr(original, "covered_windows", 0)
            tm = getattr(original, "total_months", 0)
            self.windows_label = f"{cw} window{'s' if cw != 1 else ''} ({tm} mo)" if cw else getattr(original, "windows_label", "—")

        def __getattr__(self, name):
            return getattr(self._o, name)

    market_regimes_enriched = [_MR(r) for r in (runtime.market_regimes or [])]

    # ── Technical Indicators (Daily / Weekly / Monthly) ────────────────────────
    tech_indicators = {}
    try:
        tech_indicators = _compute_technical_indicators(runtime.nav_series)
        if tech_indicators:
            for tf_k, tf_lbl in [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]:
                if tf_k in tech_indicators:
                    tech_indicators[tf_k]["gauge_chart"] = _safe_chart(_chart_tech_riskometer, tech_indicators[tf_k], tf_lbl)
    except Exception as _ti_exc:
        logger.warning("Tech indicators skipped: %s", _ti_exc)

    # ── Peer comparison data ───────────────────────────────────────────────
    peers_data = []
    try:
        from apps.funds.peers import get_peer_matches
        peer_matches = get_peer_matches(scheme, max_peers=7)
        for match in peer_matches:
            ps = match.scheme
            ps_snap = FundScreenerSnapshot.objects.filter(scheme=ps).first()
            if not ps_snap:
                continue
            peers_data.append({
                "scheme_name":   ps.scheme_name,
                "fund_house":    ps.fund_house or "",
                "amfi_code":     ps.amfi_code,
                "return_1y":     _flt(getattr(ps_snap, "returns_1y_pct", None)),
                "return_3y":     _flt(getattr(ps_snap, "returns_3y_pct", None)) or _flt(getattr(ps_snap, "cagr_3y_pct", None)),
                "return_5y":     _flt(getattr(ps_snap, "returns_5y_pct", None)),
                "sharpe_ratio":  _flt(getattr(ps_snap, "sharpe_ratio", None)),
                "volatility":    _flt(getattr(ps_snap, "volatility_3y_pct", None)),
                "alpha":         _flt(getattr(ps_snap, "alpha_3y", None)),
                "expense_ratio": _flt(getattr(ps_snap, "expense_ratio", None)),
                "aum":           _flt(getattr(ps_snap, "aum_cr", None)),
                "match_reason":  match.match_reason or "",
            })
    except Exception as _peer_exc:
        logger.warning("Peers data skipped: %s", _peer_exc)

    ctx_out = {

        "scheme": scheme, "meta": meta,
        "report_date": today.strftime("%d %B %Y"),
        "nav_date": runtime.nav_date, "nav_latest": runtime.nav_latest,
        "trailing_returns": trailing_enriched,
        "calendar_returns": calendar_enriched,
        "rolling_returns": rolling_enriched,
        "rolling_1y": rolling_enriched.get("1Y"),
        "rolling_3y": rolling_enriched.get("3Y"),
        "rolling_5y": rolling_enriched.get("5Y"),
        "risk_3y": risk_3y, "risk_5y": risk_5y,
        "drawdown": drawdown,
        "yearly_risk": yearly_risk_enriched,
        "crisis_periods": runtime.crisis_periods,
        "market_regimes": market_regimes_enriched,
        "quarterly_performance": runtime.quarterly_performance,
        "top_holdings": (runtime.top_holdings or [])[:20],
        "sector_alloc": sector_alloc, "asset_alloc": asset_alloc,
        "top10_weight": runtime.top10_weight,
        "total_holdings_count": runtime.total_holdings_count,
        "holdings_month": runtime.holdings_month.strftime("%b %Y")
                          if runtime.holdings_month else None,
        "benchmark_name": runtime.benchmark_display_name or runtime.benchmark_name,
        "benchmark_ticker": runtime.benchmark_ticker,
        "benchmark_note": getattr(runtime, "benchmark_note", ""),
        "managers": runtime.managers,
        "manager_context": runtime.manager_context,
        "sources": runtime.sources,
        "category_snap": cat_snap, "category_name": cat_name,
        "score_data": score_data,
        "charts": charts, "commentary": commentary, "perf_kpis": perf_kpis,
        "badge_color": _badge_color(score_data.get("overall_badge", "")),
        "tech_indicators": tech_indicators,
        "peers_data": peers_data,
        "request": request,
    }
    ctx_out["narratives"] = _build_research_narratives(ctx_out)
    return ctx_out

    """
    Generate dynamic, metrics-driven institutional research commentary, key takeaways,
    section-by-section interpretations, and an analyst recommendation verdict.
    """
    scheme = ctx.get("scheme")
    meta = ctx.get("meta")
    cat_name = ctx.get("category_name", "Mutual Fund Category")
    bm_name = ctx.get("benchmark_name", "Benchmark")
    sd = ctx.get("score_data", {})
    risk3 = ctx.get("risk_3y") or ctx.get("risk_5y")
    rolling_1y = ctx.get("rolling_1y")
    rolling_3y = ctx.get("rolling_3y")
    rolling_5y = ctx.get("rolling_5y")
    trailing = ctx.get("trailing_returns", [])
    calendar = ctx.get("calendar_returns", [])
    crisis = ctx.get("crisis_periods", [])
    regimes = ctx.get("market_regimes", [])
    peers = ctx.get("peers_data", [])
    tech = ctx.get("tech_indicators", {})
    drawdown = ctx.get("drawdown")
    top_holdings = ctx.get("top_holdings", [])
    sector_alloc = ctx.get("sector_alloc", [])
    top10_wt = ctx.get("top10_weight")

    score = _flt(sd.get("final_score")) if sd and "final_score" in sd else _flt(sd.get("overall_score"), 50.0)
    if score is None:
        score = 50.0
    percentile = _flt(sd.get("rank_percentile"), 50.0) or 50.0

    # 1. Executive Verdict Determination
    if score >= 75:
        verdict_action = "STRONG BUY / OUTPERFORM"
        verdict_badge = "Strong Buy"
        verdict_color = "#059669"
        verdict_tagline = "Top-tier category performer demonstrating robust alpha generation, disciplined risk control, and superior rolling consistency."
        horizon = "3 to 5+ Years"
        investor_profile = "Growth & Aggressive investors seeking core long-term capital appreciation."
        strategy = "Systematic Investment Plan (SIP) or staggered Lumpsum deployment on market pullbacks."
    elif score >= 60:
        verdict_action = "BUY / ACCUMULATE"
        verdict_badge = "Buy"
        verdict_color = "#16a34a"
        verdict_tagline = "Solid core holding with consistent benchmark beating capability and healthy risk-adjusted return efficiency."
        horizon = "3+ Years"
        investor_profile = "Growth-oriented investors building long-term equity portfolio allocation."
        strategy = "Regular SIP allocation for long-term wealth compounding."
    elif score >= 45:
        verdict_action = "HOLD / NEUTRAL"
        verdict_badge = "Hold"
        verdict_color = "#d97706"
        verdict_tagline = "Balanced performance aligned with category averages. Suitable to hold for existing investors."
        horizon = "3+ Years"
        investor_profile = "Existing fund holders seeking category-aligned market performance."
        strategy = "Maintain current SIP position; evaluate higher-alpha alternatives for incremental capital deployment."
    else:
        verdict_action = "UNDERPERFORM / REBALANCE"
        verdict_badge = "Underperform"
        verdict_color = "#dc2626"
        verdict_tagline = "Lagging relative returns or elevated risk metrics vs peer group. Rebalancing review recommended."
        horizon = "1 to 2 Years Review"
        investor_profile = "Caution advised for prospective new investors."
        strategy = "Pause incremental SIP contributions and evaluate peer category leaders."

    # 2. Extract Key Performance Metrics
    cagr_1y = None; cagr_3y = None; cagr_5y = None; ex_bm_3y = None; ex_cat_3y = None
    for tr in trailing:
        p = getattr(tr, "period", "")
        if p == "1Y": cagr_1y = _flt(getattr(tr, "cagr_pct", None))
        elif p == "3Y":
            cagr_3y = _flt(getattr(tr, "cagr_pct", None))
            ex_bm_3y = _flt(getattr(tr, "excess_bm", None))
            ex_cat_3y = _flt(getattr(tr, "excess_cat", None))
        elif p == "5Y": cagr_5y = _flt(getattr(tr, "cagr_pct", None))

    pos_cal_years = sum(1 for cr in calendar if (getattr(cr, "fund_return", 0) or 0) > 0)
    total_cal_years = len(calendar)

    r3_win0 = _flt(getattr(rolling_3y, "win_rate_0", None)) if rolling_3y else None
    r3_win8 = _flt(getattr(rolling_3y, "win_rate_8", None)) if rolling_3y else None
    r3_min = _flt(getattr(rolling_3y, "min_pct", None)) if rolling_3y else None
    r3_max = _flt(getattr(rolling_3y, "max_pct", None)) if rolling_3y else None

    alpha_val = _flt(getattr(risk3, "alpha", None)) if risk3 else None
    beta_val = _flt(getattr(risk3, "beta", None)) if risk3 else None
    sharpe_val = _flt(getattr(risk3, "sharpe_ratio", None)) if risk3 else None
    vol_val = (_flt(getattr(risk3, "volatility", None)) or _flt(getattr(risk3, "std_dev", None))) if risk3 else None
    max_dd = _flt(getattr(drawdown, "max_drawdown_pct", None)) or (_flt(getattr(risk3, "max_drawdown", None)) if risk3 else None)


    daily_rating = tech.get("daily", {}).get("sum_counts", {}).get("rating", "Neutral")
    weekly_rating = tech.get("weekly", {}).get("sum_counts", {}).get("rating", "Neutral")
    monthly_rating = tech.get("monthly", {}).get("sum_counts", {}).get("rating", "Neutral")

    # Strengths & Monitorables
    strengths = []
    if cagr_3y is not None and cagr_3y >= 15:
        strengths.append(f"Delivered a strong 3-Year CAGR of {cagr_3y:.2f}%, outpacing long-term inflation and wealth creation hurdles.")
    if alpha_val is not None and alpha_val > 1.5:
        strengths.append(f"Generates positive annual Alpha (+{alpha_val:.2f}%), proving fund manager stock-selection efficacy.")
    if r3_win0 is not None and r3_win0 >= 90:
        strengths.append(f"Exceptional 3-Year Rolling Return Win Rate of {r3_win0:.1f}%, indicating near-zero historical capital loss risk across 3Y holding windows.")
    if sharpe_val is not None and sharpe_val > 1.0:
        strengths.append(f"Favorable Sharpe Ratio ({sharpe_val:.2f}) confirms superior risk-adjusted reward per unit of volatility.")
    if not strengths:
        strengths.append("Established track record with disciplined portfolio management.")
        strengths.append("Well-balanced sector and asset allocation profile.")

    concerns = []
    if vol_val is not None and vol_val > 18:
        concerns.append(f"Higher annualized volatility ({vol_val:.2f}%), requiring investors to tolerate short-term price fluctuations.")
    if alpha_val is not None and alpha_val < 0:
        concerns.append(f"Negative Alpha ({alpha_val:.2f}%), indicating lag against benchmark index on a risk-adjusted basis.")
    if max_dd is not None and abs(max_dd) > 25:
        concerns.append(f"Significant historical drawdown peak ({abs(max_dd):.1f}%), highlighting vulnerability during steep market corrections.")
    if not concerns:
        concerns.append("Performance remains vulnerable to broader macro-economic shifts and interest rate cycles.")
        concerns.append("Dependent on key fund manager execution and continuity.")

    cagr_3y_str = f"{cagr_3y:.2f}%" if cagr_3y is not None else "N/A"
    ex_bm_3y_str = f"{ex_bm_3y:+.2f}%" if ex_bm_3y is not None else "N/A"
    r3_win0_str = f"{r3_win0:.1f}%" if r3_win0 is not None else "N/A"
    r3_win8_str = f"{r3_win8:.1f}%" if r3_win8 is not None else "N/A"
    r3_min_str = f"{r3_min:.2f}%" if r3_min is not None else "N/A"
    r3_max_str = f"{r3_max:.2f}%" if r3_max is not None else "N/A"
    vol_val_str = f"{vol_val:.2f}%" if vol_val is not None else "N/A"
    sharpe_val_str = f"{sharpe_val:.2f}" if sharpe_val is not None else "N/A"
    alpha_val_str = f"{alpha_val:+.2f}%" if alpha_val is not None else "N/A"
    beta_val_str = f"{beta_val:.2f}" if beta_val is not None else "N/A"

    return {
        "verdict_action": verdict_action,
        "verdict_badge": verdict_badge,
        "verdict_color": verdict_color,
        "verdict_tagline": verdict_tagline,
        "horizon": horizon,
        "investor_profile": investor_profile,
        "strategy": strategy,
        "strengths": strengths,
        "concerns": concerns,
        "scorecard_text": f"{scheme.scheme_name} achieves an overall quantitative score of {score:.1f}/100, placing in the top {max(1, 100 - int(percentile))}% percentile of its peer group. This proprietary score synthesizes four analytical pillars: Performance ({sd.get('performance_badge','—')}), Risk ({sd.get('risk_badge','—')}), Consistency ({sd.get('consistency_badge','—')}), and Cost ({sd.get('cost_badge','—')}).",
        "perf_text": f"Over the 3-year horizon, the fund delivered an annualized CAGR of {cagr_3y_str}" + (f" vs {bm_name}'s benchmark return, generating an excess alpha spread of {ex_bm_3y_str}." if ex_bm_3y is not None else ".") + f" Across {total_cal_years} calendar years evaluated, the fund achieved positive annual returns in {pos_cal_years} of {total_cal_years} years.",
        "rolling_text": f"Rolling returns eliminate point-to-point bias by evaluating every possible investment timeframe. For 3-year holding periods, the fund achieved a {r3_win0_str} win-rate for positive returns and a {r3_win8_str} win-rate for beating an 8% inflation/hurdle rate. Historical 3Y rolling returns ranged between {r3_min_str} (minimum) and {r3_max_str} (maximum).",
        "risk_text": f"The fund exhibits an annualized volatility (Standard Deviation) of {vol_val_str} and a Sharpe Ratio of {sharpe_val_str}. An Alpha of {alpha_val_str} demonstrates the portfolio manager's stock selection skill over market movements, while a Beta of {beta_val_str} measures systematic market sensitivity.",
        "portfolio_text": f"The portfolio holds {len(top_holdings)} key stocks, with top 10 holdings accounting for {top10_wt:.1f}% of total assets." if top10_wt else "The portfolio features a well-diversified allocation across market capitalization and sector exposures.",
        "peer_text": f"Compared against peer funds in {cat_name}, the scheme demonstrates competitive standing across Sharpe ratio, Alpha generation, and fee efficiency.",
        "tech_text": f"Technical analysis indicates multi-timeframe trend alignment: Daily signals reflect '{daily_rating}', Weekly signals indicate '{weekly_rating}', and Monthly signals show '{monthly_rating}'.",
    }



# ── Main entry point ──────────────────────────────────────────────────────────


def _system_chrome_html_to_pdf(html_string: str) -> bytes:
    """
    Fallback PDF renderer using system-installed Google Chrome, Microsoft Edge,
    or Playwright's Chromium CLI.
    """
    import glob
    import os
    import shutil
    import subprocess
    import tempfile

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome-stable"),
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("msedge"),
    ]

    for ms_dir in [os.path.expanduser("~/.cache/ms-playwright"), os.path.expanduser("~/AppData/Local/ms-playwright")]:
        if os.path.exists(ms_dir):
            candidates.extend(glob.glob(os.path.join(ms_dir, "chromium-*", "chrome-linux", "chrome")))
            candidates.extend(glob.glob(os.path.join(ms_dir, "chromium-*", "chrome-win*", "chrome.exe")))
            candidates.extend(glob.glob(os.path.join(ms_dir, "chromium_headless_shell-*", "chrome-headless-shell-linux", "chrome-headless-shell")))
            candidates.extend(glob.glob(os.path.join(ms_dir, "chromium_headless_shell-*", "chrome-headless-shell-win*", "chrome-headless-shell.exe")))

    binary = next((c for c in candidates if c and os.path.exists(c)), None)
    if not binary:
        raise FileNotFoundError("No system Chrome or Edge binary found.")

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "report.html")
        pdf_path = os.path.join(tmpdir, "report.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_string)

        cmd = [
            binary,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path,
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode == 0 and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                data = f.read()
                if data:
                    return data
        raise RuntimeError(f"System Chrome CLI returncode={res.returncode}: {res.stderr.decode('utf-8', errors='ignore')}")


def _chrome_html_to_pdf(html_string: str) -> bytes:
    """
    Convert an HTML string to PDF bytes using a multi-tiered rendering pipeline:
    1. Playwright (Headless Chromium)
    2. System-installed Chrome / Edge CLI (--headless --print-to-pdf)
    3. xhtml2pdf (pisa) fallback
    """
    errors = []

    # 1. Playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-software-rasterizer",
                ]
            )
            page = browser.new_page()
            page.set_content(html_string, wait_until="load", timeout=20000)
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
            if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                return pdf_bytes
    except Exception as exc:
        logger.warning("Playwright PDF generation failed, attempting system Chrome/Edge CLI fallback: %s", exc)
        errors.append(f"Playwright: {exc}")

    # 2. System Chrome / Edge CLI
    try:
        pdf_bytes = _system_chrome_html_to_pdf(html_string)
        if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
            return pdf_bytes
    except Exception as exc:
        logger.warning("System Chrome/Edge CLI PDF generation failed, attempting xhtml2pdf fallback: %s", exc)
        errors.append(f"System Chrome CLI: {exc}")

    # 3. xhtml2pdf fallback
    try:
        import io
        from xhtml2pdf import pisa
        out = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=out)
        pdf_bytes = out.getvalue()
        if not pisa_status.err and pdf_bytes and pdf_bytes.startswith(b"%PDF"):
            return pdf_bytes
        errors.append(f"xhtml2pdf: err_code={pisa_status.err}")
    except Exception as exc:
        logger.warning("xhtml2pdf fallback failed: %s", exc)
        errors.append(f"xhtml2pdf: {exc}")

    raise RuntimeError("All PDF generation engines failed: " + " | ".join(errors))


def generate_fund_report_response(request, scheme) -> HttpResponse:
    """
    Generate a comprehensive multi-page PDF report for a mutual fund scheme.
    Uses Chrome headless --print-to-pdf with multi-tiered fallback.
    """
    try:
        ctx = build_report_context(request, scheme)
    except Exception as exc:
        logger.error("build_report_context failed for %s:\n%s", scheme.amfi_code, _tb.format_exc())
        raise

    try:
        html_string = render_to_string("funds/report_pdf.html", ctx)
    except Exception as exc:
        logger.error("Template render failed for %s:\n%s", scheme.amfi_code, _tb.format_exc())
        raise

    safe_name = scheme.scheme_name.replace(" ", "_").replace("/", "-")[:60]

    try:
        pdf_bytes = _chrome_html_to_pdf(html_string)
        response  = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="FundReport_{safe_name}.pdf"'
        logger.info("PDF report generated for %s (%d bytes)", scheme.amfi_code, len(pdf_bytes))
        return response
    except Exception as exc:
        logger.error("Chrome PDF generation failed for %s: %s\n%s",
                     scheme.amfi_code, exc, _tb.format_exc())
        # Absolute fallback: serve the HTML so user isn't left empty-handed
        html_response = HttpResponse(html_string, content_type="text/html; charset=utf-8")
        html_response["Content-Disposition"] = (
            f'inline; filename="FundReport_{safe_name}.html"'
        )
        html_response["X-Report-Fallback"] = "HTML"
        return html_response

