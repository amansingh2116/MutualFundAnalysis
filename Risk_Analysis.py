"""
pages/5_Risk_Analysis.py
Tabs: Financial Distress (Z-Score) | Value at Risk | Monte Carlo Simulation
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import numpy as np

from app.data.fetcher import get_income_statement_enriched, get_balance_sheet_enriched, get_stock_info, get_fast_info, get_price_history
from app.compute.risk import compute_altman_z_score, calculate_var_cvar, run_monte_carlo
from app.utils.formatters import fmt_currency, fmt_pct, fmt_number, format_date_cols
from app.utils.charts import altman_bar_chart, histogram_chart, monte_carlo_chart, DARK_BG, CARD_BG, BORDER, TEXT, BLUE, GREEN, AMBER, PURPLE, RED
from app.utils.guides import info_btn, section_guide

st.set_page_config(page_title="Risk Analysis · Equity Research", page_icon="⚠️", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main { background: #0f1117 !important; }
.block-container { padding-top: 1.5rem !important; }
.stTabs [data-baseweb="tab-list"] { gap:0.5rem; background:#1a1d26; border-radius:10px; padding:0.4rem; }
.stTabs [data-baseweb="tab"] { border-radius:8px!important; color:#94a3b8!important; font-weight:500!important; padding:0.5rem 1rem!important; }
.stTabs [aria-selected="true"] { background:#3b82f6!important; color:white!important; }
section[data-testid="stSidebar"] { background: #1a1d26 !important; }
.risk-box { background: #1a1d26; border: 1px solid #2d3748; border-radius: 10px; padding: 1.5rem; text-align: center; }
.risk-box-title { color: #94a3b8; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.risk-box-val { font-size: 2.2rem; font-weight: 700; color: #e2e8f0; }
.risk-box-sub { font-size: 0.9rem; margin-top: 0.5rem; }
</style>
""", unsafe_allow_html=True)

if "ticker" not in st.session_state or not st.session_state.ticker:
    st.warning("⚠️ No stock selected. Go to the Home page first.")
    st.page_link("main.py", label="← Back to Home")
    st.stop()

ticker = st.session_state.ticker
company_name = st.session_state.get("company_name", ticker)

with st.sidebar:
    st.markdown(f"### 📊 {ticker}")
    st.caption(company_name)
    st.divider()
    st.page_link("main.py", label="🏠 Home / Search")
    st.page_link("pages/1_Company_Overview.py", label="🏢 Overview")
    st.page_link("pages/2_Financial_Statements.py", label="📋 Financial Statements")
    st.page_link("pages/3_Ratio_Analysis.py", label="📐 Ratio Analysis")
    st.page_link("pages/4_Valuation.py", label="💰 Valuation")
    st.page_link("pages/5_Risk_Analysis.py", label="⚠️ Risk")
    st.page_link("pages/6_Report_Generator.py", label="📄 PDF Report")

st.markdown(f"## ⚠️ {company_name} — Risk Analysis")

with st.spinner("Fetching data for risk models..."):
    info = get_stock_info(ticker)
    fast = get_fast_info(ticker)
    income, _inc_src = get_income_statement_enriched(ticker, "annual", company_name)
    balance, _bal_src = get_balance_sheet_enriched(ticker, "annual", company_name)

    currency = info.get("currency", "USD")
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") or fast.get("current_price", 0)
    market_cap = info.get("marketCap") or fast.get("market_cap", 0)

    # 3Y daily returns for VaR and Monte Carlo
    price_hist = get_price_history(ticker, "3y", "1d")

tab1, tab2, tab3 = st.tabs([
    "🆘 Financial Distress (Z-Score)", "📉 Value at Risk (VaR)", "🎲 Monte Carlo Price Simulation"
])

