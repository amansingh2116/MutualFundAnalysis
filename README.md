# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, and backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns. Any recommendation feature must clearly expose its assumptions, limitations, and the need for qualified professional advice where appropriate.

---

## 🌟 Features & Working Details

### 🔍 Fund Research & Discovery
- Browse and search across **14,000+ AMFI-registered schemes** with real-time AMFI cache fallback.
- Full **fund detail pages** with NAV history, metadata, and analytics.
- **Performance**: Calendar-year returns, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max).
- **Risk Metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, and **Quarterly Performance Analysis (Upside/Downside)**.
- **Rolling return distributions** with win rates, medians, and min/max ranges.
- **Composition**: Holdings, sector allocation, and asset allocation from Morningstar.
- **Scorecard System**: 100-point dynamic scoring model across Performance, Risk, Cost, and Composition pillars (see `docs/SCORING_MODEL.md`).
- **Peer comparison**: Scored India-focused peer matching by fund fingerprint, plan type, Direct/Regular flag, category, sector/theme, index group, FoF exposure, and AUM ranking (see `docs/PEER_MATCHING.md`).

### 💼 Portfolio Analysis
- Upload CAS (Consolidated Account Statement) Excel/CSV files, or enter transactions **manually**.
- **Fuzzy matching** of fund names from CAS to AMFI codes.
- Per-fund and portfolio-level **XIRR** using SciPy root-finding.
- **Blended benchmark comparison**: Automatically aggregates your portfolio's underlying benchmarks and accurately weights them by your actual capital allocation.
- **Concentration score** using Herfindahl-Hirschman Index (HHI) and **Portfolio turnover** analysis.

### 📊 Tactical Backtester Engine
- Build a custom **investment plan** with per-fund SIP schedules, lumpsum events, and sell rules.
- Simulate against **historical NAV data** with full transaction ledger using rigorous unitized NAV accounting.
- Five strategy variants: **Base Plan, Trend Filter (12-month), MA Filter (10-month), Volatility Control, Composite Signal**.
- Tactical overlays automatically redirect equity SIPs to a **debt parking fund** when macroeconomic/momentum signals deteriorate.
- Per-strategy metrics: CAGR, XIRR, Final Corpus, Max Drawdown, Sharpe, Sortino, Volatility.
- See `docs/backtester_analysis.md` for full mathematical and architectural details.

### 🎯 Recommendations & Risk Profiling
- Risk-profiling **questionnaire** (experience, horizon, loss tolerance, goals) mapping to optimal Equity/Debt/Gold allocation ratios.
- Selects top funds in each required SEBI category using the 100-point Scoring Model.
- Direct one-click integration to run a **5-year historical backtest** on the suggested portfolio.

### 🧮 Financial Calculators
- **SIP** and **Step-Up SIP** future value, **Lumpsum** return calculator, **SWP** depletion analysis, **XIRR** cash flows, and **Goal planner**.

---

## ⚙️ How It Works (Under the Hood)
1. **Data Ingestion (`adapters/`)**: The system fetches live scheme data, historical NAVs, and metadata completely free of cost by connecting to unauthenticated APIs including AMFI, mfapi.in, captnemo, Morningstar (via mstarpy), and Yahoo Finance.
2. **Analytics Engine (`apps/analytics/`)**: Real-time mathematical computations (CAGR, Beta, Sharpe, Rolling returns) are heavily vectorized using **Pandas** and **NumPy** to ensure fast response times directly on the server side.
3. **Runtime Assembly (`apps/funds/runtime.py`)**: When you load a fund, the runtime snapshot intelligently aggregates database historical data and live adapter data, filling missing gaps dynamically before rendering the HTML template.
4. **Peer Discovery (`apps/funds/peers.py`)**: The peer tab uses a scored matcher that works even when SEBI category data is missing by fingerprinting scheme names and basic metadata.
5. **Interactive UI (`static/js/`)**: The frontend uses Vanilla JavaScript and **Plotly** to render complex financial charts without heavy JS frameworks, keeping the application lightweight.

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

---

## 📂 Project Structure & File Details

