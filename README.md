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
- **Advanced Fund Screener**: Powerful data-grid to filter, sort, and export funds based on AUM, Expense Ratio, 1/3/5-year performance, Rolling Returns, Sharpe/Sortino ratios, and Max Drawdown.
- **Home Page Dashboard**: A comprehensive landing page with 6 distinct sections:
  - **Benchmark Monitor**: Live 1Y/3Y/5Y/YTD returns for major indices.
  - **Category Return Meter**: Interactive min-max-avg bar charts across fund categories.
  - **Top Performing Funds**: Extensible basket tabs (e.g., "Best Large Caps", "Low Cost Index Funds").
  - **Category Analysis**: Score distribution (Strong/Good/Fair/Weak), risk, and return stats per category.
  - **Browse by Category**: Mega-chip grid linked directly to screener filters.
  - **Quartile Rankings**: Dynamic Q1-Q4 rankings and percentile ranks for all funds in a category.
- **Scorecard System (v2)**: 100-point category-normalized, 6-pillar dynamic scoring model evaluating Performance, Risk/Stability, Cost, Composition & Liquidity, Debt Quality, and Manager Quality & Governance (see `documentation/SCORING_MODEL.md`). *Note: Currently, the system uses DB-only composition data (Option B) for speed, but will transition to full API scoring (Option A) in the future for maximum accuracy.*
- **Compare Selected**: Multi-select up to 5 funds across the Browse and Screener tabs to instantly send them to the **Compare Funds calculator**. Compare them side-by-side across Overview, Returns, Risk, and Portfolio tabs. Includes dynamic Overlapping Best/Worst Quarters analysis, Sector Allocation mini-donuts, Risk vs Return scatter plots, and intelligent benchmark fallback (using NIFTY COMPOSITE DEBT INDEX for debt funds).
- **Peer comparison**: Scored India-focused peer matching by fund fingerprint, plan type, Direct/Regular flag, category, sector/theme, index group, FoF exposure, and AUM ranking (see `documentation/PEER_MATCHING.md`).

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
- See `documentation/backtester_analysis.md` for full mathematical and architectural details.

### 🎯 Recommendations & Risk Profiling
- Risk-profiling **questionnaire** (experience, horizon, loss tolerance, goals) mapping to optimal Equity/Debt/Gold allocation ratios.
- Selects top funds in each required SEBI category using the 100-point Scoring Model.
- Direct one-click integration to run a **5-year historical backtest** on the suggested portfolio.

### 🧮 Financial Calculators
- **SIP**, **Step-Up SIP**, **Lumpsum**, and **SWP** calculators.
- **STP Calculator**: Systematic Transfer Plan to project transferring funds from a source to a target scheme over time.
- **XIRR** cash flows, and **Goal planner**.
- **Net Worth Calculator**: Comprehensive dynamic tool to tally 25+ asset classes (Cash, Investments, EPF/PPF/NPS, Real Estate) and 9 liability classes (Home/Auto Loans, CC). Features live Ploly donut charts, category progress bars, and solvency ratios.
- **Rolling Return Calculator** (multi-fund): Compare up to **5 mutual funds** simultaneously on a single rolling return chart.
  - Each fund is rendered with a distinct color; its benchmark is shown as a matching lighter dotted line on the same axis.
  - Category Averages are also displayed as horizontal dashed lines for deeper comparison.
  - Automatically deduplicates overlapping benchmarks (funds with the same benchmark share one benchmark line).
  - Optional **custom benchmark override** from a curated list of 30+ NIFTY/SENSEX/global indices — or use each fund's own default.
  - **Intelligent fallback**: Any benchmark without a confirmed Yahoo Finance ticker is automatically proxied. Equity/Hybrid funds fall back to Nifty 50, while Debt/Liquid funds fall back to NIFTY COMPOSITE DEBT INDEX, accompanied by a UI note.
  - Statistics table: Average, Median, Min, Max, **Volatility (Std Dev)**, and Negative-period % for every fund and its benchmark.
  - Return distribution table: Percentage of periods in each return bucket (Negative, 0–8%, 8–10%, 10–12%, 12–15%, 15–20%, >20%).
  - Date range is automatically pre-filled from the earliest fund inception date across all selected funds.

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
│   ├── calculators/         ← Stateless financial logic for SIP, Lumpsum, SWP, Goals, Net Worth
│   ├── recommendations/     ← Risk profiling questionnaire and fund suggestion engine
│   └── portfolio/           ← CAS parsing, XIRR processing, and the Backtester simulation engine
│
├── adapters/                ← Third-party API integrations (AMFI, Morningstar, Yahoo)
├── templates/               ← Django HTML templates (UI layout)
├── static/                  ← Vanilla CSS styles and JS scripts (Plotly charts, Tooltips)
│
└── documentation/           ← Deep-dive technical documentation
    ├── DATA_PIPELINE_AND_COMMANDS.md ← Master guide on how to run ingestions, analytics, and pipelines
    ├── PROJECT_CONTEXT.md   ← Full architectural overview for developers
    ├── DEPLOYMENT.md        ← Render.com deployment and local setup
    ├── backtester_analysis.md ← Backtester math, simulation rules, and API payload reference
    ├── PEER_MATCHING.md     ← Peer comparison matching rules and validation notes
    └── SCORING_MODEL.md     ← Comprehensive rules for the 100-point Fund scoring model
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

