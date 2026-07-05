# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, and strategy backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns.

---

## 🌟 Features

### 🔍 Fund Research & Discovery
- Browse and search across **14,000+ AMFI-registered schemes** with real-time AMFI cache fallback
- Full **fund detail pages** with NAV history, metadata, and analytics
- **Performance**: Calendar-year returns, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max)
- **Risk Metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Quarterly Performance Analysis
- **Rolling return distributions** with win rates, medians, and min/max ranges
- **Composition**: Holdings, sector allocation, and asset allocation from Morningstar
- **Advanced Fund Screener**: Filter, sort, and export funds based on AUM, Expense Ratio, 1/3/5-year performance, Rolling Returns, Sharpe/Sortino, and Max Drawdown
- **Home Page Dashboard**: Benchmark Monitor, Category Return Meter, Top Performing Funds, Category Analysis, Browse by Category, Quartile Rankings
- **Scorecard System (v2)**: 100-point, 6-pillar dynamic scoring (Performance, Risk/Stability, Cost, Composition & Liquidity, Debt Quality, Manager Quality)
- **Compare Selected**: Multi-fund side-by-side comparison with overlapping Best/Worst Quarters, Sector Allocation, Risk vs Return scatter, and benchmark fallback
- **Peer Comparison**: Scored India-focused peer matching by fund fingerprint, plan type, category, sector/theme, and AUM ranking

### 💼 Portfolio Analysis
- Upload CAS (Consolidated Account Statement) files or enter transactions manually
- Fuzzy matching of fund names from CAS to AMFI codes
- Per-fund and portfolio-level **XIRR** using SciPy root-finding
- **Blended benchmark comparison** weighted by actual capital allocation
- **Concentration score** (Herfindahl-Hirschman Index) and Portfolio turnover analysis

### ⚗️ Strategy Backtester V2
- Build a custom portfolio with **mutual funds and/or NSE indices**
- Simulate **SIP, Step-Up SIP, Lumpsum, SWP (withdrawal), and Switch** investment strategies
- Attach **conditional triggers** to any rule:
  - NIFTY 50 PE Ratio, PB Ratio, Dividend Yield
  - Drawdown from ATH, Portfolio Drawdown
  - 200-DMA (Moving Average), RSI
  - Relative Valuation Ratio (any two assets)
  - Calendar Date (one-time or recurring)
- **Rebalancing** engine (annual or drift-threshold based)
- **Tax calculation**: STCG/LTCG with FIFO lot tracking, LTCG exemption
- **Inflation adjustment**: Manual rate or live World Bank India CPI data
- **Monte Carlo projection**: 200–1000 simulated future scenarios with percentile fan
- **Exit load** simulation per fund
- **Custom weighted benchmark** for comparison (e.g., 60% NIFTY 50 + 40% NIFTY NEXT 50)
- Full **Transaction Ledger** and **Trigger Attribution** tabs
- See `documentation/backtester_analysis.md` for the complete user and developer guide

### 🎯 Recommendations & Risk Profiling
- Risk-profiling questionnaire → optimal Equity/Debt/Gold allocation
- Top fund selection using the 100-point Scoring Model
- One-click backtest integration for suggested portfolios

### 🧮 Financial Calculators
- SIP, Step-Up SIP, Lumpsum, SWP calculators
- STP (Systematic Transfer Plan) Calculator
- XIRR, Goal Planner, Net Worth Calculator (25+ asset classes, 9 liability classes)
- **Rolling Return Calculator** (multi-fund, up to 5 funds with benchmarks and category averages)

---

## ⚙️ How It Works

1. **Data Ingestion (`adapters/`)**: Connects to AMFI, mfapi.in, captnemo, Morningstar (via mstarpy), and Yahoo Finance — all free, unauthenticated APIs
2. **Analytics Engine (`apps/analytics/`)**: Real-time computations (CAGR, Beta, Sharpe, Rolling returns) vectorized with Pandas and NumPy
3. **Runtime Assembly (`apps/funds/runtime.py`)**: Aggregates DB data + live adapter data on-demand when a fund page loads
4. **Peer Discovery (`apps/funds/peers.py`)**: Scored matcher using fund fingerprinting on scheme names and metadata
5. **Interactive UI (`static/js/`)**: Vanilla JavaScript + Plotly for complex financial charts — no heavy JS frameworks

---

## 🛠 Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x (Python 3.11+) |
| Analytics | Pandas, NumPy, SciPy, statsmodels |
| Charts | Plotly (client-side JS) |
| Frontend | Django Templates, Vanilla CSS, Vanilla JS |
| Database | SQLite (Dev) / PostgreSQL (Prod) |
| Background tasks | django-q2 |
| External data | wbgapi (World Bank CPI), nsepython (NSE PE/PB data) |

---

## 📂 Project Structure