```text
MutualFundAnalysis/
├── manage.py                ← Django command-line utility for administrative tasks
├── requirements.txt         ← Project Python dependencies
├── render.yaml              ← Render.com Infrastructure-as-Code deployment config
│
├── config/                  ← Main Django configuration
│   ├── settings/            ← Shared, development, and production settings
│   └── urls.py              ← Global URL routing table
│
├── apps/                    ← Django Application Modules
│   ├── core/                ← Base models, mixins, and shared utilities
│   ├── funds/               ← Scheme master, NAV history, runtime snapshots, peer matching, tests
│   ├── analytics/           ← Core financial math engine (`engine.py`, rolling returns, metrics)
│   ├── benchmarks/          ← Benchmark index registry and NAV history tracking
│   ├── calculators/         ← Stateless financial logic for SIP, Lumpsum, SWP, Goals
│   ├── recommendations/     ← Risk profiling questionnaire and fund suggestion engine
│   └── portfolio/           ← CAS parsing, XIRR processing, and the Backtester simulation engine
│
├── adapters/                ← Third-party API integrations (AMFI, Morningstar, Yahoo)
├── templates/               ← Django HTML templates (UI layout)
├── static/                  ← Vanilla CSS styles and JS scripts (Plotly charts, Tooltips)
│
└── docs/                    ← Deep-dive technical documentation
    ├── backtester_analysis.md ← Backtester math, simulation rules, and API payload reference
    ├── PEER_MATCHING.md       ← Peer comparison matching rules and validation notes
    ├── SCORING_MODEL.md       ← Comprehensive rules for the 100-point Fund scoring model
    └── DEPLOYMENT.md          ← Original deployment reference documentation
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

# Create Virtual Environment
python -m venv venv

# Activate Virtual Environment (Windows)
venv\Scripts\activate
# Activate Virtual Environment (macOS/Linux)
source venv/bin/activate

# Install Dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
```
Edit the `.env` file to set your `SECRET_KEY` and ensure `DEBUG=True` for local development.

### 3. Initialize the Database & Admin User
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Load Scheme Master Data
```bash
# Build the scheme registry from AMFI (~14,000 schemes)
python manage.py build_scheme_master

# Fetch benchmark index history
python manage.py ingest_benchmarks
```
> **Note:** Fund detail data (NAV history, metadata, holdings) is fetched **on-demand** when a user visits a fund page. You do not need to bulk-ingest all NAV data locally to run the app.

### 5. Refresh the Fund Screener
The screener uses persisted snapshots so filtering, sorting, and CSV export stay fast. Refresh them manually after updating scheme metadata, NAV history, or analytics:

```bash
# Preview the target set
python manage.py refresh_screener_data --dry-run --direct-growth-only

# Refresh Direct Growth screener rows
python manage.py refresh_screener_data --direct-growth-only
```

Generate a top-funds CSV and standalone HTML performance reports:

```bash
python manage.py generate_screener_reports --top 10 --sort cagr_3y
```

Reports are written under `media/reports/fund_screener/YYYY-MM-DD/`. Supported sort values are `cagr_3y`, `rolling_3y`, `return_1y`, and `aum`.

### 6. Run the Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/funds/screener/` for the screener.

### 7. Run Tests
```powershell
$env:DEBUG='True'; python manage.py test apps.funds apps.analytics
```
If you run tests without overriding `DEBUG`, make sure `.env` uses a boolean such as `DEBUG=True` or `DEBUG=False`.

---

## 🚀 Deployment (Cloud via GitHub & Render)

To make the app searchable online, persist user data securely in the cloud, and automate daily database updates, follow these deployment steps:

### 1. Push to GitHub
Commit your local codebase and push it to a GitHub repository:
```bash
git add .
git commit -m "Ready for deployment"
git remote add origin https://github.com/YOUR_USERNAME/MutualFundAnalysis.git
git push -u origin main
```

### 2. Deploy on Render.com (Free Tier)
1. Create a free account at [Render.com](https://render.com).
2. Click **New +** and select **Blueprint**.
3. Connect your GitHub account and select your repository.
4. Render will automatically detect the included `render.yaml` file and spin up:
   * A **PostgreSQL Database** (ensuring user profiles/portfolios are securely saved).
   * A **Web Service** running your Django platform.

### 3. Automate Daily Data Fetching (GitHub Actions)
You must fetch new mutual fund NAVs daily so your platform stays up-to-date.
1. Create `.github/workflows/daily_update.yml` in your repository.
2. Add the following GitHub Action workflow to trigger Render to run the update every day at midnight (UTC):
```yaml
name: Daily NAV Database Update
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
3. Get your **Deploy Hook URL** from the Render dashboard (Web Service settings) and add it as a Repository Secret (`RENDER_DEPLOY_HOOK_URL`) in your GitHub repository.
