# MutualFundAnalysis

> **An institutional-grade, India-focused mutual fund research, portfolio intelligence, multi-factor scoring, strategy backtesting, and automated PDF report platform built with Django, Pandas, and Plotly.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Django 5.x](https://img.shields.io/badge/django-5.x-green.svg)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Disclaimer:** Mutual fund investments are subject to market risks. Read all scheme-related documents carefully before investing. This platform is built strictly for research, quantitative analysis, and educational purposes. It does not constitute financial, legal, or tax advice.

---

## 🚀 Key Platform Features

### 1. 📄 Institutional PDF Research Report System
- **Dynamic 13-Page PDF Report**: Automated Chrome-headless PDF generator creating wall-street style research documents for any Indian mutual fund scheme or ETF.
- **Dynamic Analyst Narrative Generator**: Synthesizes scorecards, 3Y CAGR, Jensen's Alpha, Beta, Sharpe Ratios, Rolling Return Win-Rates, and Technical Signals into structured research commentaries.
- **Executive Analyst Verdict Cards**: Assigns quantitative ratings (`STRONG BUY`, `BUY / ACCUMULATE`, `HOLD`, `REBALANCE`) with target holding horizons, investor profiles, deployment strategies, key strengths, and monitorable risks.
- **In-Line Metric Definitions**: Educational explainer cards for Jensen's Alpha, Sharpe & Sortino Ratios, Beta, and Maximum Drawdown.
- **Visual Analytics & Gauges**: Side-by-side rolling return distribution box plots (1Y–7Y), technical riskometer gauges (Daily/Weekly/Monthly), and 10-column peer comparison matrices.
- **Executive & Legal Disclaimers**: Embedded compliance disclosures at both the start and end of every report.
- *See [INSTITUTIONAL_REPORT.md](documentation/INSTITUTIONAL_REPORT.md) for full architecture and template specifications.*

---

### 2. 📊 Market Intelligence & Ticker Strip
- **Live Ticker Strip**: Real-time ticker bar displaying broad market indices, market sentiment, technicals, macroeconomic indicators, and global benchmarks.
- **24 Built-in Market Metrics**:
  - **Broad Indices**: Nifty 50, Sensex, Nifty 200, Nifty Midcap 150, Nifty Smallcap 250
  - **Volatility & Currency**: USD/INR, India VIX
  - **Technicals**: Nifty RSI(14), MACD, BB %B, 50/200 DMA, Distance from 52W High, Distance from ATH, Mid/Large Cap Relative Strength
  - **Macro (RBI & FRED)**: RBI Repo Rate, India CPI (YoY), Fed Funds Rate *(with personal FRED API key validation & storage)*
  - **Global Benchmarks**: US VIX, DXY, US 10Y Yield, Brent Crude, Gold, S&P 500, NASDAQ
- **Direction-Calibrated Signals & Tooltips**: Color badges (`BULLISH`, `BEARISH`, `DEFENSIVE`, `LOW COST`) and viewport-aware hover tooltips explaining metrics and decision thresholds.
- *See [mf_market_metrics_reference.md](documentation/ideas/mf_market_metrics_reference.md) for the mathematical decision map.*

---

### 3. 🔍 Fund Research, Screener & Analytics
- **Complete Indian Universe**: Browse and evaluate **2,000+ Direct Growth Mutual Funds** and **300+ ETFs** with real-time AMFI cache fallbacks.
- **6-Pillar Quantitative Scoring Engine (0–100)**: Evaluates Performance (30%), Risk & Stability (25%), Cost Efficiency (15%), Portfolio Composition (15%), Manager Quality (15%), and Debt Quality (10% for hybrid/debt).
- **Macro Stress Testing**: Simulates fund behavior across 6 major historical market crashes (2024–25 Tariff Shock, COVID-19 Crash, 2022 Rate Hikes, 2018 IL&FS, 2015 China Slowdown, 2008 GFC).
- **Market-Regime Analysis**: Evaluates performance across 5 economic cycles (Bull, Bear, Sideways, High Inflation, Rate Cut).
- **Quartile & Peer Rankings**: Dynamic sub-category peer ranking computed on-the-fly.
- **Advanced Quant Suite**: 9 technical indicators, 5 pivot systems, 500-path Monte Carlo simulations, VaR/CVaR risk matrices, Ensemble & ARIMA/XGBoost/LSTM return forecasting, and GARCH volatility models.
- *See [SCREENER.md](documentation/SCREENER.md) and [ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md).*

---

### 4. 📁 Portfolio CAS Analysis & Overlap Engine
- **CAS Import**: Upload Consolidated Account Statement (CAS) PDF files or enter manual transactions.
- **Fuzzy Name Matching**: Automatically resolves CAS fund names to standard AMFI codes.
- **Performance & Risk Tracking**: Computes exact per-fund and portfolio-level **XIRR** using SciPy root-finding.
- **Portfolio Overlap Matrix**: Evaluates stock-level holding overlap across portfolio funds.
- **Herfindahl-Hirschman Index (HHI)**: Quantifies portfolio stock and sector concentration risk.

---

### 5. ⚡ Strategy Backtester V2
- **Multi-Asset Strategy Builder**: Simulate custom portfolios containing mutual funds and NSE benchmark indices.
- **Investment Modes**: Simulate SIP, Step-Up SIP, Lumpsum, SWP, and Switch strategies.
- **Conditional Triggers**: Attach rule-based triggers (Drawdown from ATH, 200 DMA, RSI thresholds, Valuation bounds, Calendar dates).
- **Advanced Engines**: Inflation adjustment (World Bank CPI), FIFO STCG/LTCG tax engines, and multi-scenario Monte Carlo projections.
- *See [backtester_analysis.md](documentation/backtester_analysis.md).*

---

### 6. 🧮 Financial Calculators Suite (17 Calculators)
- **Growth & Wealth**: SIP, Lumpsum, SWP, Step-Up SIP, STP, XIRR, and Rolling Returns.
- **Peer & AMC Comparison**: Peer Comparison (SEBI fingerprint matching), Fund Comparison, Overlap Checker, AMC Comparison, and Category Comparison.
- **Life Event Planning**: Goal Planner, Retirement Planner (25x FIRE rule & 4% SWR), Child Education Planner, and SWP Pension Longevity.
- **Tax & Wealth**: Capital Gains Tax Calculator (FY 2025-26 rules) and Net Worth Tracker.
- *See [CALCULATORS.md](documentation/CALCULATORS.md).*

---

## 🛠️ Technology Stack

| Layer | Technologies Used |
|---|---|
| **Backend Core** | Python 3.11+, Django 5.x |
| **Data & Analytics** | Pandas, NumPy, SciPy, Statsmodels, Scikit-Learn |
| **Visualization** | Plotly.js, Plotly Python, Kaleido, Canvas PDF.js |
| **PDF Generation** | Google Chrome Headless (`--no-pdf-header-footer` CLI), Django HTML/CSS Paged Media |
| **Frontend UI** | Django Templates, Vanilla CSS (Custom Design System), Vanilla JS, HTMX |
| **Database** | SQLite (Development) / PostgreSQL (Production) |
| **External APIs** | yfinance, FRED API, mfapi.in, Morningstar, AMFI |

---

## 💻 Local Setup & Development Quickstart

### Prerequisites
- Python 3.11 or higher
- Git
- Google Chrome (installed at standard OS location for PDF generation)

### Installation Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/amansingh2116/MutualFundAnalysis.git
   cd MutualFundAnalysis
   ```

2. **Create and Activate Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   ```bash
   cp .env.example .env
   # Edit .env to set your SECRET_KEY and optional FRED_API_KEY
   ```

5. **Run Database Migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create Superuser (Optional)**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Start Development Server**:
   ```bash
   python manage.py runserver
   ```
   Open `http://127.0.0.1:8000/` in your browser.

---

## 🔄 Data Ingestion & Sync Commands

The platform features automated management commands to fetch and calculate data:

```bash
# Sync NAV price series for all funds from mfapi.in
python manage.py sync_nav

# Update AMFI fund universe metadata & scheme listings
python manage.py sync_amfi

# Recompute screener snapshots and quantitative scorecards
python manage.py recompute_screener_snapshots

# Update category benchmark snapshots & peer averages
python manage.py sync_category_snapshots

# Fetch macroeconomic metrics from FRED & RBI
python manage.py sync_macro_fred
```

---

## 📚 Technical Documentation Directory

- **[INSTITUTIONAL_REPORT.md](documentation/INSTITUTIONAL_REPORT.md)** — Institutional PDF Research Report architecture & engine guide
- **[SCREENER.md](documentation/SCREENER.md)** — Fund Screener user & developer guide
- **[ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md)** — Technical indicators, ML forecasting & risk models
- **[CALCULATORS.md](documentation/CALCULATORS.md)** — Guide for all 17 financial calculators
- **[backtester_analysis.md](documentation/backtester_analysis.md)** — Strategy Backtester V2 specs & user guide
- **[mf_market_metrics_reference.md](documentation/ideas/mf_market_metrics_reference.md)** — Live Market Ticker metrics framework
- **[PROJECT_CONTEXT.md](documentation/PROJECT_CONTEXT.md)** — Architecture & repository directory context

---

## ⚖️ License & Disclaimer

Distributed under the **MIT License**. See `LICENSE` for more information.

*Mutual fund investments are subject to market risks. Read all scheme-related documents carefully before investing. Historical performance and quantitative model scores do not guarantee future returns.*