# ──── TAB 1: ALTMAN Z-SCORE ─────────────────────────────────────────
with tab1:
    st.markdown("### Altman Z-Score (Bankruptcy Prediction)")
    section_guide("risk_zscore", expanded=True)

    if income is not None and not income.empty and balance is not None and not balance.empty:
        zscore_df = compute_altman_z_score(income, balance, market_cap)

        if zscore_df is not None and not zscore_df.empty:
            dates = [str(c.year) if hasattr(c, 'year') else str(c) for c in zscore_df.columns][::-1]
            latest_z = float(zscore_df.loc["Altman Z-Score"].iloc[0])

            if latest_z > 2.99:
                z_color, z_zone, z_desc = GREEN, "Safe Zone", "Low risk of bankruptcy within 2 years."
            elif latest_z >= 1.81:
                z_color, z_zone, z_desc = AMBER, "Grey Zone", "Moderate risk of financial distress."
            else:
                z_color, z_zone, z_desc = RED, "Distress Zone", "High probability of bankruptcy within 2 years."

            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f"""
                <div class='risk-box' style='border-color: {z_color}; background: rgba({int(z_color[1:3],16)},{int(z_color[3:5],16)},{int(z_color[5:7],16)},0.05)'>
                    <div class='risk-box-title'>Current Z-Score ({dates[-1]})</div>
                    <div class='risk-box-val' style='color: {z_color}'>{latest_z:.2f}</div>
                    <div class='risk-box-sub' style='color: {z_color}; font-weight: 600'>{z_zone}</div>
                    <div style='color: #94a3b8; font-size: 0.8rem; margin-top: 1rem;'>{z_desc}</div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("""
                **Z-Score Formula:**
                `Z = 1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5`
                - **X1:** Working Capital / Total Assets
                - **X2:** Retained Earnings / Total Assets
                - **X3:** EBIT / Total Assets
                - **X4:** Market Value of Equity / Total Liabilities
                - **X5:** Sales / Total Assets
                """)

            with c2:
                fig_z = altman_bar_chart(zscore_df)
                st.plotly_chart(fig_z, width='stretch')

            col_hdr, col_info = st.columns([0.95, 0.05])
            with col_hdr:
                st.markdown("#### 📋 Z-Score Components")
            with col_info:
                info_btn("risk_zscore_components")

            z_fmt = format_date_cols(zscore_df.copy())
            for idx in z_fmt.index:
                for col in z_fmt.columns:
                    try:
                        v = float(z_fmt.loc[idx, col])
                        if idx == "Altman Z-Score":
                            z_fmt.loc[idx, col] = f"{v:.2f}"
                        elif idx in ["X1", "X2", "X3", "X4", "X5"]:
                            z_fmt.loc[idx, col] = f"{v:.3f}"
                        else:
                            z_fmt.loc[idx, col] = fmt_currency(v, "")
                    except (ValueError, TypeError):
                        pass
            st.dataframe(z_fmt, width='stretch')
        else:
            st.warning("Insufficient financial data to compute Altman Z-Score.")
    else:
        st.warning("Financial statements missing.")

# ──── TAB 2: VALUE AT RISK (VaR) ────────────────────────────────────
with tab2:
    st.markdown("### Historical Value at Risk (VaR) & CVaR")
    st.write("Using past 3 years of daily returns.")
    section_guide("risk_var_overview", expanded=True)

    if price_hist is not None and not price_hist.empty and len(price_hist) > 100:
        returns = price_hist["Close"].pct_change(fill_method=None).dropna()
        var_res = calculate_var_cvar(returns)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""
            <div class='risk-box'>
                <div class='risk-box-title'>95% Daily VaR</div>
                <div class='risk-box-val' style='color:{AMBER}'>{var_res['VaR_95'] * 100:.2f}%</div>
                <div class='risk-box-sub'>1 in 20 days loss will exceed this</div>
            </div>""", unsafe_allow_html=True)
            info_btn("risk_var_95")
        with c2:
            st.markdown(f"""
            <div class='risk-box'>
                <div class='risk-box-title'>99% Daily VaR</div>
                <div class='risk-box-val' style='color:{RED}'>{var_res['VaR_99'] * 100:.2f}%</div>
                <div class='risk-box-sub'>1 in 100 days loss will exceed this</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class='risk-box'>
                <div class='risk-box-title'>99% CVaR (Expected Shortfall)</div>
                <div class='risk-box-val' style='color:{PURPLE}'>{var_res['CVaR_99'] * 100:.2f}%</div>
                <div class='risk-box-sub'>Average loss on worst 1% of days</div>
            </div>""", unsafe_allow_html=True)
            info_btn("risk_cvar_99")

        st.divider()

        fig_hist = histogram_chart(returns, var_levels={
            95: var_res["VaR_95"],
            99: var_res["VaR_99"],
            99.5: var_res["VaR_99.5"]
        }, title=f"{ticker} Daily Returns Distribution & VaR Thresholds")

        st.plotly_chart(fig_hist, width='stretch')
        section_guide("risk_returns_distribution")
    else:
        st.warning("Insufficient price history to calculate VaR (minimum 100 days required).")


# ──── TAB 3: MONTE CARLO SIMULATION ─────────────────────────────────
with tab3:
    st.markdown("### 🎲 Monte Carlo Price Simulation")
    st.write("Simulating future price paths based on historical drift and volatility (Geometric Brownian Motion).")
    section_guide("risk_monte_carlo", expanded=True)

    if price_hist is not None and not price_hist.empty and len(price_hist) > 100:
        returns = price_hist["Close"].pct_change(fill_method=None).dropna()

        # Inputs
        col_hdr, col_inf = st.columns([0.95, 0.05])
        with col_hdr:
            st.markdown("**Simulation Inputs**")
        with col_inf:
            info_btn("risk_mc_params")

        col_inp1, col_inp2, col_inp3, col_inp4 = st.columns(4)
        with col_inp1:
            days = st.number_input("Days to Simulate", min_value=10, max_value=504, value=252, step=10)
        with col_inp2:
            paths = st.number_input("Number of Paths", min_value=100, max_value=10000, value=2000, step=500)
        with col_inp3:
            mu_override = st.number_input("Expected Annual Return (Drift) %", value=returns.mean() * 252 * 100, step=1.0) / 100
        with col_inp4:
            vol_override = st.number_input("Annual Volatility %", value=returns.std() * np.sqrt(252) * 100, step=1.0) / 100

        mc_res = run_monte_carlo(current_price, mu_override, vol_override, time_horizon=days/252, n_sims=paths)

        if mc_res:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class='risk-box'>
                    <div class='risk-box-title'>Median Expected Price (50th Pct)</div>
                    <div class='risk-box-val' style='color:{AMBER}'>{fmt_currency(mc_res['expected_price_50th'], currency, False)}</div>
                </div>""", unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class='risk-box'>
                    <div class='risk-box-title'>Bear Case (5th Pct)</div>
                    <div class='risk-box-val' style='color:{RED}'>{fmt_currency(mc_res['price_5th'], currency, False)}</div>
                </div>""", unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class='risk-box'>
                    <div class='risk-box-title'>Bull Case (95th Pct)</div>
                    <div class='risk-box-val' style='color:{GREEN}'>{fmt_currency(mc_res['price_95th'], currency, False)}</div>
                </div>""", unsafe_allow_html=True)

            st.divider()

            fig_mc = monte_carlo_chart(mc_res["paths"], current_price, ticker, n_show=200)
            st.plotly_chart(fig_mc, width='stretch')
    else:
        st.warning("Insufficient price history to run Monte Carlo.")