### 5. Build and Refresh the Data Pipelines (Screener & Home Dashboard)
The platform uses a denormalised snapshot architecture to power the **Advanced Fund Screener** and the **Home Dashboard** instantly, without running heavy live computations on thousands of funds. You must run these data pipelines to populate the platform's advanced features.

#### Pipeline 1: The Fund Screener & Analytics Pipeline
This pipeline processes all active mutual funds, fetches their historical NAVs, computes advanced metrics (Trailing, Rolling, and Calendar Returns, Sharpe, Sortino, Drawdown, etc.), and saves them to the `FundScreenerSnapshot` table.
```bash
# Process a small batch for testing:
python manage.py populate_screener --limit=100

# Process all direct-growth funds (~2,500 schemes).
# This respects API rate limits and handles gracefully falling back on errors.
python manage.py populate_screener

# Process without updating analytics or scores (fast update just for metadata)
python manage.py populate_screener --skip-analytics --skip-score
```
*Note: `populate_screener` will automatically trigger `populate_home_dashboard` at the end unless you pass `--skip-home-dashboard`.*

#### Pipeline 2: Benchmark Monitor Pipeline
This pipeline computes the calendar year returns, rolling returns (1Y, 3Y, 5Y), and risk metrics for all ingested benchmark indices (including NIFTY and newly added BSE indices like BSE 500, BSE Bankex, etc.)
```bash
# Fetch raw historical NAVs for all registered indices via Yahoo Finance/NSE
python manage.py ingest_benchmarks

# Compute returns and metrics, saving to the BenchmarkReturns table
python manage.py populate_benchmark_returns
```

#### Pipeline 3: Home Dashboard Aggregation
This pipeline aggregates the `FundScreenerSnapshot` data to generate category-level statistics (Average returns, Risk distribution, Score allocations) and calculates Quartile Rankings for every fund within its sub-category.
```bash
# Update category statistics and quartile rankings
python manage.py populate_home_dashboard
```

#### Understanding the Pipeline Workflow
For daily maintenance, the optimal execution order is:
1. `python manage.py ingest_benchmarks` (fetches new market data)
2. `python manage.py populate_benchmark_returns` (updates index stats)
3. `python manage.py populate_screener` (updates all fund metrics and cascades into home dashboard updates)

Generate a top-funds CSV and standalone HTML performance reports:

```bash
python manage.py generate_screener_reports --top 10 --sort cagr_3y
```

Reports are written under `media/reports/fund_screener/YYYY-MM-DD/`. Supported sort values are `cagr_3y`, `rolling_3y`, `return_1y`, `sharpe`, and `aum`.

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
