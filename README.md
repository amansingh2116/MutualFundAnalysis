# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, and strategy backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns.

---

## Features

### Fund Research & Discovery
- Browse and search across **14,000+ AMFI-registered schemes** with real-time AMFI cache fallback
- Full **fund detail pages** with NAV history, metadata, and analytics
- **Performance**: Calendar-year returns, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max)
- **Risk Metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Quarterly Performance Analysis
- **Rolling return distributions** with win rates, medians, and min/max ranges
- **Composition**: Holdings, sector allocation, and asset allocation from Morningstar
- **Advanced Fund Screener**: Filter, sort, and export by AUM, Expense Ratio, 1/3/5-year performance, Rolling Returns, Sharpe/Sortino, and Max Drawdown
- **Home Page Dashboard**: Benchmark Monitor, Category Return Meter, Top Performing Funds, Category Analysis, Browse by Category, Quartile Rankings
- **Scorecard System (v2)**: 100-point, 6-pillar dynamic scoring (Performance, Risk/Stability, Cost, Composition & Liquidity, Debt Quality, Manager Quality)
- **Compare Selected**: Multi-fund side-by-side comparison with overlapping Best/Worst Quarters, Sector Allocation, Risk vs Return scatter, and benchmark fallback
- **Peer Comparison**: Scored India-focused peer matching by fund fingerprint, plan type, category, sector/theme, and AUM ranking

### Portfolio Analysis
- Upload CAS (Consolidated Account Statement) files or enter transactions manually
- Fuzzy matching of fund names from CAS to AMFI codes
- Per-fund and portfolio-level **XIRR** using SciPy root-finding
- **Blended benchmark comparison** weighted by actual capital allocation
- **Concentration score** (Herfindahl-Hirschman Index) and Portfolio turnover analysis
- **Portfolio Dashboard tabs**: Overview, Analytics & Performance, Rebalancing & Alerts, **Overlap Matrix**, **Benchmark Analysis**
- **Inline Overlap Matrix** (dashboard tab): fetches stock-level overlap data via JSON API, renders an interactive Plotly heatmap + table without leaving the dashboard
- **Inline Benchmark Analysis** (dashboard tab): build a custom blended benchmark from any available NSE indices, compare portfolio vs default blend vs custom blend vs NIFTY 50 — equity curves, XIRR, Alpha, Beta, Sharpe, Sortino, Capture Ratios; all inline

### Strategy Backtester V2
- **Backtester Hub** landing page with two entry points: _Build & Test Strategy_ and _Saved Strategies_
- Build a custom portfolio with **mutual funds and/or NSE indices**
- Simulate **SIP, Step-Up SIP, Lumpsum, SWP (withdrawal), and Switch** investment strategies
- Attach **conditional triggers** to any rule:
  - Drawdown from ATH or Portfolio Drawdown (any fund/index via live search)
  - Moving Average (configurable period, default 200-day)
  - RSI (Relative Strength Index)
  - Relative Valuation Ratio (any two assets)
  - Calendar Date (one-time or recurring)
- **Rebalancing** engine: frequency-based (monthly/quarterly/annually) or drift-threshold based
- **Inflation adjustment**: Manual rate or live World Bank India CPI data (via wbgapi)
- **Tax Calculation**: User-configurable Equity STCG / LTCG / LTCG-exemption / Debt-slab rates applied to FIFO-cost redemptions; toggled via the settings panel
- **Monte Carlo projection**: 200–1000 simulated future scenarios with P10/P25/P50/P75/P90 fan
- **Results tabs**: Summary, Risk (drawdown/Sharpe/Sortino/Calmar/VaR), Consistency (equity chart, annual returns, monthly heatmap, rolling returns), Attribution, Adjusted Returns, Ledger, Monte Carlo
- **Rolling Return charts** (Consistency tab): Rolling Return Distribution (box plots per 3Y/5Y/7Y window, portfolio vs benchmark) and **Rolling Return Trend** (time-series of rolling CAGR, switchable 3Y/5Y/7Y)
- **Daily & Monthly Return Distribution histograms** with avg, volatility, best/worst month summary cards
- **Monthly Return Heatmap**: Year × Month color-coded grid (red/green)
- **Save & Load strategies**: Persist strategy plans to your account with cached result JSON; restore at any time
- **Saved Strategies list** (`/portfolio/strategies/`) with search and checkbox selection
- **Strategy Compare page**: Select 2–4 saved strategies and compare simulated outcomes side-by-side (equity curves, risk metrics, annual returns, rolling return summaries)
- Full **Transaction Ledger** and **Trigger Attribution** views
- See `documentation/backtester_analysis.md` for the complete user and developer guide

