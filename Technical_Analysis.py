"""
pages/8_Technical_Analysis.py
Interactive candlestick chart + TradingView-style technical summary.

Features
────────
• Chart types   : Candlestick, OHLC, Line, Area, Heikin-Ashi
• Intervals     : 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1wk, 1mo
• Overlay indic.: SMA, EMA, WMA, HMA, DEMA, TEMA, VWMA,
                  Bollinger Bands, Keltner Channels, VWAP,
                  Ichimoku Cloud, Parabolic SAR
• Sub-panels    : Volume, MACD, RSI, Stochastic, CCI, ADX,
                  Williams %R, Awesome Oscillator, OBV, MFI
• S/R lines     : Typed price levels + free-draw via Plotly modebar
• Summary       : 3 gauge dials + 11 oscillator + 15 MA signals + Pivots
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.data.fetcher import get_stock_info, get_fast_info
from app.utils.formatters import fmt_currency
from app.compute.technicals import (
    compute_sma, compute_ema, compute_wma, compute_hma,
    compute_dema, compute_tema, compute_vwma,
    compute_bollinger_bands, compute_keltner_channels, compute_vwap,
    compute_ichimoku_full, compute_parabolic_sar, compute_heikin_ashi,
    compute_rsi, compute_macd, compute_stochastic, compute_cci,
    compute_adx, compute_williams_r, compute_awesome_oscillator,
    compute_momentum, compute_stoch_rsi, compute_obv, compute_mfi,
    compute_atr, compute_pivots,
    get_oscillator_signals, get_ma_signals, get_summary,
)
from app.utils.guides import info_btn, section_guide

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Technical Analysis · Equity Research",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main { background: #0f1117 !important; }
.block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
section[data-testid="stSidebar"] { background: #1a1d26 !important; }
.stTabs [data-baseweb="tab-list"]  { gap:.4rem; background:#1a1d26; border-radius:10px; padding:.3rem; }
.stTabs [data-baseweb="tab"]       { border-radius:8px!important; color:#94a3b8!important; font-weight:500!important; padding:.4rem .9rem!important; }
.stTabs [aria-selected="true"]     { background:#3b82f6!important; color:#fff!important; }
.stDataFrame { border-radius:10px !important; }
div[data-testid="metric-container"] { background:#1a1d26; border:1px solid #2d3748; border-radius:10px; padding:.6rem 1rem; }
.sr-chip { display:inline-block; background:#1e3a5f; color:#60a5fa; border-radius:20px;
           padding:2px 12px; margin:2px; font-size:0.78rem; font-weight:600; }
.gauge-label { text-align:center; font-size:0.85rem; color:#94a3b8; margin-top:4px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# GUARD — ticker must be selected
# ─────────────────────────────────────────────────────────────────────────────
ticker = st.session_state.get("ticker", "")
if not ticker:
    st.warning("⚠️ Please select a ticker from the **Home** page first.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
DARK_BG  = "#0f1117"
CARD_BG  = "#1a1d26"
BORDER   = "#2d3748"
TEXT     = "#e2e8f0"
GREEN    = "#26a69a"   # candlestick up (TradingView teal)
RED      = "#ef5350"   # candlestick down
BLUE     = "#3b82f6"
AMBER    = "#f59e0b"
PURPLE   = "#8b5cf6"

# Interval → (yfinance_interval, max_period_label)
INTERVALS = {
    "1m":  ("1m",  "5d"),
    "5m":  ("5m",  "60d"),
    "15m": ("15m", "60d"),
    "30m": ("30m", "60d"),
    "1h":  ("1h",  "2y"),
    "4h":  ("1h",  "2y"),   # resample from 1h
    "1D":  ("1d",  "max"),
    "1W":  ("1wk", "max"),
    "1M":  ("1mo", "max"),
}

PERIOD_OPTIONS = {
    "1m":  ["1d", "5d"],
    "5m":  ["5d", "1mo", "3mo"],
    "15m": ["5d", "1mo", "3mo"],
    "30m": ["5d", "1mo", "3mo"],
    "1h":  ["1mo", "3mo", "6mo", "1y", "2y"],
    "4h":  ["1mo", "3mo", "6mo", "1y", "2y"],
    "1D":  ["3mo", "6mo", "1y", "2y", "5y", "max"],
    "1W":  ["6mo", "1y", "2y", "5y", "max"],
    "1M":  ["1y", "2y", "5y", "10y", "max"],
}

MA_PALETTE = {
    9:   "#fbbf24", 10: "#3b82f6", 20: "#f97316",
    21:  "#8b5cf6", 30: "#ec4899", 50: "#06b6d4",
    55:  "#84cc16", 100:"#22c55e", 200:"#ef4444",
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load(ticker: str, period: str, yf_interval: str, resample_4h: bool) -> pd.DataFrame:
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=period, interval=yf_interval, auto_adjust=True)
    if df.empty:
        return df
    if resample_4h:
        df = df.resample("4h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        ).dropna(subset=["Close"])
    # Normalise column names
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# CHART HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _gauge(score: float, title: str, buy: int, neutral: int, sell: int) -> go.Figure:
    """Semi-circle indicator gauge matching TradingView style."""
    if score >= 0.5:   lbl, col = "Strong Buy",  "#22c55e" # brighter green
    elif score >= 0.1: lbl, col = "Buy",         "#4ade80" # lighter green
    elif score <= -0.5:lbl, col = "Strong Sell", "#ef4444" # bright red
    elif score <= -0.1:lbl, col = "Sell",        "#f87171" # light red
    else:              lbl, col = "Neutral",     "#94a3b8"

    fig = go.Figure(go.Indicator(
        mode="gauge",
        value=score,
        domain={"x": [0.05, 0.95], "y": [0.15, 0.85]},
        title={
            "text": (
                f"<span style='color:{TEXT};font-size:15px;font-weight:500;letter-spacing:0.5px'>{title}</span><br>"
                f"<span style='color:{col};font-size:22px;font-weight:700'>{lbl}</span>"
            ),
        },
        gauge={
            "axis":  {"range": [-1, 1], "visible": False},
            "bar":   {"color": TEXT, "thickness": 0.12},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [-1.0, -0.5], "color": "#7f1d1d"},
                {"range": [-0.5, -0.1], "color": "#b91c1c"},
                {"range": [-0.1,  0.1], "color": "#334155"},
                {"range": [ 0.1,  0.5], "color": "#166534"},
                {"range": [ 0.5,  1.0], "color": "#14532d"},
            ],
        },
    ))
    # Buy / Neutral / Sell counts below gauge
    fig.add_annotation(
        x=0.15, y=0.05, xref="paper", yref="paper",
        text=f"<b style='color:{RED};font-size:16px'>{sell}</b><br><span style='color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px'>Sell</span>",
        showarrow=False,
    )
    fig.add_annotation(
        x=0.5, y=0.05, xref="paper", yref="paper",
        text=f"<b style='color:#e2e8f0;font-size:16px'>{neutral}</b><br><span style='color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px'>Neutral</span>",
        showarrow=False,
    )
    fig.add_annotation(
        x=0.85, y=0.05, xref="paper", yref="paper",
        text=f"<b style='color:{GREEN};font-size:16px'>{buy}</b><br><span style='color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px'>Buy</span>",
        showarrow=False,
    )
    fig.update_layout(
        height=260, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=60, b=20), font={"color": TEXT},
    )
    return fig


def _signal_color(sig: str) -> str:
    if sig in ("Buy", "Strong Buy"):   return GREEN
    if sig in ("Sell", "Strong Sell"): return RED
    return "#6b7280"


def _styled_signal_table(rows: list[dict], currency: str) -> str:
    """Render oscillator/MA table as styled HTML."""
    html = (
        "<table style='width:100%;border-collapse:collapse;font-size:0.83rem'>"
        "<thead><tr>"
        f"<th style='text-align:left;padding:6px 8px;color:#94a3b8;border-bottom:1px solid {BORDER}'>Name</th>"
        f"<th style='text-align:right;padding:6px 8px;color:#94a3b8;border-bottom:1px solid {BORDER}'>Value</th>"
        f"<th style='text-align:right;padding:6px 8px;color:#94a3b8;border-bottom:1px solid {BORDER}'>Action</th>"
        "</tr></thead><tbody>"
    )
    for i, row in enumerate(rows):
        bg = CARD_BG if i % 2 == 0 else "#151821"
        sig = row.get("signal", "Neutral")
        sc  = _signal_color(sig)
        val = row.get("value")
        val_str = f"{val:,.2f}" if val is not None and not (isinstance(val, float) and np.isnan(val)) else "—"
        html += (
            f"<tr style='background:{bg}'>"
            f"<td style='padding:5px 8px;color:{TEXT}'>{row['name']}</td>"
            f"<td style='padding:5px 8px;text-align:right;color:#94a3b8'>{val_str}</td>"
            f"<td style='padding:5px 8px;text-align:right;color:{sc};font-weight:600'>{sig}</td>"
            "</tr>"
        )
    html += "</tbody></table>"
    return html


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
info  = get_stock_info(ticker)
fast  = get_fast_info(ticker)
name  = info.get("longName") or info.get("shortName") or ticker
ccy   = info.get("currency") or fast.get("currency") or "USD"
price = info.get("currentPrice") or info.get("regularMarketPrice") or fast.get("current_price") or 0
chg   = info.get("regularMarketChangePercent") or 0
high52 = info.get("fiftyTwoWeekHigh") or 0
low52  = info.get("fiftyTwoWeekLow") or 0

chg_col = "#22c55e" if chg >= 0 else "#ef4444"
chg_arrow = "▲" if chg >= 0 else "▼"

st.markdown(
    f"<h2 style='margin:0;font-size:1.5rem;color:{TEXT}'>{name} "
    f"<span style='color:#94a3b8;font-size:1rem;font-weight:400'>({ticker})</span>"
    f"&nbsp;&nbsp;<span style='color:{TEXT}'>{fmt_currency(price,ccy)}</span>"
    f"&nbsp;<span style='color:{chg_col};font-size:1rem'>{chg_arrow} {abs(chg):.2f}%</span></h2>"
    f"<p style='color:#94a3b8;font-size:0.82rem;margin:2px 0 12px'>52W Range: "
    f"{fmt_currency(low52,ccy)} – {fmt_currency(high52,ccy)}</p>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# CHART CONTROLS  (inline, above chart)
# ─────────────────────────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2.2, 2.5, 2.5, 3])

with ctrl1:
    lbl_col1, lbl_col2 = st.columns([5, 1])
    lbl_col1.markdown("**Chart Type**")
    with lbl_col2:
        info_btn("tech_chart_type")
    chart_type = st.radio(
        "Chart type", ["Candle", "OHLC", "HA", "Line", "Area"],
        horizontal=True, label_visibility="collapsed", key="ta_chart_type",
    )
with ctrl2:
    lbl_col1, lbl_col2 = st.columns([5, 1])
    lbl_col1.markdown("**Interval**")
    with lbl_col2:
        info_btn("tech_chart_interval")
    interval_key = st.radio(
        "Interval", ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W", "1M"],
        horizontal=True, label_visibility="collapsed", key="ta_interval",
        index=6,
    )
with ctrl3:
    st.markdown("**Period**")
    period_opts = PERIOD_OPTIONS.get(interval_key, ["1y"])
    default_period = "1y" if "1y" in period_opts else period_opts[-1]
    period_key = st.selectbox(
        "Period", period_opts,
        index=period_opts.index(default_period) if default_period in period_opts else 0,
        label_visibility="collapsed", key="ta_period",
    )
with ctrl4:
    intraday_intervals = ["1m", "5m", "15m", "30m", "1h", "4h"]
    if interval_key in ["1m", "5m", "15m", "30m"]:
        st.caption("⚠️ Sub-hourly data: limited to last 60 days (yfinance constraint)")
    elif interval_key in ["1h", "4h"]:
        st.caption("ℹ️ Hourly/4H data: up to 730 days. VWAP resets daily.")
    else:
        st.caption(f"📅 Daily / Weekly / Monthly — full history available")

# ── Load OHLCV ───────────────────────────────────────────────────────────────
yf_interval = INTERVALS[interval_key][0]
resample_4h = (interval_key == "4h")

with st.spinner("Loading chart data…"):
    df = _load(ticker, period_key, yf_interval, resample_4h)

if df is None or df.empty:
    st.error("⚠️ No price data available for this ticker/interval/period combination.")
    st.stop()

# Require at least 50 bars for most indicators
if len(df) < 10:
    st.warning(f"Only {len(df)} bars returned — try a longer period or different interval.")

# ─────────────────────────────────────────────────────────────────────────────
# OVERLAY INDICATOR CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("📈 Overlay Indicators", expanded=False):
    ov1, ov2, ov3, ov4 = st.columns(4)

    with ov1:
        st.markdown("**Moving Averages**")
        info_btn("tech_moving_averages")
        show_sma  = st.checkbox("SMA",  value=True,  key="ov_sma")
        sma_periods = st.multiselect("SMA periods", [10,20,50,100,200], default=[20,50,200], key="sma_p") if show_sma else []
        show_ema  = st.checkbox("EMA",  value=False, key="ov_ema")
        ema_periods = st.multiselect("EMA periods", [9,21,50,100,200], default=[9,21], key="ema_p") if show_ema else []
        show_wma  = st.checkbox("WMA",  value=False, key="ov_wma")
        wma_period = st.number_input("WMA period", 2, 500, 20, key="wma_p") if show_wma else None
        show_hma  = st.checkbox("HMA",  value=False, key="ov_hma")
        hma_period = st.number_input("HMA period", 2, 500, 9,  key="hma_p") if show_hma else None
        show_dema = st.checkbox("DEMA", value=False, key="ov_dema")
        dema_period= st.number_input("DEMA period",2,500,20, key="dema_p") if show_dema else None
        show_tema = st.checkbox("TEMA", value=False, key="ov_tema")
        tema_period= st.number_input("TEMA period",2,500,20, key="tema_p") if show_tema else None
        show_vwma = st.checkbox("VWMA", value=False, key="ov_vwma")
        vwma_period= st.number_input("VWMA period",2,500,20, key="vwma_p") if show_vwma else None

    with ov2:
        st.markdown("**Bands & Channels**")
        show_bb = st.checkbox("Bollinger Bands", value=True, key="ov_bb")
        info_btn("tech_bollinger_bands")
        if show_bb:
            bb_period  = st.number_input("BB Period",  2, 500, 20,  key="bb_per")
            bb_std     = st.number_input("BB Std Dev", 0.5, 5.0, 2.0, step=0.5, key="bb_std")
        else:
            bb_period, bb_std = 20, 2.0
        show_kc = st.checkbox("Keltner Channels", value=False, key="ov_kc")
        info_btn("tech_keltner_channels")
        if show_kc:
            kc_ema = st.number_input("KC EMA period", 2, 500, 20,  key="kc_ema")
            kc_atr = st.number_input("KC ATR period", 2, 500, 10,  key="kc_atr")
            kc_mult= st.number_input("KC Multiplier", 0.5, 5.0, 2.0, step=0.5, key="kc_mul")
        else:
            kc_ema, kc_atr, kc_mult = 20, 10, 2.0

    with ov3:
        st.markdown("**Other Overlays**")
        # VWAP only available for intraday
        vwap_ok = interval_key in intraday_intervals
        show_vwap = st.checkbox("VWAP", value=vwap_ok, disabled=not vwap_ok, key="ov_vwap")
        info_btn("tech_vwap")
        if not vwap_ok:
            st.caption("_VWAP: intraday only_")
        show_ichimoku = st.checkbox("Ichimoku Cloud", value=False, key="ov_ichi")
        info_btn("tech_ichimoku")
        if show_ichimoku:
            ichi_t = st.number_input("Tenkan",   2, 100, 9,  key="ichi_t")
            ichi_k = st.number_input("Kijun",    2, 100, 26, key="ichi_k")
            ichi_s = st.number_input("Senkou B", 2, 200, 52, key="ichi_s")
        else:
            ichi_t, ichi_k, ichi_s = 9, 26, 52
        show_psar = st.checkbox("Parabolic SAR", value=False, key="ov_psar")
        info_btn("tech_psar")
        if show_psar:
            psar_af  = st.number_input("PSAR AF Start", 0.01, 0.2, 0.02, step=0.01, key="psar_af")
            psar_max = st.number_input("PSAR AF Max",   0.1,  1.0, 0.20, step=0.05, key="psar_mx")
        else:
            psar_af, psar_max = 0.02, 0.2

    with ov4:
        st.markdown("**Chart Extras**")
        show_volume = st.checkbox("Volume (sub-panel)", value=True, key="ov_vol")
        show_hl52   = st.checkbox("52-Week H/L lines",  value=False, key="ov_52hl")
        log_scale   = st.checkbox("Log scale (Y-axis)",  value=False, key="ov_log")

# ─────────────────────────────────────────────────────────────────────────────
# SUB-PANEL INDICATOR CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("📉 Sub-Panel Indicator", expanded=False):
    sp1, sp2 = st.columns([1, 2])
    with sp1:
        sub_ind = st.radio("Select indicator", [
            "None", "MACD", "RSI", "Stochastic",
            "CCI", "ADX", "Williams %R",
            "Awesome Oscillator", "OBV", "MFI",
        ], key="sub_indicator")
    with sp2:
        st.markdown("**Parameters**")
        psp1, psp2, psp3 = st.columns(3)
        with psp1:
            macd_fast   = st.number_input("MACD Fast",   2, 200, 12,  key="m_fast")
            rsi_period  = st.number_input("RSI Period",  2, 100, 14,  key="r_per")
            stoch_k     = st.number_input("Stoch K",     2, 100, 14,  key="stoch_k")
            cci_period  = st.number_input("CCI Period",  2, 200, 20,  key="c_per")
        with psp2:
            macd_slow   = st.number_input("MACD Slow",   2, 200, 26,  key="m_slow")
            stoch_smooth= st.number_input("Stoch Smooth",1, 10,  3,   key="stoch_sm")
            adx_period  = st.number_input("ADX Period",  2, 100, 14,  key="a_per")
            wr_period   = st.number_input("Williams %R", 2, 100, 14,  key="wr_per")
        with psp3:
            macd_signal = st.number_input("MACD Signal", 2, 100, 9,   key="m_sig")
            stoch_d     = st.number_input("Stoch D",     1, 10,  3,   key="stoch_d")
            mfi_period  = st.number_input("MFI Period",  2, 100, 14,  key="mfi_p")

# ─────────────────────────────────────────────────────────────────────────────
# SUPPORT / RESISTANCE LINES
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("📏 Support & Resistance Lines", expanded=False):
    if "sr_levels" not in st.session_state:
        st.session_state.sr_levels = []

    sr_col1, sr_col2, sr_col3 = st.columns([2, 1, 1])
    with sr_col1:
        sr_input = st.text_input(
            "Price level (press Add)", placeholder="e.g. 185.50",
            key="sr_input", label_visibility="collapsed",
        )
    with sr_col2:
        if st.button("➕ Add Level", key="sr_add"):
            try:
                lvl = float(sr_input.replace(",", ""))
                if lvl > 0 and lvl not in st.session_state.sr_levels:
                    st.session_state.sr_levels.append(lvl)
                    st.rerun()
            except ValueError:
                st.error("Enter a valid number.")
    with sr_col3:
        if st.button("🗑 Clear All", key="sr_clear"):
            st.session_state.sr_levels = []
            st.rerun()

    if st.session_state.sr_levels:
        chips = "".join(
            f"<span class='sr-chip'>{lvl:,.2f}</span>"
            for lvl in sorted(st.session_state.sr_levels)
        )
        st.markdown(f"Active levels: {chips}", unsafe_allow_html=True)
    st.caption("💡 You can also draw lines directly on the chart using the toolbar (pencil icon).")

# ─────────────────────────────────────────────────────────────────────────────
# BUILD PLOTLY CHART
# ─────────────────────────────────────────────────────────────────────────────

# Determine subplot layout
has_sub   = (sub_ind != "None") and len(df) >= 10
has_vol   = show_volume and "Volume" in df.columns and df["Volume"].sum() > 0
n_rows    = 1 + (1 if has_vol else 0) + (1 if has_sub else 0)
row_map   = {"price": 1}
r_heights = [0.65]
row_titles = [""]

if has_vol:
    row_map["volume"] = 2
    r_heights.append(0.15)
    row_titles.append("")

if has_sub:
    row_map["indicator"] = len(row_map) + 1
    r_heights.append(0.20)
    row_titles.append("")

# Normalise heights
total = sum(r_heights); r_heights = [h/total for h in r_heights]

fig = make_subplots(
    rows=n_rows, cols=1,
    shared_xaxes=True,
    row_heights=r_heights,
    vertical_spacing=0.015,
    specs=[[{"type": "xy"}] for _ in range(n_rows)],
)

# ── Prepare OHLCV data ──────────────────────────────────────────────────────
O, H, L, C, V = df["Open"], df["High"], df["Low"], df["Close"], df["Volume"]

# Apply Heikin-Ashi transform if selected
if chart_type == "HA":
    O, H, L, C = compute_heikin_ashi(O, H, L, C)

up_col   = GREEN
down_col = RED

# ── Price trace ─────────────────────────────────────────────────────────────
if chart_type in ("Candle", "HA"):
    fig.add_trace(go.Candlestick(
        x=df.index, open=O, high=H, low=L, close=C,
        increasing_line_color=up_col,   increasing_fillcolor=up_col,
        decreasing_line_color=down_col, decreasing_fillcolor=down_col,
        name="Price", showlegend=False, line=dict(width=1),
    ), row=1, col=1)
elif chart_type == "OHLC":
    fig.add_trace(go.Ohlc(
        x=df.index, open=O, high=H, low=L, close=C,
        increasing_line_color=up_col, decreasing_line_color=down_col,
        name="Price", showlegend=False,
    ), row=1, col=1)
elif chart_type == "Line":
    fig.add_trace(go.Scatter(
        x=df.index, y=C, mode="lines",
        line=dict(color=BLUE, width=1.5),
        name="Close", showlegend=False,
    ), row=1, col=1)
elif chart_type == "Area":
    fig.add_trace(go.Scatter(
        x=df.index, y=C, mode="lines", fill="tozeroy",
        fillcolor="rgba(59,130,246,0.12)",
        line=dict(color=BLUE, width=1.5),
        name="Close", showlegend=False,
    ), row=1, col=1)

# ── SMA overlays ────────────────────────────────────────────────────────────
if show_sma:
    for p in sma_periods:
        s = compute_sma(df["Close"], p)
        col = MA_PALETTE.get(p, "#94a3b8")
        fig.add_trace(go.Scatter(
            x=df.index, y=s, mode="lines",
            line=dict(color=col, width=1.2),
            name=f"SMA {p}",
        ), row=1, col=1)

# ── EMA overlays ────────────────────────────────────────────────────────────
if show_ema:
    for p in ema_periods:
        e = compute_ema(df["Close"], p)
        col = MA_PALETTE.get(p, "#f59e0b")
        fig.add_trace(go.Scatter(
            x=df.index, y=e, mode="lines",
            line=dict(color=col, width=1.2, dash="dot"),
            name=f"EMA {p}",
        ), row=1, col=1)

# ── WMA, HMA, DEMA, TEMA, VWMA ──────────────────────────────────────────────
if show_wma and wma_period:
    s = compute_wma(df["Close"], int(wma_period))
    fig.add_trace(go.Scatter(x=df.index, y=s, mode="lines",
        line=dict(color="#a78bfa", width=1.2), name=f"WMA {int(wma_period)}"), row=1, col=1)

if show_hma and hma_period:
    s = compute_hma(df["Close"], int(hma_period))
    fig.add_trace(go.Scatter(x=df.index, y=s, mode="lines",
        line=dict(color="#f472b6", width=1.2), name=f"HMA {int(hma_period)}"), row=1, col=1)

if show_dema and dema_period:
    s = compute_dema(df["Close"], int(dema_period))
    fig.add_trace(go.Scatter(x=df.index, y=s, mode="lines",
        line=dict(color="#34d399", width=1.2), name=f"DEMA {int(dema_period)}"), row=1, col=1)

if show_tema and tema_period:
    s = compute_tema(df["Close"], int(tema_period))
    fig.add_trace(go.Scatter(x=df.index, y=s, mode="lines",
        line=dict(color="#fb923c", width=1.2, dash="dashdot"), name=f"TEMA {int(tema_period)}"), row=1, col=1)

if show_vwma and vwma_period:
    s = compute_vwma(df["Close"], df["Volume"], int(vwma_period))
    fig.add_trace(go.Scatter(x=df.index, y=s, mode="lines",
        line=dict(color="#67e8f9", width=1.2), name=f"VWMA {int(vwma_period)}"), row=1, col=1)

# ── Bollinger Bands ──────────────────────────────────────────────────────────
if show_bb:
    bb_up, bb_mid, bb_lo = compute_bollinger_bands(df["Close"], int(bb_period), bb_std)
    fig.add_trace(go.Scatter(x=df.index, y=bb_up, mode="lines",
        line=dict(color="rgba(59,130,246,0.7)", width=1), name="BB Upper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=bb_mid, mode="lines",
        line=dict(color="rgba(59,130,246,0.4)", width=1, dash="dot"), name="BB Mid"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=bb_lo, mode="lines", fill="tonexty",
        fillcolor="rgba(59,130,246,0.06)",
        line=dict(color="rgba(59,130,246,0.7)", width=1), name="BB Lower"), row=1, col=1)

# ── Keltner Channels ─────────────────────────────────────────────────────────
if show_kc:
    kc_up, kc_mid, kc_lo = compute_keltner_channels(
        df["High"], df["Low"], df["Close"], int(kc_ema), int(kc_atr), kc_mult)
    fig.add_trace(go.Scatter(x=df.index, y=kc_up, mode="lines",
        line=dict(color="rgba(245,158,11,0.6)", width=1), name="KC Upper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=kc_mid, mode="lines",
        line=dict(color="rgba(245,158,11,0.4)", width=1, dash="dot"), name="KC Mid"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=kc_lo, mode="lines", fill="tonexty",
        fillcolor="rgba(245,158,11,0.05)",
        line=dict(color="rgba(245,158,11,0.6)", width=1), name="KC Lower"), row=1, col=1)

# ── VWAP ─────────────────────────────────────────────────────────────────────
if show_vwap and vwap_ok:
    vwap_s = compute_vwap(df["High"], df["Low"], df["Close"], df["Volume"])
    fig.add_trace(go.Scatter(x=df.index, y=vwap_s, mode="lines",
        line=dict(color="#e879f9", width=1.5), name="VWAP"), row=1, col=1)

# ── Ichimoku Cloud ────────────────────────────────────────────────────────────
if show_ichimoku:
    ichi = compute_ichimoku_full(df["High"], df["Low"], df["Close"],
                                  int(ichi_t), int(ichi_k), int(ichi_s))
    fig.add_trace(go.Scatter(x=df.index, y=ichi["tenkan"], mode="lines",
        line=dict(color="#f87171", width=1.2), name="Tenkan"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ichi["kijun"], mode="lines",
        line=dict(color="#60a5fa", width=1.2), name="Kijun"), row=1, col=1)
    # Cloud fill (Senkou A & B)
    fig.add_trace(go.Scatter(x=df.index, y=ichi["senkou_a"], mode="lines",
        line=dict(color="rgba(52,211,153,0.4)", width=0.5), name="Senkou A"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ichi["senkou_b"], mode="lines",
        fill="tonexty", fillcolor="rgba(52,211,153,0.06)",
        line=dict(color="rgba(251,113,133,0.4)", width=0.5), name="Senkou B"), row=1, col=1)

# ── Parabolic SAR ─────────────────────────────────────────────────────────────
if show_psar:
    psar_s = compute_parabolic_sar(df["High"], df["Low"], psar_af, psar_max)
    fig.add_trace(go.Scatter(x=df.index, y=psar_s, mode="markers",
        marker=dict(color=AMBER, size=3, symbol="circle"),
        name="PSAR"), row=1, col=1)

# ── 52-Week H/L ───────────────────────────────────────────────────────────────
shapes, annotations = [], []
if show_hl52 and high52 and low52:
    for level, lbl, col in [(high52, "52W H", GREEN), (low52, "52W L", RED)]:
        shapes.append(dict(type="line", x0=df.index[0], x1=df.index[-1],
                           y0=level, y1=level, xref="x", yref="y1",
                           line=dict(color=col, width=1, dash="dash")))
        annotations.append(dict(x=df.index[-1], y=level, text=f" {lbl}",
                                 showarrow=False, font=dict(color=col, size=10),
                                 xref="x", yref="y1"))

# ── S/R Lines ────────────────────────────────────────────────────────────────
for lvl in st.session_state.sr_levels:
    shapes.append(dict(type="line", x0=df.index[0], x1=df.index[-1],
                       y0=lvl, y1=lvl, xref="x", yref="y1",
                       line=dict(color=AMBER, width=1.5, dash="dot")))
    annotations.append(dict(x=df.index[-1], y=lvl, text=f"  {lvl:,.2f}",
                             showarrow=False, font=dict(color=AMBER, size=10),
                             xref="x", yref="y1"))

# ── Volume sub-panel ─────────────────────────────────────────────────────────
if has_vol:
    vrow = row_map["volume"]
    vol_colors = [up_col if c >= o else down_col for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color=vol_colors, marker_line_width=0,
        name="Volume", showlegend=False,
    ), row=vrow, col=1)
    fig.update_yaxes(title_text="Vol", row=vrow, col=1,
                     showgrid=False, tickfont=dict(size=9))

# ── Sub-panel indicator ───────────────────────────────────────────────────────
if has_sub:
    irow = row_map["indicator"]

    if sub_ind == "MACD":
        ml, sl_, hist = compute_macd(df["Close"], int(macd_fast), int(macd_slow), int(macd_signal))
        fig.add_trace(go.Scatter(x=df.index, y=ml, mode="lines",
            line=dict(color=BLUE, width=1.2), name="MACD"), row=irow, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=sl_, mode="lines",
            line=dict(color=AMBER, width=1.2), name="Signal"), row=irow, col=1)
        hist_colors = [GREEN if v >= 0 else RED for v in hist.fillna(0)]
        fig.add_trace(go.Bar(x=df.index, y=hist, marker_color=hist_colors,
            marker_line_width=0, name="Histogram"), row=irow, col=1)
        fig.add_hline(y=0, line=dict(color=BORDER, width=0.8), row=irow, col=1)
        fig.update_yaxes(title_text="MACD", row=irow, col=1)

    elif sub_ind == "RSI":
        rsi_s = compute_rsi(df["Close"], int(rsi_period))
        fig.add_trace(go.Scatter(x=df.index, y=rsi_s, mode="lines",
            line=dict(color=PURPLE, width=1.5), name="RSI"), row=irow, col=1)
        for lvl, col_ in [(70, "rgba(239,68,68,0.3)"), (30, "rgba(34,197,94,0.3)")]:
            fig.add_hline(y=lvl, line=dict(color=col_, width=1, dash="dot"), row=irow, col=1)
        fig.add_hline(y=50, line=dict(color=BORDER, width=0.8), row=irow, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=irow, col=1)

    elif sub_ind == "Stochastic":
        k_s, d_s = compute_stochastic(df["High"], df["Low"], df["Close"],
                                       int(stoch_k), int(stoch_smooth), int(stoch_d))
        fig.add_trace(go.Scatter(x=df.index, y=k_s, mode="lines",
            line=dict(color=BLUE, width=1.2), name="%K"), row=irow, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=d_s, mode="lines",
            line=dict(color=AMBER, width=1.2, dash="dot"), name="%D"), row=irow, col=1)
        for lvl, col_ in [(80, "rgba(239,68,68,0.3)"), (20, "rgba(34,197,94,0.3)")]:
            fig.add_hline(y=lvl, line=dict(color=col_, width=1, dash="dot"), row=irow, col=1)
        fig.update_yaxes(title_text="Stoch", range=[0, 100], row=irow, col=1)

    elif sub_ind == "CCI":
        cci_s = compute_cci(df["High"], df["Low"], df["Close"], int(cci_period))
        fig.add_trace(go.Scatter(x=df.index, y=cci_s, mode="lines",
            line=dict(color="#a78bfa", width=1.2), name="CCI"), row=irow, col=1)
        for lvl, col_ in [(100, "rgba(239,68,68,0.3)"), (-100, "rgba(34,197,94,0.3)")]:
            fig.add_hline(y=lvl, line=dict(color=col_, width=1, dash="dot"), row=irow, col=1)
        fig.add_hline(y=0, line=dict(color=BORDER, width=0.8), row=irow, col=1)
        fig.update_yaxes(title_text="CCI", row=irow, col=1)

    elif sub_ind == "ADX":
        adx_s, pdi_s, ndi_s = compute_adx(df["High"], df["Low"], df["Close"], int(adx_period))
        fig.add_trace(go.Scatter(x=df.index, y=adx_s, mode="lines",
            line=dict(color=AMBER, width=1.5), name="ADX"), row=irow, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=pdi_s, mode="lines",
            line=dict(color=GREEN, width=1.2), name="+DI"), row=irow, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=ndi_s, mode="lines",
            line=dict(color=RED, width=1.2), name="-DI"), row=irow, col=1)
        fig.add_hline(y=20, line=dict(color=BORDER, width=0.8, dash="dot"), row=irow, col=1)
        fig.update_yaxes(title_text="ADX", row=irow, col=1)

    elif sub_ind == "Williams %R":
        wr_s = compute_williams_r(df["High"], df["Low"], df["Close"], int(wr_period))
        fig.add_trace(go.Scatter(x=df.index, y=wr_s, mode="lines",
            line=dict(color="#fb923c", width=1.2), name="%R"), row=irow, col=1)
        for lvl, col_ in [(-20, "rgba(239,68,68,0.3)"), (-80, "rgba(34,197,94,0.3)")]:
            fig.add_hline(y=lvl, line=dict(color=col_, width=1, dash="dot"), row=irow, col=1)
        fig.update_yaxes(title_text="%R", range=[-105, 5], row=irow, col=1)

    elif sub_ind == "Awesome Oscillator":
        ao_s = compute_awesome_oscillator(df["High"], df["Low"])
        ao_col = [GREEN if v >= 0 else RED for v in ao_s.fillna(0)]
        fig.add_trace(go.Bar(x=df.index, y=ao_s, marker_color=ao_col,
            marker_line_width=0, name="AO"), row=irow, col=1)
        fig.add_hline(y=0, line=dict(color=BORDER, width=0.8), row=irow, col=1)
        fig.update_yaxes(title_text="AO", row=irow, col=1)

    elif sub_ind == "OBV":
        obv_s = compute_obv(df["Close"], df["Volume"])
        fig.add_trace(go.Scatter(x=df.index, y=obv_s, mode="lines",
            line=dict(color="#34d399", width=1.2), name="OBV"), row=irow, col=1)
        fig.update_yaxes(title_text="OBV", row=irow, col=1)

    elif sub_ind == "MFI":
        mfi_s = compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"], int(mfi_period))
        fig.add_trace(go.Scatter(x=df.index, y=mfi_s, mode="lines",
            line=dict(color="#67e8f9", width=1.2), name="MFI"), row=irow, col=1)
        for lvl, col_ in [(80, "rgba(239,68,68,0.3)"), (20, "rgba(34,197,94,0.3)")]:
            fig.add_hline(y=lvl, line=dict(color=col_, width=1, dash="dot"), row=irow, col=1)
        fig.update_yaxes(title_text="MFI", range=[0, 100], row=irow, col=1)

# ── Layout ───────────────────────────────────────────────────────────────────
fig.update_layout(
    height=640,
    paper_bgcolor=DARK_BG,
    plot_bgcolor=DARK_BG,
    legend=dict(
        bgcolor="rgba(26,29,38,0.8)", bordercolor=BORDER, borderwidth=1,
        font=dict(color=TEXT, size=11), orientation="h",
        yanchor="bottom", y=1.01, xanchor="left", x=0,
    ),
    margin=dict(l=10, r=10, t=30, b=10),
    hovermode="x unified",
    hoverlabel=dict(bgcolor=CARD_BG, bordercolor=BORDER, font=dict(color=TEXT, size=11)),
    dragmode="pan",
    xaxis_rangeslider_visible=False,
    yaxis_type="log" if log_scale else "linear",
    shapes=shapes,
    annotations=annotations,
    font=dict(color=TEXT),
)
# Dark grid lines on all y-axes
for i in range(1, n_rows + 1):
    fig.update_yaxes(
        row=i, col=1,
        gridcolor=BORDER, gridwidth=0.5,
        zeroline=False,
        tickfont=dict(size=10, color="#94a3b8"),
        title_font=dict(size=10, color="#94a3b8"),
    )
fig.update_xaxes(
    gridcolor=BORDER, gridwidth=0.3,
    showspikes=True, spikecolor="#94a3b8", spikethickness=1,
    tickfont=dict(size=10, color="#94a3b8"),
)

# ── Render chart ─────────────────────────────────────────────────────────────
chart_config = {
    "scrollZoom": True,
    "displayModeBar": True,
    "modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"],
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "editable": True,
    "displaylogo": False,
    "toImageButtonOptions": {"format": "png", "height": 900, "width": 1600, "scale": 2},
}
st.plotly_chart(fig, use_container_width=True, config=chart_config)

# Render active sub-panel indicator guide if selected
if sub_ind == "MACD":
    section_guide("tech_macd", title="📖 Reading MACD", expanded=False)
elif sub_ind == "RSI":
    section_guide("tech_rsi", title="📖 Reading RSI", expanded=False)
elif sub_ind == "Stochastic":
    section_guide("tech_stochastic", title="📖 Reading Stochastic", expanded=False)
elif sub_ind == "ADX":
    section_guide("tech_adx", title="📖 Reading ADX", expanded=False)
elif sub_ind == "Williams %R":
    section_guide("tech_williams", title="📖 Reading Williams %R", expanded=False)
elif sub_ind == "CCI":
    section_guide("tech_cci", title="📖 Reading CCI", expanded=False)
elif sub_ind == "OBV":
    section_guide("tech_obv", title="📖 Reading OBV", expanded=False)
elif sub_ind == "MFI":
    section_guide("tech_mfi", title="📖 Reading MFI", expanded=False)

# ─────────────────────────────────────────────────────────────────────────────
# TECHNICAL SUMMARY SECTION
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 📊 Technical Summary")
section_guide("tech_summary", title="📖 Understanding the Technical Summary", expanded=False)

# Timeframe selector for summary (independent of chart interval)
sum_ctrl1, sum_ctrl2 = st.columns([3, 5])
with sum_ctrl1:
    sum_tf = st.radio(
        "Summary timeframe",
        ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W", "1M"],
        horizontal=True, index=6, key="sum_tf",
    )
with sum_ctrl2:
    intraday_warning = {
        "1m": "⚠️ 1m: last 5 days only",
        "5m": "⚠️ 5m / 15m / 30m: last 60 days only",
        "15m": "⚠️ 5m / 15m / 30m: last 60 days only",
        "30m": "⚠️ 5m / 15m / 30m: last 60 days only",
        "1h": "ℹ️ 1h / 4h: last 730 days",
        "4h": "ℹ️ 1h / 4h: last 730 days",
    }
    if sum_tf in intraday_warning:
        st.caption(intraday_warning[sum_tf])

# Load data for summary at selected timeframe
_sum_yf_int = INTERVALS[sum_tf][0]
_sum_resample = (sum_tf == "4h")
_sum_period   = INTERVALS[sum_tf][1]

with st.spinner("Computing signals…"):
    df_sum = _load(ticker, _sum_period, _sum_yf_int, _sum_resample)

if df_sum is None or len(df_sum) < 30:
    st.warning(f"Not enough data ({len(df_sum) if df_sum is not None else 0} bars) for reliable signals at {sum_tf}.")
else:
    # Compute signals
    osc_params = {
        "rsi_period": rsi_period, "cci_period": cci_period,
        "adx_period": adx_period, "mom_period": 10, "wr_period": wr_period,
    }
    try:
        osc_signals = get_oscillator_signals(df_sum, osc_params)
        ma_signals  = get_ma_signals(df_sum)
        summary     = get_summary(osc_signals, ma_signals)
    except Exception as e:
        st.error(f"Signal computation error: {e}")
        osc_signals, ma_signals, summary = [], [], {}

    if summary:
        # ── 3 Gauges ──────────────────────────────────────────────────────────
        g1, g2, g3 = st.columns(3)
        with g1:
            s = summary["oscillators"]
            st.plotly_chart(
                _gauge(s["score"], "Oscillators", s["buy"], s["neutral"], s["sell"]),
                use_container_width=True, config={"displayModeBar": False},
            )
        with g2:
            s = summary["summary"]
            st.plotly_chart(
                _gauge(s["score"], "Summary", s["buy"], s["neutral"], s["sell"]),
                use_container_width=True, config={"displayModeBar": False},
            )
        with g3:
            s = summary["ma"]
            st.plotly_chart(
                _gauge(s["score"], "Moving Averages", s["buy"], s["neutral"], s["sell"]),
                use_container_width=True, config={"displayModeBar": False},
            )

    # ── Oscillator + MA Signal Tables ──────────────────────────────────────
    st.markdown("---")
    tbl1, tbl2 = st.columns(2)

    with tbl1:
        st.markdown("#### Oscillators")
        if osc_signals:
            st.markdown(_styled_signal_table(osc_signals, ccy), unsafe_allow_html=True)

    with tbl2:
        st.markdown("#### Moving Averages")
        if ma_signals:
            st.markdown(_styled_signal_table(ma_signals, ccy), unsafe_allow_html=True)

    # ── Pivot Points Table ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📍 Pivot Points")
    section_guide("tech_pivot_points", title="📖 What are Pivot Points?", expanded=False)

    # Use last completed bar of the CHART data (not summary data)
    try:
        # Use prior bar (completed candle) for pivot calculation
        _pdf = df if len(df) >= 2 else df_sum
        _row = _pdf.iloc[-2]     # -1 is current (forming); -2 is last complete
        _prev_row = _pdf.iloc[-3] if len(_pdf) >= 3 else _row
        pivs = compute_pivots(
            float(_row["High"]), float(_row["Low"]), float(_row["Close"]),
            prev_C=float(_prev_row["Close"])
        )

        # Build pivot table
        levels = ["R3", "R2", "R1", "P", "S1", "S2", "S3"]
        pivot_data = {}
        for method, vals in pivs.items():
            col_vals = []
            for lvl in levels:
                v = vals.get(lvl)
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    col_vals.append("—")
                else:
                    col_vals.append(f"{v:,.2f}")
            pivot_data[method] = col_vals

        pivot_df = pd.DataFrame(pivot_data, index=levels)

        # Style: P row highlighted, R levels in green, S levels in red
        def _style_pivot(val, idx):
            if idx == "P":  return f"background-color:{CARD_BG};color:{AMBER};font-weight:700"
            if idx.startswith("R"): return f"color:{GREEN}"
            if idx.startswith("S"): return f"color:{RED}"
            return f"color:{TEXT}"

        styled = pivot_df.style.apply(
            lambda col: [_style_pivot(v, idx) for idx, v in col.items()], axis=0
        ).set_table_styles([
            {"selector": "thead th", "props": f"background:{CARD_BG};color:#94a3b8;font-weight:600;text-align:center;padding:6px 12px;border-bottom:1px solid {BORDER}"},
            {"selector": "tbody td", "props": f"text-align:center;padding:5px 12px;font-size:0.85rem;border-bottom:1px solid {BORDER}20"},
            {"selector": "tbody th", "props": f"text-align:left;padding:5px 12px;color:#94a3b8;font-weight:600;border-bottom:1px solid {BORDER}20"},
        ])

        st.caption(
            f"Pivot inputs: H={_row['High']:,.2f}  L={_row['Low']:,.2f}  C={_row['Close']:,.2f} "
            f"(last completed {interval_key} candle)"
        )
        st.dataframe(styled, use_container_width=True, height=300)

    except Exception as e:
        st.warning(f"Could not compute pivot points: {e}")
