# MutualFundAnalysis

> **An institutional-grade, India-focused mutual fund research, portfolio intelligence, multi-factor scoring, strategy backtesting, and automated PDF report platform built with Django, Pandas, and Plotly.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Django 5.x](https://img.shields.io/badge/django-5.x-green.svg)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker)](https://www.docker.com/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary_Non--Commercial-red.svg)](LICENSE)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7?logo=render)](https://render.com)
[![Database: CockroachDB](https://img.shields.io/badge/Database-CockroachDB-6933FF?logo=cockroachlabs)](https://cockroachlabs.cloud)
[![Kaggle Dataset](https://img.shields.io/badge/Kaggle-Dataset-20BEFF?logo=kaggle)](https://www.kaggle.com/datasets/amansingh2116/indian-mutual-funds-complete-nav-analytics)

**Disclaimer:** Mutual fund investments are subject to market risks. Read all scheme-related documents carefully before investing. This platform is built strictly for research, quantitative analysis, and educational purposes. It does not constitute financial, legal, or tax advice.

---

## 🚀 Key Platform Features

### 1. 📄 Institutional PDF Research Report System
- **Comprehensive Institutional PDF Report**: Automated Chrome-headless PDF generator creating wall-street style research documents for any Indian mutual fund scheme or ETF.
- **Dynamic Analyst Narrative Generator**: Synthesizes scorecards, 3Y CAGR, Jensen's Alpha, Beta, Sharpe Ratios, Rolling Return Win-Rates, and Technical Signals into structured research commentaries.
- **Executive Analyst Verdict Cards**: Assigns quantitative ratings (`STRONG BUY`, `BUY / ACCUMULATE`, `HOLD`, `REBALANCE`) with target holding horizons, investor profiles, deployment strategies, key strengths, and monitorable risks.
- **In-Line Metric Definitions**: Educational explainer cards for Jensen's Alpha, Sharpe & Sortino Ratios, Beta, and Maximum Drawdown.
- **Visual Analytics & Gauges**: Side-by-side rolling return distribution box plots (1Y–7Y), technical riskometer gauges (Daily/Weekly/Monthly), and 10-column peer comparison matrices.
- *See [INSTITUTIONAL_REPORT.md](documentation/INSTITUTIONAL_REPORT.md) for full architecture and template specifications.*

---

### 2. 📊 Market Intelligence & Ticker Strip
- **Live Ticker Strip**: Real-time ticker bar displaying broad market indices, market sentiment, technicals, valuation, macroeconomic indicators, and global benchmarks.
- **33 Built-in Market Metrics**:
  - **Broad Indices**: Nifty 50, Sensex, Nifty 200, Nifty Midcap 150, Nifty Smallcap 250
  - **Sentiment**: India VIX, Nifty PCR (Put/Call Ratio), FII Net Activity, Advance/Decline Ratio, Monthly SIP Inflows
  - **Technicals**: Nifty RSI(14), MACD, BB %B, 50/200 DMA, Distance from 52W High, Distance from ATH, Mid/Large Cap Relative Strength
  - **Valuation**: Nifty 50 PE, PB, Dividend Yield, Earnings Yield–Bond Gap, Buffett Indicator (Market Cap/GDP)
  - **Macro**: USD/INR, India 10Y G-Sec Yield, India CPI (YoY) *(FRED API key required for macro metrics)*
  - **Global Benchmarks**: Fed Funds Rate, US VIX, DXY, US 10Y Yield, Brent Crude, Gold, S&P 500, NASDAQ
- **Direction-Calibrated Signals & Tooltips**: Color badges (`BULLISH`, `BEARISH`, `DEFENSIVE`, `LOW COST`) and viewport-aware hover tooltips.
- *See [mf_market_metrics_reference.md](documentation/ideas/mf_market_metrics_reference.md) for the mathematical decision map.*

---

### 3. 🔍 Fund Research, Screener & Analytics
- **Complete Indian Universe:** Browse and evaluate **~2,300 Open-Ended Direct Growth Mutual Funds and ETFs** with real-time AMFI cache fallbacks. Close-Ended, Interval, Regular, IDCW, and dividend options are excluded platform-wide.
- **6-Pillar Quantitative Scoring Engine (0–100):** Evaluates Performance (30%), Risk & Stability (25%), Cost Efficiency (15%), Portfolio Composition (15%), Manager Quality (15%), and Debt Quality (10% for hybrid/debt).
- **Personalized Ranking Scorecard & Factor Breakdown:**
  - **Strategy Archetypes:** ⚖️ *Balanced (Default 25/25/25/25)*, 🛡️ *Capital Preservation (Stability 45%)*, 🎯 *Long-Term Compounder (Consistency 45%)*, 🚀 *Momentum / High Growth (Recency 45%)*, and 💰 *Cost Optimizer (Low Fee 45%)*.
  - **Dynamic Weight Sliders:** Interactive range sliders with auto-normalization to 100% and real-time score recalculation.
  - **Visual 4-Factor Breakdown Cards:** Dedicated cards for Stability, Consistency, Recency, and Cost (plus Quality & Governance) detailing sub-metrics, scores, and exact point contributions.
  - **Multi-Factor Radar Benchmark Comparison:** Interactive spider/radar chart benchmarking the fund across 5 dimensions against SEBI category averages.
  - **Mathematical Transparency:** Step-by-step arithmetic substitution card and stacked color contribution bar showing live math aggregation: `Personalized Score = Σ(Weight_i × Score_i) − Red Flag Penalties`.
- **Advanced Quantitative Analysis Suite (`#tab-advanced`):**
  - **Technical Pattern & Divergence Scanner:** Active 50/200 DMA Golden/Death Cross with active days tracker, RSI Regular Bullish/Bearish Divergence, MACD Momentum, ADX Trend Strength, and live Market Regime classification.
  - **Parametric & Empirical VaR/CVaR Matrix:** Multi-horizon (1D, 5D, 21D, 252D) risk evaluation comparing Empirical Historical vs. Gaussian Parametric VaR/CVaR with Fat-Tail Kurtosis Risk Gap.
  - **16-Model Time-Series, ML & Deep Learning Forecasting:** ARIMA($p,d,q$), SARIMA (Seasonal), Facebook Prophet, ETS, Linear, Momentum, ARIMAX, XGBoost ML, LightGBM Regressor, LSTM Sequence Net, Bi-LSTM, GRU, Self-Attention Transformer, and Inverse-MAPE Weighted Ensemble with 7D to 365D (1 Year) horizons.
  - **🧪 StrategyLab™ Strategy Backtester Engine:** Simulates 10 quantitative, technical, ML, deep learning, and systematic DCA strategies (Buy & Hold, SMA Cross, RSI Mean-Reversion, MACD Momentum, Bollinger Dip Buy, XGBoost ML, LightGBM ML, LSTM Neural Trend, Multi-Model Ensemble, Monthly SIP) directly on historical NAV with Top Strategy Hero Recommendation, interactive Plotly equity growth chart, and leaderboard table.
- **Macro Stress Testing:** Simulates fund behavior across 6 major historical market crashes (2024–25 Tariff Shock, COVID-19 Crash, 2022 Rate Hikes, 2018 IL&FS, 2015 China Slowdown, 2008 GFC).
- **Market-Regime Analysis:** Evaluates performance across 5 economic cycles (Bull, Bear, Sideways, High Inflation, Rate Cut).
- **Quartile & Peer Rankings:** Dynamic sub-category peer ranking computed on-the-fly.
- *See [SCORING_MODEL.md](documentation/SCORING_MODEL.md), [SCREENER.md](documentation/SCREENER.md), and [ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md).*

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

### 6. 🧮 Financial Calculators & Research Suite (18 Tools)
- **Growth & Wealth**: SIP, Lumpsum, SWP, Step-Up SIP, STP, XIRR, and Rolling Returns.
- **Research & Peer Comparison**: Research Report Generator, Peer Comparison Calculator, Fund Comparison, Overlap Checker, AMC Comparison, and Category Comparison.
- **Life Event Planning**: Goal Planner, Retirement Planner (25x FIRE rule & 4% SWR), Child Education Planner, and SWP Pension Longevity.
- **Tax & Wealth**: Capital Gains Tax Calculator (FY 2025-26 rules) and Net Worth Tracker.
- *See [CALCULATORS.md](documentation/CALCULATORS.md).*

---

### 7. 🛡️ Data Status Dashboard
- **Real-time Pipeline Transparency**: See coverage %, last pipeline run time, and weekly/monthly batch schedule.
- **7-Day Activity Chart**: Bar chart showing how many funds were refreshed each day this week.
- **Monthly Portfolio Data**: Holdings coverage, sector allocation coverage, market-cap breakdown coverage, AUM snapshot months, and data source breakdown (Morningstar / finapi / yahoo).
- **Score & Rank Trend Coverage**: Weeks of score trend data available, latest snapshot date.
- **Benchmark Status Table**: Freshness and row counts for all 51 benchmark indices.
- **Coverage Metrics**: NAV coverage, screener snapshot coverage, model score coverage, trailing return coverage, holdings/sector/cap coverage.
- Accessible at `/data-status/` — linked from the Explore section of the sidebar.

---

## 🔐 User Accounts & Authentication

| Feature | Status |
|---|---|
| User registration (email + password) | ✅ Working |
| Email verification on sign-up | ✅ Working (console in dev, SMTP in prod) |
| Login with rate limiting (5 attempts/min) | ✅ Working |
| Auto-activation of stuck inactive accounts | ✅ Working (recovers from SMTP failures) |
| Forgot password / self-service password reset | ✅ Working (uses branded page, not Django admin) |
| Change password in User Settings | ✅ Working |
| Logout (POST-based, Django 5.x compatible) | ✅ Working |
| Personal API key storage (FRED, etc.) | ✅ Working (encrypted in user settings) |

> **Email delivery in production:** Set `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in Render's environment to enable real email. Without them, emails are logged to Render's console. See [DEPLOYMENT.md](documentation/DEPLOYMENT.md#phase-6--configure-email-optional-when-ready).

---

## 🛠️ Technology Stack

| Layer | Technologies Used |
|---|---|
| **Backend Core** | Python 3.11+, Django 5.x |
| **Data & Analytics** | Pandas, NumPy, SciPy, Statsmodels, Scikit-Learn, Arch (GARCH) |
| **Visualization** | Plotly.js, Plotly Python, Canvas PDF.js |
| **PDF Generation** | Google Chrome Headless, Django HTML/CSS Paged Media |
| **Frontend UI** | Django Templates, Vanilla CSS (Custom Design System), Vanilla JS, HTMX |
| **Database** | SQLite (dev) / CockroachDB -- PostgreSQL-compatible (production, free 10 GB) / PostgreSQL 16 (Docker dev) |
| **Containerization** | Docker + Docker Compose (multi-stage build; PostgreSQL 16 service for local dev) |
| **Auth & Email** | Django built-in auth, rate-limited login, email verification, SMTP (Sender.net / Gmail) |
| **External Data APIs** | mfapi.in (incremental NAV), captnemo.in / Kuvera (metadata), yfinance + yahooquery (equity benchmarks & portfolio fallback), FRED API (macro), AMFI NAVAll.txt (8-col format), World Bank API (CPI), Morningstar REST API (portfolio holdings — plain HTTP) |
| **Deployment** | Render (web service, free tier), GitHub Actions (weekly pipeline every 6h + monthly portfolio pipeline on 5th, free for public repos) |
| **Data Distribution** | Kaggle dataset (manual publish via `push_to_kaggle` command or Actions workflow) |

---

## Local Setup & Development Quickstart

Two options: **native Python** (SQLite, fast for UI work) or **Docker** (PostgreSQL 16, matches production).

### Option A: Native Python (SQLite)

#### Prerequisites
- Python 3.11 or higher
- Git
- Google Chrome (installed at standard OS location for PDF generation)

#### Installation Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/amansingh2116/MutualFundAnalysis.git
   cd MutualFundAnalysis
   ```

2. **Create and Activate Virtual Environment**:
   ```bash
   python -m venv venv
   # Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   ```bash
   cp .env.example .env
   # Edit .env -- at minimum set SECRET_KEY
   # DJANGO_SETTINGS_MODULE=config.settings.dev
   # SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(50))">
   ```
   > **Email in local dev:** Emails are printed to the terminal console -- no SMTP provider needed.

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

### Option B: Docker + PostgreSQL 16 (Recommended for production-accurate testing)

#### Prerequisites
- Docker Desktop installed and running

#### Steps

1. **Clone and configure**:
   ```bash
   git clone https://github.com/amansingh2116/MutualFundAnalysis.git
   cd MutualFundAnalysis
   cp .env.example .env   # Edit SECRET_KEY at minimum
   ```

2. **Build and start all services** (PostgreSQL 16 + Django web + django-q2 worker):
   ```bash
   docker compose up --build
   ```

3. **First-time database setup** (run once in a new terminal while containers are running):
   ```bash
   docker compose run --rm web python manage.py migrate
   docker compose run --rm web python manage.py createsuperuser
   docker compose run --rm web python manage.py build_scheme_master
   ```

4. **Access the app** at http://localhost:8000

5. **(Optional) Populate with real data** from production:
   ```bash
   # Requires DATABASE_URL env var pointing to CockroachDB
   docker compose run --rm web python manage.py sync_from_prod
   ```

> **Subsequent starts:** `docker compose up` (no rebuild needed unless requirements.txt changes). DB data persists across restarts in a named Docker volume. Use `docker compose down -v` to wipe and start fresh.

## 🔄 Data Pipeline — Automated Weekly + Monthly

Two automated pipelines keep the database fresh via GitHub Actions (free for public repos).

### Weekly Pipeline (every 6 hours, self-completing)

```
Run 1  (~Day 1, +0h):   Processes 250–350 stale funds → hits 5h 10min limit → exits
Run 2  (~Day 1, +6h):   Resumes from next stale fund → processes another 250–350
Run 3–7 (~Day 2–3):     Continues until ALL ~2,300 funds are refreshed ✅
Runs 8+  (Day 3–7):     Finds 0 stale funds → completes in < 5 minutes 💤
Next Monday:            7-day window expires → automatic full restart 🔄
```

> **Public repo = FREE unlimited GitHub Actions minutes.** 4 runs/day × 7 days × 52 weeks = 1,456 invocations/year; completely free for public repositories.

### Monthly Pipeline (5th of each month at 3 AM UTC)

Handles SEBI-mandated monthly portfolio disclosures and point-in-time AUM snapshots:

```
1. update_nifty_caplist      — refresh Nifty cap classification list (NSE)
2. ingest_holdings           — portfolio holdings (Morningstar REST → yahooquery fallback)
3. ingest_aum_snapshots      — point-in-time AUM for all schemes
4. ingest_industry_inflows   — AMFI category-level net inflows (Capital Flows widget)
5. ingest_score_trend        — weekly fund score & rank snapshot
```

### Key management commands:

```bash
# ─── Weekly commands ─────────────────────────────────────────────────────────
# Sync fund universe (AMFI master list)
python manage.py build_scheme_master

# Ingest benchmark NAVs (51 indices, incremental)
python manage.py ingest_benchmarks

# Compute benchmark return snapshots
python manage.py populate_benchmark_returns

# Full fund pipeline — NAV + metadata + analytics + scoring
python manage.py populate_screener

# Resume (skips funds updated in the last 7 days — same as pipeline uses)
python manage.py populate_screener --resume --resume-hours=167

# Exits gracefully before GitHub Actions 6h hard cap
python manage.py populate_screener --time-limit-minutes=310

# Weekly score & rank trend snapshot (keyed by week, idempotent)
python manage.py ingest_score_trend

# ─── Monthly commands ────────────────────────────────────────────────────────
# Portfolio holdings (Morningstar REST → yahooquery fallback, no browser)
python manage.py ingest_holdings --source auto --resume

# AUM snapshots (point-in-time per scheme per month)
python manage.py ingest_aum_snapshots

# AMFI category-level net inflows (last 3 months)
python manage.py ingest_industry_inflows --months 3

# ─── One-time setup ──────────────────────────────────────────────────────────
# Populate morningstar_id (ISIN → SecId mapping) — needs Chrome, run once
python manage.py build_mstar_ids

# ─── Sync Learn section (PDF guides and blog posts from Resources/) ─────────
python manage.py sync_content
```

See [DATA_PIPELINE_AND_COMMANDS.md](documentation/DATA_PIPELINE_AND_COMMANDS.md) for full flag reference and initial setup workflow.

---

## 📚 Technical Documentation Directory

| Document | Contents |
|---|---|
| [DEPLOYMENT.md](documentation/DEPLOYMENT.md) | Full production deployment guide -- Render + CockroachDB + GitHub Actions |
| [DATA_PIPELINE_AND_COMMANDS.md](documentation/DATA_PIPELINE_AND_COMMANDS.md) | All management commands (weekly + monthly), pipeline diagram, Docker setup, Kaggle publish |
| [pipeline.md](documentation/pipeline.md) | Quick-reference: weekly vs monthly schedule, ingest_holdings source hierarchy, command flags |
| [docker/README.md](docker/README.md) | Docker Compose quick reference and troubleshooting |
| [INSTITUTIONAL_REPORT.md](documentation/INSTITUTIONAL_REPORT.md) | Institutional PDF Research Report engine |
| [SCREENER.md](documentation/SCREENER.md) | Fund Screener user & developer guide |
| [ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md) | Technical indicators, ML forecasting & risk models |
| [CALCULATORS.md](documentation/CALCULATORS.md) | Guide for all 18 financial calculators |
| [SCORING_MODEL.md](documentation/SCORING_MODEL.md) | 6-pillar 100-point fund scoring methodology |
| [backtester_analysis.md](documentation/backtester_analysis.md) | Strategy Backtester V2 specs & user guide |
| [PROJECT_CONTEXT.md](documentation/PROJECT_CONTEXT.md) | Architecture & repository directory context |

---

## ⚖️ License & Disclaimer

Distributed under a **Proprietary Non-Commercial License**. See [`LICENSE`](LICENSE) for details.

Key restrictions: **No commercial use, no redistribution, no AI model training on this code.**  
Personal study, educational use, and pull-request contributions are permitted.

*Mutual fund investments are subject to market risks. Read all scheme-related documents carefully before investing. Historical performance and quantitative model scores do not guarantee future returns.*