### Recommendations & Risk Profiling
- Risk-profiling questionnaire → optimal Equity/Debt/Gold allocation
- Top fund selection using the 100-point Scoring Model
- One-click backtest integration for suggested portfolios

### Financial Calculators
- **SIP Calculator**: Prospective projections + historical back-test mode with multi-fund comparison
  - Cashflow table uses **fund names** (not generic labels) for each fund's row
  - Start date auto-aligns to the **earliest common inception date** across all selected funds
  - XIRR and Absolute Gain computed per fund with side-by-side comparison table
- **Step-Up SIP Calculator**: Same as SIP with annual percentage step-up; same multi-fund alignment logic
- **Lumpsum Calculator**: Single one-time investment projection with historical NAV back-test
- **SWP Calculator**: Monthly withdrawal simulation from a corpus
- **STP Calculator** (Systematic Transfer Plan): Source/target fund with XIRR computation for both legs
- **XIRR Calculator**: Manual irregular cashflow entry with annualised return computation
- **Goal Planner**: Target-corpus reverse-calculation
- **Net Worth Calculator**: 25+ asset classes, 9 liability classes, Plotly donut chart, and **Solvency Ratio** with color-coded bar
- **Rolling Return Calculator**: Multi-fund (up to 5), custom benchmark override, color-coded chart with volatility stats
- **ⓘ Info Button System** across all calculators: Every key metric and input has a contextual tooltip (hover or click) powered by the shared `initInfoTooltips()` engine. Tooltips cover what the metric is, how to interpret it, benchmark ranges, and caveats — making the platform accessible for users with limited financial knowledge.

### Learn & Community
- **PDF Guides page** (`/learn/resources/guides/`) — three sections:
  - **Complete Mutual Fund Handbook** — always pinned at top, full-width featured card, not filterable
  - **Chapterwise Guides** — individual chapter PDFs with chapter number badges; tag-filterable
  - **Other Guides** — research, analysis, and investing guides; tag-filterable
- **In-app PDF Viewer** (`/learn/resources/guides/view/<slug>/`) — clicking any PDF card opens a full in-app viewer instead of the raw file:
  - Renders PDFs via **PDF.js** (canvas-based) — no raw file URL exposed in page HTML
  - **Toolbar**: zoom out/in (50% → 300% in steps), live zoom % display, go-to-page input with smooth scroll
  - **Keyboard shortcuts**: `Ctrl/Cmd++` zoom in, `Ctrl/Cmd+-` zoom out, `Enter` on page input to jump
  - **Pinch-to-zoom** on touch/mobile devices
  - **Security hardening**: right-click disabled on canvas, `Ctrl+S`/`Ctrl+P` blocked, `window.print()` replaced, drag-out prevented, `@media print` blanks the page
  - **Download button** — conditionally shown per guide based on `downloadable` field in `guides.json`; absent from DOM when not allowed
  - Raw serve endpoint (`/learn/resources/guides/serve/<slug>/`) responds with `no-store` cache headers and `X-Robots-Tag: noindex`
