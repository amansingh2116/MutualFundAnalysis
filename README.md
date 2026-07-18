# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, and strategy backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns.

---

## Features

### Fund Research & Discovery
- Browse and search across **all Direct Growth mutual funds and all ETFs** (~2,000+ Direct Growth + ~300+ ETFs) with real-time AMFI cache fallback
- Full **fund detail pages** with NAV history, metadata, and analytics
- **Performance**: Calendar-year returns, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max)
- **Risk Metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Quarterly Performance Analysis
- **Rolling return distributions** with win rates, medians, and min/max ranges
- **Composition**: Holdings, sector allocation, and asset allocation from Morningstar
- **Advanced Fund Screener** *(login required)*: Filter, sort, and export across the complete Direct Growth + ETF universe on 30+ metrics — see [SCREENER.md](documentation/SCREENER.md) for a full feature guide
  - **30+ filterable metrics** across Returns, Risk, and Relative Stats (Sharpe, Sortino, Alpha, Beta, Tracking Error, Capture Ratios, ROMAD, and more)
  - **Returns vs Sub-Category** (Excess Category Returns) filters for 1Y, 3Y, 5Y, and 7Y — compare how much a fund beats or lags its sub-category average
  - **Median Rolling Returns** (1Y, 3Y, 5Y, 7Y) filter group with range sliders
  - **Category Peer Metrics** filter group: Avg Alpha, Beta, Expense Ratio, and Portfolio Turnover range filters
  - **Add Filters panel**: optional metrics added as interactive sidebar sections
  - **Active Filters popover**: click the filter badge to see, edit, or remove any active filter in-place — range metrics show editable inputs; categorical metrics show interactive multi-select dropdowns
  - **Saved Screens**: save any filter+view configuration by name; load, overwrite, or manage saved screens from the toolbar
  - **ⓘ Info tooltips** on every filter, every column header, and every metric in the Add Filters panel
- **Browse Funds Page** *(lite screener)*: Filter by AMC, Category, Risk, AUM range, Expense Ratio, and Returns. Dynamic page sizing (50/100/200/All), sortable columns, sticky fund-name and column headers, last-updated timestamp.
- **Quartile Rankings** *(Research → Quartile Rankings)*: Dynamic on-the-fly peer ranking — no stored rank data; ranks are computed live against the full sub-category cohort on every request
  - Filter by **Category Group** → **Sub-Category** cascade, with fund name search
  - Three **Metric Groups** toggle: **Returns** (1Y/3Y/5Y CAGR, 3Y/5Y Avg Rolling), **Volatility** (1Y/5Y Vol, 3Y Tracking Error, 1Y/5Y/SI Max Drawdown), **Ratios** (Sharpe, Sortino, Alpha, Beta, Info Ratio, Upside/Downside Capture)
  - Each cell shows value + **Q1–Q4 quartile badge** (colour-coded green/blue/amber/red) + numeric rank (e.g. `+12.3% Q2 15/67`)
  - Sticky column headers and sticky fund-name column while scrolling; sortable columns; pagination (50 per page)
  - ⓘ info tooltips on every metric column header explaining direction and interpretation
  - Ranks are always computed on the **full cohort** — searching/filtering only changes which rows are displayed, not the rank values