```text
MutualFundAnalysis/
├── manage.py                    ← Django CLI utility
├── requirements.txt             ← Python dependencies
├── render.yaml                  ← Render.com deployment config
├── Procfile                     ← Process definitions for deployment
│
├── config/                      ← Django configuration
│   ├── settings/                ← Shared, development, and production settings
│   └── urls.py                  ← Global URL routing
│
├── apps/                        ← Django application modules
│   ├── core/                    ← Base models, mixins, shared utilities
│   ├── funds/                   ← Scheme master, NAV history, runtime snapshots, peer matching
│   ├── analytics/               ← Core financial math engine (CAGR, Beta, Sharpe, rolling returns)
│   ├── benchmarks/              ← Benchmark index registry and NAV history
│   ├── calculators/             ← Stateless financial logic (SIP, Lumpsum, SWP, Goals, Net Worth)
│   ├── recommendations/         ← Risk profiling questionnaire and fund suggestion engine
│   └── portfolio/               ← CAS parsing, XIRR, Backtester V2 simulation engine
│       └── services/
│           ├── backtester_v2.py ← Core simulation engine (~2,400 lines)
│           ├── pe_adapter.py    ← PE/PB/DivYield data fetcher with retry + SQLite cache
│           └── analytics.py     ← Portfolio analytics helpers
│
├── adapters/                    ← Third-party API integrations (AMFI, Morningstar, Yahoo)
├── templates/                   ← Django HTML templates
│   └── portfolio/
│       └── backtester.html      ← Strategy Backtester (single-file, ~3,150 lines)
├── static/                      ← CSS and JS static files
├── scripts/                     ← Utility and development scripts
│
└── documentation/               ← Technical documentation
    ├── backtester_analysis.md   ← ⭐ Full backtester user & developer guide
    ├── backtester_spec_v2.md    ← Original backtester V2 specification
    ├── backtester_pending_fixes.md ← Backtester known issues & implementation plan
    ├── DATA_PIPELINE_AND_COMMANDS.md ← Guide to running ingestion pipelines
    ├── PROJECT_CONTEXT.md       ← Full architectural overview for new developers
    ├── DEPLOYMENT.md            ← Render.com deployment and local setup
    ├── SCORING_MODEL.md         ← 100-point fund scoring model documentation
    ├── PEER_MATCHING.md         ← Peer comparison matching rules
    └── archive/                 ← Older specs and exploration documents
```

---

## 💻 Setup & Installation (Local Development)

### Prerequisites
- Python 3.11+
- Git

### 1. Clone and Set Up Environment
```bash
git clone https://github.com/amansingh2116/MutualFundAnalysis.git
cd MutualFundAnalysis

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```
Edit `.env` to set your `SECRET_KEY`. For local dev, ensure `DEBUG=True`.

### 3. Initialize Database & Admin User
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Load Scheme Master Data
```bash
# Build scheme registry from AMFI (~14,000 schemes) — required for fund search
python manage.py build_scheme_master

# Fetch benchmark index NAV history — required for index assets and benchmarks
python manage.py ingest_benchmarks
```

> **Note:** Fund detail data (NAV history, metadata, holdings) is fetched **on-demand** when a user visits a fund page. You do not need to bulk-ingest all NAV data locally.

### 5. Run the Server
```bash
python manage.py runserver
```
- Backtester: `http://127.0.0.1:8000/portfolio/backtester/`
- Fund Screener: `http://127.0.0.1:8000/funds/screener/`
- Admin: `http://127.0.0.1:8000/admin/`

### 6. Build Data Pipelines (Optional, for Screener & Dashboard)

The Fund Screener and Home Dashboard use pre-computed snapshots. Run these pipelines to populate them:

```bash
# 1. Fetch new market data for all benchmark indices
python manage.py ingest_benchmarks

# 2. Update index return statistics
python manage.py populate_benchmark_returns

# 3. Process all active funds — computes metrics, scores, and cascades into home dashboard
#    (Use --limit=100 for a quick test run)
python manage.py populate_screener --limit=100

# Full run (takes 30–60 min for ~2,500 direct-growth funds):
python manage.py populate_screener
```

### 7. Run Tests
```powershell
$env:DEBUG='True'; python manage.py test apps.funds apps.analytics
```

---

## 🚀 Deployment (Render.com)

### 1. Push to GitHub
```bash
git add .
git commit -m "your message"
git push origin main
```

### 2. Deploy on Render.com
1. Create account at [Render.com](https://render.com)
2. Click **New +** → **Blueprint**
3. Connect GitHub and select this repository
4. Render auto-detects `render.yaml` and spins up:
   - PostgreSQL database
   - Django web service

### 3. Automate Daily Updates (GitHub Actions)
Create `.github/workflows/daily_update.yml`:

```yaml
name: Daily NAV Update
on:
  schedule:
    - cron: '0 23 * * *'
  workflow_dispatch:

jobs:
  update-db:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Render Deploy Hook
        run: curl -X POST ${{ secrets.RENDER_DEPLOY_HOOK_URL }}
```

Add your **Deploy Hook URL** from the Render dashboard as a repository secret named `RENDER_DEPLOY_HOOK_URL`.

See `documentation/DEPLOYMENT.md` for detailed deployment instructions.

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [backtester_analysis.md](documentation/backtester_analysis.md) | ⭐ Complete backtester user guide, math reference, API docs, developer debugging |
| [backtester_pending_fixes.md](documentation/backtester_pending_fixes.md) | Known backtester issues and implementation plan |
| [DATA_PIPELINE_AND_COMMANDS.md](documentation/DATA_PIPELINE_AND_COMMANDS.md) | How to run all data ingestion and analytics pipelines |
| [PROJECT_CONTEXT.md](documentation/PROJECT_CONTEXT.md) | Full architectural overview for developers |
| [DEPLOYMENT.md](documentation/DEPLOYMENT.md) | Local setup and Render.com deployment guide |
| [SCORING_MODEL.md](documentation/SCORING_MODEL.md) | 100-point fund scoring model (6 pillars, all formulas) |
| [PEER_MATCHING.md](documentation/PEER_MATCHING.md) | Peer comparison matching algorithm |