- **Tag filter bar** sits between the Handbook and the filterable sections; allowed tags: `investing`, `fundamentals`, `technicals`, `research`, `analysis`, `mutual funds`, `ipo`
- **Blogs page** (`/learn/resources/blogs/`) — featured hero article + grid of further posts, filterable by tag
- File-backed content workflow: PDF metadata via `Resources/PDF Guides/guides.json` (with `category`, `tags`, and `downloadable`); blog front matter in `Resources/Blogs/*.md`
- `sync_content` management command upserts `LearnPDFGuide` and `LearnBlogPost` DB records; syncs all fields including `downloadable` from `guides.json`
- **`downloadable` live override**: editing `guides.json` takes effect immediately in the viewer without re-running sync (manifest is always preferred over DB for this field)
- **Community page** (`/learn/community/`) — realistic static mockup. **Login required** — unauthenticated users are redirected to the login page with `?next=` redirect

---

## How It Works

1. **Data Ingestion (`adapters/`)**: Connects to AMFI, mfapi.in, captnemo, Morningstar (via mstarpy), and Yahoo Finance — all free, unauthenticated APIs
2. **Analytics Engine (`apps/analytics/`)**: Real-time computations (CAGR, Beta, Sharpe, Rolling returns) vectorized with Pandas and NumPy
3. **Runtime Assembly (`apps/funds/runtime.py`)**: Aggregates DB data + live adapter data on-demand when a fund page loads
4. **Peer Discovery (`apps/funds/peers.py`)**: Scored matcher using fund fingerprinting on scheme names and metadata
5. **Learn Content (`apps/core/content.py`)**: Reads local PDF/blog metadata from `Resources/`, renders markdown blogs, and exposes a `sync_content` command for admin-backed publishing
6. **Interactive UI**: Vanilla JavaScript + Plotly for complex financial charts — no heavy JS frameworks

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x (Python 3.11+) |
| Analytics | Pandas, NumPy, SciPy, statsmodels |
| Charts | Plotly.js (client-side) |
| Frontend | Django Templates, Vanilla CSS, Vanilla JS |
| Database | SQLite (Dev) / PostgreSQL (Prod) |
| Background tasks | django-q2 |
| External data | wbgapi (World Bank CPI), mfapi.in (NAV), Morningstar |

---

## Project Structure

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
│       ├── models.py            ← Portfolio, Transaction, SavedStrategy models
│       ├── views.py             ← API views including strategy save/load
│       └── services/
│           ├── backtester_v2.py ← Core simulation engine (~2,400 lines)
│           ├── pe_adapter.py    ← PE/PB/DivYield data adapter (deferred)
│           └── analytics.py     ← Portfolio analytics helpers
│
├── adapters/                    ← Third-party API integrations (AMFI, Morningstar, Yahoo)
├── templates/                   ← Django HTML templates
│   ├── learn/
│   │   ├── pdf_guides.html      ← PDF Guides listing page (3 sections + tag filter)
│   │   ├── pdf_viewer.html      ← In-app PDF viewer (PDF.js, zoom toolbar, download button)
│   │   ├── blogs.html           ← Blog listing page
│   │   └── blog_detail.html     ← Blog article reader
│   └── portfolio/
│       ├── backtester_hub.html  ← Backtester landing page (Build vs Saved Strategies)
│       ├── backtester.html      ← Strategy Backtester builder & results UI (~3,800 lines)
│       ├── strategies.html      ← Saved strategies list with search & multi-select compare
│       └── strategy_compare.html← Side-by-side strategy comparison page
├── static/                      ← CSS and JS static files
├── scripts/                     ← Utility and development scripts
├── Resources/                   ← Learn content source files (PDF guides, markdown blogs, local images)
│
└── documentation/               ← Technical documentation
    ├── backtester_analysis.md       ← ⭐ Full backtester user & developer guide
    ├── backtester_spec_v2.md        ← Backtester V2 design specification
    ├── BACKTESTER_CHANGELOG.md      ← Backtester v2.x changes & pending work
    ├── DATA_PIPELINE_AND_COMMANDS.md ← Guide to running ingestion pipelines
    ├── PROJECT_CONTEXT.md           ← Full architectural overview for developers
    ├── DEPLOYMENT.md                ← Render.com deployment and local setup
    ├── LEARN_CONTENT.md             ← Learn Resources PDF/blog content workflow
    ├── SCORING_MODEL.md             ← 100-point fund scoring model documentation
    ├── PEER_MATCHING.md             ← Peer comparison matching algorithm
    └── archive/                     ← Older specs and exploration documents
