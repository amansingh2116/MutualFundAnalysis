# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, and backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns. Any recommendation feature must clearly expose its assumptions, limitations, and the need for qualified professional advice where appropriate.

---

## Features

### 🔍 Fund Research & Discovery
- Browse and search across **14,000+ AMFI-registered schemes** with real-time AMFI cache fallback
- Full **fund detail pages** with NAV history, metadata, and analytics
- **Calendar-year returns**, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max)
- **Rolling return distributions** with win rates, medians, and min/max ranges
- **Risk metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios
- **Holdings, sector allocation, and asset allocation** from Morningstar
- **Scorecard System**: 100-point dynamic scoring model across Performance, Risk, Cost, and Composition pillars (see `docs/SCORING_MODEL.md`)

### 💼 Portfolio Analysis
- Upload CAS (Consolidated Account Statement) Excel/CSV files, or enter transactions **manually**
- **Fuzzy matching** of fund names from CAS to AMFI codes
- Per-fund and portfolio-level **XIRR** using SciPy root-finding
- **Portfolio value journey** chart (weekly resolution, NAV-adjusted)
- **Concentration score** using Herfindahl-Hirschman Index (HHI)
- **Portfolio turnover** analysis (buy activity in last 12 months)
- **Blended benchmark comparison** with custom index weights

### 📊 Tactical Backtester Engine
- Build a custom **investment plan** with per-fund SIP schedules, lumpsum events, and sell rules
- Simulate against **historical NAV data** with full transaction ledger using rigorous unitized NAV accounting
- Five strategy variants: **Base Plan, Trend Filter (12-month), MA Filter (10-month), Volatility Control, Composite Signal**
- Tactical overlays automatically redirect equity SIPs to a **debt parking fund** when macroeconomic/momentum signals deteriorate
- Per-strategy metrics: CAGR, XIRR, Final Corpus, Max Drawdown, Sharpe, Sortino, Volatility
- **Rebalancing Engine**: Annual or drift-threshold based asset reallocation
- See `docs/backtester_analysis.md` for full mathematical and architectural details.

### 🎯 Recommendations & Risk Profiling
- Risk-profiling **questionnaire** (experience, horizon, loss tolerance, goals)
- Maps user profile to optimal Equity/Debt/Gold allocation ratios
- Selects top funds in each required SEBI category using the 100-point Scoring Model
- Direct one-click integration to run a **5-year historical backtest** on the suggested portfolio

### 🧮 Financial Calculators
- **SIP** and **Step-Up SIP** future value
- **Lumpsum** return calculator
- **SWP** (Systematic Withdrawal Plan) depletion analysis
- **XIRR** from manually entered cash flows
- **Goal planner** — how much SIP needed to reach a target corpus

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x (Python 3.11+) |
| Analytics | Pandas, NumPy, SciPy, statsmodels |
| Charts | Plotly (client-side JS) |
| Frontend | Django Templates, vanilla CSS, vanilla JS |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Background tasks | django-q2 |
| Static files | WhiteNoise |
| Deployment | Render.com |

---

## Data Sources

All sources are free and unauthenticated.

| Source | Use |
|---|---|
| **AMFI** | Scheme universe, latest NAVs, search index |
| **mfapi.in** | Full historical NAV series per scheme |
| **captnemo API** | Rich metadata (expense ratio, AUM, inception date) |
| **mstarpy** | Holdings, sector allocation, asset allocation |
| **NSE India API** | Live and historical benchmark index data |
| **yfinance** | Fallback for benchmark data and fund ticker resolution |

---

## Project Structure

```
MutualFundAnalysis/
├── manage.py
├── requirements.txt
├── .env.example             ← copy to .env and fill secrets
├── render.yaml              ← Render.com deployment config
│
├── config/                  ← Django project config
│
├── apps/
│   ├── core/                ← BaseModel
│   ├── funds/               ← Scheme master, NAV history, runtime snapshot
│   ├── analytics/           ← Analytics engine, 100-point Scorer
│   ├── benchmarks/          ← BenchmarkIndex, BenchmarkNAV
│   ├── calculators/         ← Stateless financial calculators
│   ├── recommendations/     ← Risk profiling questionnaire
│   └── portfolio/           ← Portfolio upload, XIRR, backtester engine
│
├── adapters/                ← External API adapters
├── templates/               ← Django HTML templates
├── static/                  ← CSS and JS files
├── notebooks/               ← Jupyter notebooks and research files
│
└── docs/                    ← Architecture documentation
    ├── backtester_analysis.md ← Backtester design, math, and API reference
    ├── SCORING_MODEL.md       ← Fund scoring model design
    ├── recommendation_engine.md ← Recommendation engine logic
    └── UI_TOOLTIPS.md         ← Info-button tooltip system reference
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Git

### 1. Clone and set up environment

```bash
git clone https://github.com/amansingh2116/MutualFundAnalysis.git
cd MutualFundAnalysis
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY, DEBUG=True for local dev
```

### 3. Initialise the database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Load scheme master data (one-time)

```bash
# Build the scheme registry from AMFI NAVAll.txt (~14,000 schemes)
python manage.py build_scheme_master

# Fetch benchmark index history (Nifty 50, Sensex, etc.)
python manage.py ingest_benchmarks
```

> **Note:** Fund detail data (NAV history, metadata, holdings) is fetched **on-demand** when a user visits a fund page. You do not need to bulk-ingest all NAV data.

### 5. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`

---

## Deployment (Render.com)

See [`DEPLOYMENT.md`](DEPLOYMENT.md) and [`render.yaml`](render.yaml) for full production deployment instructions.