- **Home Page Dashboard**: Category Return Meter, Category Analysis, Quartile Rankings preview, and a comprehensive **Benchmark Monitor** (inspired by [AdvisorKhoj](https://www.advisorkhoj.com/mutual-funds-research/mutual-fund-benchmark-monitor))
  - **Customizable Top Bar** *(login required)*: Investors can manage and select which benchmarks and metrics are displayed in the ticker strip at the top of the homepage (saved per user). Default metrics are shown for guests.
  - **Educational Philosophy Cards**: Clear messaging that the platform focuses exclusively on Direct and Growth mutual funds and ETFs, with links to our blogs explaining why.
  - **Category Return Meter**: Rolling Returns table now includes 1Y/3Y/5Y Median and 1Y/3Y/5Y Minimum rolling return columns with ⓘ tooltips
  - **Category Analysis**: Avg and Median metric boxes for Alpha (3Y), Beta (3Y), Expense Ratio, and Portfolio Turnover — all wired to `CategorySnapshot` with ⓘ tooltips
  - **Category Analysis** correctly excludes funds with less than 1 year of NAV history from all aggregate metrics — young funds still appear in category fund lists but do not skew category averages, medians, or risk measures
  - **Benchmark Monitor**: Rolling Returns table includes 1Y/3Y/5Y Avg, Median, Min, and Max columns. The homepage dashboard displays cards for benchmarks saved in the user's Watchlist (with defaults for unauthenticated users).
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

### User Dashboard & Admin Panel
- **User Dashboard** (`/user/dashboard/`) *(login required)*: Centralized hub for logged-in users to view and jump into their saved data across the application.
  - View counts and quick links to Portfolios, Saved Strategies, and Watchlist Benchmarks.
  - Quick links to update Risk Profiling recommendation questions.
- **Admin Panel**: Simplified user account management for changing passwords, viewing username, and logging out directly from the sidebar.

### Financial Calculators
- **Calculator Hub** (`/calculators/`) — all 12 calculators accessible from a single dashboard
- **SIP Calculator**: Generic projections + historical NAV back-test with multi-fund comparison
  - Start date auto-aligns to the **earliest common inception date** across all selected funds
  - XIRR and Absolute Gain computed per fund with side-by-side comparison table
  - Cashflow table uses **fund names** (not generic labels)
- **Step-Up SIP Calculator**: Annual percentage step-up; same multi-fund alignment logic
- **Lumpsum Calculator**: Single one-time investment projection with historical NAV back-test
- **SWP Calculator** (Systematic Withdrawal Plan): Monthly withdrawal simulation from a corpus
- **STP Calculator** (Systematic Transfer Plan): Source/target fund growth modelling with XIRR
- **XIRR Calculator**: Manual irregular cashflow entry with annualised return computation
- **Goal Planner**: Inflation-adjusted target-corpus reverse-calculation (SIP and lumpsum alternatives)
- **Net Worth Calculator**: 25+ asset classes, 9 liability classes, Plotly donut chart, and Solvency Ratio
- **Rolling Returns Calculator**: Multi-fund (up to 5), custom benchmark override, rolling CAGR distribution
- **Fund Overlap Checker** (`/calculators/overlap/`): Stock-level portfolio overlap analysis (Minimum Weight Method)
  - **Venn Diagram** with exact portfolio weight percentages and count-based exclusive-circle values
  - **Tabbed holdings tables**: Common, Only in Fund A, Only in Fund B — using actual fund short names
  - **Weight bars**: Inline horizontal bars for at-a-glance weight comparison
- **Fund Comparison Calculator** (`/calculators/compare/`) — side-by-side comparison of up to 5 funds
  - Overview, Returns, Risk, and Portfolio tabs
  - Intelligently assigns **Best** badges: lower is better for expense ratio, volatility, beta, drawdown, turnover, top-10 concentration; higher is better for returns, Sharpe, Sortino, alpha, information ratio
  - No best badge for R², Tracking Error, Min SIP, Min Lumpsum (context-dependent)
- **Tax Calculator** (`/calculators/tax/`) — advanced FY 2025-26 capital gains calculator
  - **12 fund types** with correct STCG/LTCG rates and holding-period thresholds (Budget 2024/2025)
  - **Multi-fund portfolio**: add unlimited funds, each with purchase/sale dates, IDCW, exit load
  - **Loss set-off engine**: applies STCL/LTCL in optimal priority order (STCL offsets STCG first, then LTCG; LTCL offsets LTCG only)
  - **₹1.25L equity LTCG exemption** with stock LTCG offset tracking
  - **Carry-forward losses** from prior years
  - **Smart Alerts**: "Hold X more days to save ₹Y", unused loss carry-forward reminders, exemption tips
  - **Tax Loss Harvesting** tool: Savings Calculator, Priority Order ranker, Year-End Planner
  - **SIP FIFO Tax Calculator**: installment-by-installment FIFO breakdown for SIP redemptions
  - **Compare & Plan**: Growth vs IDCW, Fund Switch Tax (dates + fund type), Arbitrage vs Liquid
  - **ITR & Filing Guide**: ITR form selector, FY 2025-26 deadlines, Schedule CG walkthrough
- **ⓘ Info Button System** across calculators and the screener: Every key metric and input has a contextual tooltip powered by the shared `initInfoTooltips()` engine. Each calculator tab also includes a **Guide section** at the bottom explaining how the calculator works, when to use it, and how to interpret results. The screener extends this system to cover filter labels, Add Filters panel items, column headers, and dynamically-built sidebar widgets — see [UI_TOOLTIPS.md](documentation/UI_TOOLTIPS.md).

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
- **Blogs page** (`/learn/resources/blogs/`) — all articles displayed as sorted horizontal cards, filterable by tag
  - Cards marked `featured: true` in frontmatter display a ⭐ **Featured** gold badge and highlighted border
  - `featured: false` (or omitting the field) shows a normal card — any number of blogs can be featured simultaneously
- **Blog article reader** — rich reading experience with automatic Table of Contents:
  - **Cover image hero** — `thumbnail` from front matter is shown as a full-width banner at the top of the article body
  - **Desktop (> 960 px)**: sticky auto-generated ToC sidebar in a two-column grid layout
  - **Mobile / tablet (≤ 960 px)**: floating ☰ **Contents** pull-tab fixed to the vertical centre of the right edge; tapping slides a full-height drawer panel in from the right
    - Tapping the tab hides it and opens the panel; closing the panel (✕ button, backdrop tap, or Escape) slides it back and reveals the tab again
    - Scroll within the drawer is isolated — page content does not scroll while the drawer is open
  - ToC is built at runtime from the article's `h2`, `h3`, `h4` headings — no manual ToC needed in the markdown
  - **Dynamic active-heading highlight**: as you scroll the article the current section is highlighted in the ToC in real time (scroll-based, rAF-throttled — reliable in all directions)
  - Clicking / tapping any ToC item smooth-scrolls to that heading and highlights it immediately
- File-backed content workflow: PDF metadata via `Resources/PDF Guides/guides.json`; blog front matter in `Resources/Blogs/*.md`
- `sync_content` management command upserts `LearnPDFGuide` and `LearnBlogPost` DB records; syncs all fields including `featured` and `tags`
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
│   │   ├── blogs.html           ← Blog listing page (horizontal cards, featured badge, tag filter)
│   │   └── blog_detail.html     ← Blog article reader (cover hero, sticky ToC desktop, floating ToC drawer mobile, dynamic scroll highlight)
│   ├── calculators/
│   │   ├── hub.html             ← Calculator hub / landing page
│   │   ├── sip.html             ← SIP Calculator (generic + historical NAV)
│   │   ├── step_sip.html        ← Step-Up SIP Calculator
│   │   ├── lumpsum.html         ← Lumpsum Calculator
│   │   ├── swp.html             ← SWP Calculator
│   │   ├── stp.html             ← STP Calculator
│   │   ├── xirr.html            ← XIRR Calculator
│   │   ├── goal.html            ← Goal Planner
│   │   ├── net_worth.html       ← Net Worth Calculator
│   │   ├── rolling.html         ← Rolling Returns Calculator (up to 5 funds)
│   │   ├── overlap.html         ← Fund Overlap Checker (Venn diagram, tabs, weight bars)
│   │   ├── compare.html         ← Fund Comparison Calculator (up to 5 funds, Best badges)
│   │   └── tax.html             ← Tax Calculator FY 2025-26 (5 tabs, 12 fund types)
│   └── portfolio/
│       ├── backtester_hub.html  ← Backtester landing page (Build vs Saved Strategies)
│       ├── backtester.html      ← Strategy Backtester builder & results UI (~3,800 lines)
│       ├── strategies.html      ← Saved strategies list with search & multi-select compare
│       └── strategy_compare.html← Side-by-side strategy comparison page
├── static/                      ← CSS, JS, and icon static files
│   ├── css/
│   │   ├── main.css             ← Global styles, tooltip system, shared component styles
│   │   └── screener.css         ← Screener-specific styles (filter sidebar, popover, Add Filters panel)
│   └── js/
│       └── main.js              ← Global JS: initInfoTooltips(), shared utilities
├── scripts/                     ← Utility and development scripts
├── Resources/                   ← Learn content source files (PDF guides, markdown blogs, images)
│
└── documentation/               ← Technical documentation
    ├── SCREENER.md                  ← ⭐ Fund Screener feature guide & developer reference
    ├── CALCULATORS.md               ← ⭐ All 12 calculators — inputs, logic, output, audit notes
    ├── backtester_analysis.md       ← ⭐ Full backtester user & developer guide
    ├── backtester_spec_v2.md        ← Backtester V2 design specification
    ├── BACKTESTER_CHANGELOG.md      ← Backtester v2.x changes & pending work
    ├── DATA_PIPELINE_AND_COMMANDS.md ← Guide to running ingestion pipelines
    ├── PROJECT_CONTEXT.md           ← Full architectural overview for developers
    ├── DEPLOYMENT.md                ← Render.com deployment and local setup
    ├── LEARN_CONTENT.md             ← Learn Resources PDF/blog content workflow
    ├── SCORING_MODEL.md             ← 100-point fund scoring model documentation
    ├── PEER_MATCHING.md             ← Peer comparison matching algorithm
    ├── UI_TOOLTIPS.md               ← ⓘ Info button tooltip system — usage guide
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
- Calculator Hub: `http://127.0.0.1:8000/calculators/`
- Tax Calculator: `http://127.0.0.1:8000/calculators/tax/`
- Fund Comparison: `http://127.0.0.1:8000/calculators/compare/`
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

# Full run (takes several hours for ~3,000 direct-growth funds + ETFs)
# Use --resume to skip already-processed funds after an interruption
python manage.py populate_screener
python manage.py populate_screener --resume  # safe restart after Ctrl+C
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
| [SCREENER.md](documentation/SCREENER.md) | ⭐ Fund Screener — all features, JS architecture, saved screens, Active Filters popover |
| [CALCULATORS.md](documentation/CALCULATORS.md) | ⭐ All 12 calculators — inputs, calculation logic, outputs, audit notes |
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