```

---

## Setup & Installation (Local Development)

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

### 5. Sync Learn Content
```bash
# Sync local Learn PDF guides and markdown blogs into admin-manageable records
python manage.py sync_content
```

Learn content lives in `Resources/PDF Guides/` and `Resources/Blogs/`. See `documentation/LEARN_CONTENT.md` for the metadata format.

> **Note:** Fund detail data (NAV history, metadata, holdings) is fetched **on-demand** when a user visits a fund page. You do not need to bulk-ingest all NAV data locally.

### 6. Run the Server
```bash
python manage.py runserver
```
- Backtester Hub: `http://127.0.0.1:8000/portfolio/backtester/`
- Strategy Builder: `http://127.0.0.1:8000/portfolio/backtester/build/`
- Saved Strategies: `http://127.0.0.1:8000/portfolio/strategies/`
- Fund Screener: `http://127.0.0.1:8000/funds/screener/`
- Admin: `http://127.0.0.1:8000/admin/`

### 7. Build Data Pipelines (Optional — for Screener & Dashboard)

The Fund Screener and Home Dashboard use pre-computed snapshots. Run these to populate them:

```bash
# 1. Fetch new market data for all benchmark indices
python manage.py ingest_benchmarks

# 2. Update index return statistics
python manage.py populate_benchmark_returns

# 3. Process all active funds — computes metrics, scores, and cascades into home dashboard
#    Use --limit=100 for a quick test run
python manage.py populate_screener --limit=100

# Full run (takes 30–60 min for ~2,500 direct-growth funds)
python manage.py populate_screener
```

### 8. Run Tests
```powershell
$env:DEBUG='True'; python manage.py test apps.funds apps.analytics
```

---

## Deployment (Render.com)

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

## Documentation

| Document | Description |
|----------|-------------|
| [backtester_analysis.md](documentation/backtester_analysis.md) | ⭐ Complete backtester user guide, math reference, API docs |
| [BACKTESTER_CHANGELOG.md](documentation/BACKTESTER_CHANGELOG.md) | v2.1 changes, removed features, and pending work |
| [backtester_spec_v2.md](documentation/backtester_spec_v2.md) | Original backtester V2 design specification |
| [DATA_PIPELINE_AND_COMMANDS.md](documentation/DATA_PIPELINE_AND_COMMANDS.md) | How to run all data ingestion pipelines |
| [PROJECT_CONTEXT.md](documentation/PROJECT_CONTEXT.md) | Full architectural overview for developers |
| [DEPLOYMENT.md](documentation/DEPLOYMENT.md) | Local setup and Render.com deployment guide |
| [LEARN_CONTENT.md](documentation/LEARN_CONTENT.md) | PDF Guides / Blogs / Community content workflow and format reference |
| [SCORING_MODEL.md](documentation/SCORING_MODEL.md) | 100-point fund scoring model (6 pillars, all formulas) |
| [PEER_MATCHING.md](documentation/PEER_MATCHING.md) | Peer comparison matching algorithm |
| [UI_TOOLTIPS.md](documentation/UI_TOOLTIPS.md) | ⓘ Info button tooltip system — usage guide for adding tooltips to any metric |

---

## License

MIT License — see [LICENSE](LICENSE).
