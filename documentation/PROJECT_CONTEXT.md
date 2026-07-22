# Mutual Fund Analysis Platform — Project Context

This document provides a comprehensive technical overview for developers and AI assistants inheriting this project. It covers architecture, implementation decisions, data science logic, and development patterns.

---

## 1. Project Overview & Tech Stack

**Purpose:** A full-featured mutual fund research, portfolio analysis, and backtesting platform built for Indian Mutual Funds. It aims to be a free, locally hostable alternative to platforms like ValueResearch or Morningstar.

**Tech Stack:**
- **Backend:** Django 5.x (Python 3.11+)
- **Analytics:** Pandas, NumPy, SciPy, statsmodels, scikit-learn
- **Frontend:** Django Templates, vanilla CSS, Plotly (client-side charts), vanilla JS
- **Database:** SQLite (dev) / PostgreSQL (prod via `dj-database-url`)
- **PDF Generation:** WeasyPrint (HTML to PDF, active in `apps/funds/report.py`)
- **Background Tasks:** django-q2 (ORM-backed, no Redis required)
- **Deployment:** Render.com (`render.yaml`)

---

## 2. Core Architecture: "On-Demand Runtime Loading"

The most crucial architectural decision is the **On-Demand Runtime Data Model**.

Indian mutual funds comprise over 14,000 active schemes. Downloading all NAV data daily is unnecessary for a browsing-first platform. Instead:

1. **Search (AMFI Cache):** When a user searches for a fund, the app fetches `NAVAll.txt` (~300 KB) from AMFI, caches it in memory for 6 hours, and uses it to power instant autocomplete.
2. **Fund Visit (Runtime Snapshot):** When a user visits a fund, `apps.funds.runtime.get_runtime_snapshot(scheme)` builds a short-lived in-memory snapshot:
   - **NAV:** Fetches historical NAV from mfapi.in (primary), mftool (fallback)
   - **Metadata:** Fetches from captnemo by ISIN; falls back to a same-fund sibling growth plan with a UI label indicating it's a reference value
   - **Holdings/Sectors:** Uses mstarpy (Morningstar) first, then yahooquery fallback after Yahoo ticker resolution
   - **Analytics:** Computes all metrics in memory — trailing returns, rolling returns, risk metrics, drawdown, etc.
3. **Peer Matching:** `apps.funds.peers.get_peer_matches(scheme)` fingerprints scheme names and basic metadata to rank peers even when `scheme_category` is empty.
4. **Portfolio & Benchmarks** are the only data fully persisted in the database.

### Runtime Data Rules (Never Break These)
- Do NOT bulk-ingest all schemes' NAV histories for normal browsing
- Do NOT fabricate exact-plan values. If a provider only has a sibling plan, label it as a reference value in the UI
- All HTTP calls MUST be wrapped in `try/except` with UI-friendly fallback states
- `apps/funds/mstarpy_fetch.py` runs mstarpy fetches in a subprocess because mstarpy uses signal handlers unsafe for Django request threads

---

## 3. Data Sources & Provider Priority

| Source | Primary Use | Notes |
|---|---|---|
| **AMFI** (`amfiindia.com/spages/NAVAll.txt`) | Search index, latest NAVs | Cached 6h in-process |
| **mfapi.in** | Historical NAV per scheme | Primary NAV source |
| **captnemo** (`mf.captnemo.in`) | Metadata (expense ratio, AUM, manager, inception) | Try exact ISIN first, sibling plan as fallback |
| **mstarpy** (Morningstar) | Holdings, sector/asset allocation | Run via subprocess |
| **NSE India API** | Live and historical benchmark indices | Session warmup required (2 GETs) |
| **yfinance / yahooquery** | Benchmark fallback, BSE Indices | Rate-limited; handles BSE benchmarks (e.g. BSE-500.BO) and global indices |

---

## 4. Django App Structure

```
apps/
├── core/           ← BaseModel (UUID PK, created_at, updated_at), shared utilities
├── funds/          ← Scheme, NAVHistory, SchemeMeta; runtime snapshot; peer matching; PDF report
├── analytics/      ← Analytics engine (engine.py) — pure math, zero views
├── benchmarks/     ← BenchmarkIndex, BenchmarkNAV, management commands, live market API
├── holdings/       ← Holding model (fund's underlying stocks/bonds by month)
├── calculators/    ← Stateless calculator views (SIP, SWP, XIRR, Tax, Goal)
├── recommendations/← Risk questionnaire + fund recommendation engine
└── portfolio/      ← Portfolio upload, analysis dashboard, overlap, benchmark, backtester
    └── services/
        ├── analytics.py    ← XIRR, benchmark simulation, portfolio journey
        ├── backtester_v2.py← Full composable simulation engine (~2,700 lines)
        └── forecasting.py  ← Monte Carlo, ARIMA, ML forecasting
```

---

## 5. Feature Deep-Dive

### A. Analytics Engine (`apps/analytics/engine.py`)
Pure pandas/numpy — no Django ORM in hot loops. Key computations:
- **Trailing CAGR:** `((end/start)^(1/years)) - 1` for 1M, 3M, 6M, 1Y, 3Y, 5Y, MAX
- **Rolling Returns:** Pandas `rolling().apply()` over 1Y, 3Y, 5Y windows with win rates
- **Volatility:** `pct_change().std() * sqrt(252)` (annualised from daily returns)
- **Sharpe:** `(CAGR - RF_RATE) / volatility`; `RF_ANNUAL_RATE` is configurable via `.env`
- **Beta/Alpha:** `scipy.stats.linregress(fund_returns, benchmark_returns)`
- **Max Drawdown:** `nav / nav.cummax() - 1` minimum

### A2. Peer Matching (`apps/funds/peers.py`)
The peer comparison tab uses a scored India-focused matcher rather than a simple category or keyword fallback.
- Hard filters: same plan, same Direct/Regular flag, active schemes only, different fund house, and different AMFI code
- Fingerprints detect active equity/debt/hybrid, index funds, ETFs, FoFs, commodity funds, ELSS, sectors/themes, index groups, and FoF asset/geography
- Ranking is score-first, then AUM, then scheme name; AUM never overrides relevance
- The API returns `match_score`, `match_reason`, and `match_group` for debug visibility
- Full notes and edge cases live in `docs/PEER_MATCHING.md`

### B. Portfolio Analyzer (`apps/portfolio/`)
1. **Parsing** (`parsers.py`): Reads Excel/CSV using Pandas with heuristic column detection
2. **Fuzzy Matching**: Uses `rapidfuzz.WRatio` with a 75-point score cutoff to link CAS fund names to `Scheme` records
3. **XIRR** (`services/analytics.py`): `scipy.optimize.newton` on NPV equation; falls back to `None` on convergence failure
4. **Portfolio Journey**: Weekly-frequency NAV reconstruction with `bisect` binary search for O(log n) NAV lookups per date
5. **Benchmark Simulation**: Replays same cash flows into a blended index benchmark

### C. Backtester V2 (`apps/portfolio/services/backtester_v2.py`)
The most complex service (~2,700 lines). Key design decisions:
- **Dataclasses for I/O**: `RuleV2`, `RebalanceRule`, `PortfolioPlan` for input; `SimulationResult` for output
- **NAV data fetched once** at the start of simulation, then accessed via in-memory `pandas.Series` with date indexing
- **XIRR** uses `scipy.optimize.brentq` for reliability
- **Tax engine**: FIFO lot tracking per asset — realised gains on each redemption split into STCG/LTCG based on holding period; user-supplied rates from the UI settings panel (`tax_equity_stcg`, `tax_equity_ltcg`, `tax_ltcg_exemption`, `tax_debt_rate`)
- **Monte Carlo**: Geometric Brownian Motion on historical daily return distribution; P10/P25/P50/P75/P90 fan
- **Rolling return series**: Pandas `rolling().apply()` per window (3Y/5Y/7Y); returns both values and dates for the trend chart
- **Rebalancing**: Frequency-based (monthly/quarterly/half-yearly/annually) or drift-threshold (absolute or relative) — engine fires a rebalance event when either condition triggers
- AI narrative (`conclusion`) is generated by the `interpret_simulation()` function using rule-based text

### D. Recommendations Engine (`apps/recommendations/engine.py`)
1. User answers a questionnaire → `risk_score` is computed
2. `risk_score` maps to a profile (Conservative/Moderate/Aggressive) and target allocation (equity/debt/gold %)
3. Engine fetches top-ranked direct-growth funds in each required SEBI category from the local DB
4. "Run 5-Year Backtest" button builds a `prefill` URL parameter and navigates to the backtester, which auto-populates and runs the simulation

### E. Forecasting (`apps/portfolio/services/forecasting.py`)
- **Monte Carlo**: Geometric Brownian Motion using Cholesky decomposition of the historical fund covariance matrix. Falls back to independent simulations if Cholesky fails
- **ARIMA**: `statsmodels.tsa.arima.model.ARIMA` with p/d/q configurable; falls back to linear trend projection on failure
- **Machine Learning**: Ridge regression or Random Forest on autoregressive lag features; confidence bands widen proportionally over time

### F. Advanced Fund Screener & Home Dashboard Pipeline (`apps/funds/screener.py`)
Because the analytics engine is heavily computational, screening across thousands of funds requires local caching.
- **`FundScreenerSnapshot` Model**: Denormalized table storing AUM, expense ratios, trailing returns (1Y/3Y/5Y), rolling returns (3Y/5Y), calendar returns (`calendar_returns_json`), volatility, Sharpe, Sortino, Max Drawdown, Alpha, short-term returns (1W/1M/3M/6M), 5Y risk metrics (`volatility_5y_pct`, `sharpe_ratio_5y`, etc.), and quartile/percentile ranks.
- **`FundModelScore` Model**: Stores the 100-point dynamic scoring results per scheme across Performance, Risk, Cost, Composition, Debt Quality, and Manager Quality pillars. 
  - *Note on Scoring:* Currently, the pipeline uses DB-only composition data (Option B) for speed (funds without local holdings are marked UNRATED for composition). In the future, we will transition to full API scoring (Option A) for more comprehensive portfolio analysis.
- **`populate_screener` Command**: An integrated data pipeline that runs sequentially:
  1. Fetches NAV history (`mfapi.in`)
  2. Fetches metadata (`mf.captnemo.in` with sibling plan fallback)
  3. Triggers Analytics Engine for rolling, calendar & risk computations
  4. Generates and saves the final snapshot for the UI.
  5. Computes and saves the `FundModelScore`.
  6. Automatically calls `populate_home_dashboard` at the end (unless `--skip-home-dashboard` is passed).
- **Home Dashboard Pipeline**:
  - **`populate_benchmark_returns`**: Computes trailing, calendar, and rolling returns for 113+ benchmark indices (stored in `BenchmarkReturns`), driving the Home Dashboard's Benchmark Monitor. Includes NSE and major BSE/Global indices.
  - **`populate_home_dashboard`**: Aggregates `FundScreenerSnapshot` data by category to create `CategorySnapshot` records (avg/min/max returns, 3Y/5Y avg risk, score distribution) and computes quartile rankings for all funds within their sub-categories.
- **Dynamic UI**: `FundScreenerView` dynamically populates HTML filter options directly from the `FundScreenerSnapshot` distinct values, allowing new Fund Houses or Benchmarks to seamlessly appear as the database builds. Both `category_detail.html` and `benchmarks.html` ingest `calendar_returns_json` and `rolling_returns_json` to render interactive heatmaps on the frontend.
- **Compare Selected Feature**: The UI includes multi-fund selection (using browser `localStorage`) which automatically enables a direct bridge to the Unified Compare tool.

### G. Learn Resources (`apps/core` + `Resources/`)
The Learn section is intentionally lightweight and file-backed so educational material can be added without building a CMS.
- **Models:** `LearnPDFGuide` and `LearnBlogPost` store admin-manageable metadata for synced resources.
- **Source files:** PDFs live in `Resources/PDF Guides/pdfs/`; PDF metadata lives in `Resources/PDF Guides/guides.json`; blogs live as markdown files in `Resources/Blogs/` with front matter.
- **Sync command:** `python manage.py sync_content` upserts PDF/blog records from those files.
- **Rendering:** `apps/core/content.py` parses front matter, renders trusted local markdown, rewrites local image paths, and safely serves image assets from `Resources`.
- **Fallback:** Learn views fall back to direct file scanning if the local DB is unavailable or content has not been synced yet, keeping the page usable in development.
- **Community:** `/learn/community/` is currently a static/dummy discussion page reserved for a future Disqus or custom posting/reply flow.

---

### H. Fund Overlap Checker (`apps/calculators/views.py` — `calc_overlap_api`)
Stand-alone calculator for comparing stock-level portfolio overlap between exactly two mutual funds.

**API** (`POST /api/calculators/overlap/`):
- Fetches live holdings for each AMFI code via `get_runtime_snapshot`
- Uses `holding_key()` (ISIN-preferring, with normalised name fallback) as the join key
- Returns three lists: `common`, `fund1_exclusive`, `fund2_exclusive`

**Overlap Score — Minimum Weight Method:**
For each stock present in both funds, the overlap contribution = `min(weight_fund1, weight_fund2)`. Summing these gives the true duplicated exposure as a percentage of AUM. This is the industry-standard method and avoids double-counting.

**Exclusive-circle values (Venn Diagram):**
Each circle's displayed percentage is count-based (i.e. `exclusive_count / total_count` for that fund). This correctly represents the proportion of unique stocks in that fund, giving a clearer picture of stock-level differentiation rather than just raw non-overlapping weight.

**Frontend (`templates/calculators/overlap.html`):**
- Venn Diagram: CSS-positioned overlapping circles (blue left, orange right). Values-only in each region; hover tooltip shows holding count + fund name
- Three tabs with short fund names: *Common*, *Only in [Fund A]*, *Only in [Fund B]*
- Weight bars: scaled horizontal bars (blue=Fund1, orange=Fund2) next to each holding's percentage
- Methodology info box: explains both overlap and non-overlap calculations inline, with a worked TCS example

---

```
/                           ← Home (live market strip, fund search)
/funds/search/              ← Global scheme search (autocomplete)
/funds/screener/            ← Advanced data-grid fund screener
/funds/                     ← Browse by category
/funds/<amfi_code>/         ← Main fund analysis page
/funds/<amfi_code>/peers/   ← Scored peer comparison
/calculators/compare/       ← Unified side-by-side fund comparison (Grid layout, Best/Worst quarters overlap, Risk scatter, Sector donuts)
/funds/<amfi_code>/pdf/     ← WeasyPrint PDF export

/research/categories/       ← Category analysis index
/research/categories/<slug>/← Category deep dive
/research/quartiles/        ← Dynamic quartile rankings
/research/amcs/             ← AMC Analysis directory & screener
/research/amcs/<slug>/      ← AMC Detail deep dive (8 pillars across 5 tabs)
/research/amcs/compare/     ← Side-by-side AMC comparison (2–4 AMCs, 26 metrics across 7 dimensions)

/calculators/               ← Calculator hub
/calculators/sip/           ← SIP calculator (prospective + historical back-test; multi-fund; fund-name cashflow rows; auto inception-date start alignment)
/calculators/step-sip/      ← Step-Up SIP calculator (same as SIP with annual % step-up)
/calculators/lumpsum/       ← Lumpsum calculator (historical NAV back-test)
/calculators/swp/           ← SWP (Systematic Withdrawal Plan) calculator
/calculators/xirr/          ← XIRR calculator (manual cashflow entry)
/calculators/goal/          ← Goal Planner (inflation-adjusted, SIP + lumpsum alternatives)
/calculators/rolling/       ← Multi-fund Rolling Return Calculator (compare up to 5 funds, custom benchmark override, color-coded chart with deduped benchmarks, volatility stats + distribution table)
/calculators/net-worth/     ← Comprehensive Net Worth Calculator (assets/liabilities breakdown, plotly donut chart, solvency ratio with color bar)
/calculators/stp/           ← STP Calculator (Generic and Historical NAV modes with source/target XIRR computations)
/calculators/overlap/       ← Fund Overlap Checker (Venn diagram, tabbed holdings, weight bars; Minimum Weight Method)
/calculators/compare/       ← Fund Comparison Calculator (up to 5 funds; Overview/Returns/Risk/Portfolio tabs; Best badges with correct higher/lower logic per metric)
/calculators/tax/           ← Tax Calculator FY 2025-26 (5 tabs: Portfolio Tax, Tax Loss Harvesting, SIP FIFO, Compare & Plan, ITR Guide; 12 fund types; loss set-off engine; STCL/LTCL carry-forward; smart alerts)

/recommendations/           ← Risk profiling questionnaire
/recommendations/results/   ← Fund recommendation results

/learn/resources/           ← Learn Resources page for PDF guides and markdown blogs
/learn/resources/blog/<slug>/ ← Rendered markdown blog detail page
/learn/community/           ← Placeholder community discussion page

/user/dashboard/            ← Centralized User Dashboard (My Account hub)

/portfolio/                 ← Portfolio list
/portfolio/upload/          ← CAS file upload
/portfolio/manual/          ← Manual entry form
/portfolio/<pk>/            ← Portfolio analysis dashboard (tabs: Overview, Analytics, Rebalancing, Overlap Matrix, Benchmark Analysis)
/portfolio/<pk>/overlap/    ← Fund overlap matrix (standalone page; also serves JSON via Accept: application/json)
/portfolio/<pk>/benchmark/  ← Blended benchmark comparison (standalone page; also serves JSON via Accept: application/json)
/portfolio/<pk>/forecast/api/ ← Forecasting API

/portfolio/backtester/      ← Backtester Hub landing page (Build vs Saved Strategies)
/portfolio/backtester/build/ ← Strategy builder + results UI
/portfolio/backtester/v2/run/ ← Backtester simulation API (POST)
/portfolio/backtester/fund-search/ ← Fund/index search for backtester
/portfolio/strategies/      ← Saved strategies list (search + multi-select compare)
/portfolio/strategies/compare/ ← Side-by-side strategy comparison (?ids=1,2,3)
/portfolio/strategies/api/  ← Strategy list API (GET)
/portfolio/strategies/api/<id>/ ← Strategy detail API (GET/PUT/DELETE)
```

---

## 7. Key Conventions

### Tooltip System (`static/js/main.js`)
- Info buttons use class `info-btn` with `data-t-*` attributes
- `data-t-title`: Tooltip heading
- `data-t-what`: What this metric is
- `data-t-interp`: How to interpret it
- `data-t-formula`: The formula (optional)
- `data-t-range`: What values are considered good/bad (optional)
- `initInfoTooltips(container)` must be called after dynamic JS renders new content

### Logging
- Logger name: `mfanalysis` for app code, `adapters.*` for adapter code
- All adapters use structured `logger.debug/warning/error` messages
- Log format: `[timestamp] LEVEL name: message`

### Error Handling Pattern
```python
try:
    result = some_api_call()
except Exception as e:
    logger.warning(f"API call failed: {e}")
    result = None  # or sensible default
```
Never let external API failures propagate to the user with a 500 error.

### Settings Architecture
- `config/settings/base.py`: All shared settings (apps, middleware, logging, django-q2)
- `config/settings/dev.py`: `DATABASES = SQLite`, `DEBUG = True`
- `config/settings/prod.py`: `DATABASE_URL`, security headers, `STATIC_ROOT`
- `RF_ANNUAL_RATE` is configurable via `.env` (default 6.5%)

---

## 8. Current Status

All five planned phases are substantially implemented, plus several enhancements added in v2.2:
- ✅ Phase 1: Data foundation (scheme master, NAV history, benchmark ingestion with 113 indices)
- ✅ Phase 2: Fund detail page with full analytics (including 5Y risk metrics and category averages)
- ✅ Phase 3: Discovery (browse by category, fund search) + **Advanced Fund Screener** + **Unified Compare Tool**
- ✅ Phase 4: Portfolio analysis (XIRR, benchmark, overlap, blended benchmark, risk metrics) — **now with inline Overlap Matrix and Benchmark Analysis tabs in the dashboard**
- ✅ Phase 5: Backtesting + Recommendations (questionnaire, backtester, strategy hub, save/compare strategies)
- ✅ Phase 6: Strategy management (save, load, compare; Backtester Hub; Strategy Compare page)

**Next steps:**
- Open-source release preparation
- Docker containerization
- PostgreSQL production validation
- Unit test coverage expansion
- Custom weighted benchmark inside backtester (separate from portfolio dashboard benchmark)

**Recently completed:**
- ✅ **AMC Analysis Suite** (`/research/amcs/`): Comprehensive research hub for Indian Asset Management Companies built on a live-query architecture. Features an AMC Directory & Screener with multi-select floating compare bar, an 8-pillar AMC Detail page (`/research/amcs/<slug>/`) with 5 tabs (All Funds with 4 sub-tabs, Portfolio Intelligence with high-conviction holdings & sector exposure, Philosophy, Fund Managers, Categories), and a 26-metric side-by-side AMC Comparison page (`/research/amcs/compare/`) with winner badges (★ Best), sector allocation charts, and stock conviction overlap.
- ✅ **User Dashboard & Admin Panel**: Added `/user/dashboard/` to serve as a centralized hub for logged-in users to manage their portfolios, strategies, risk profiles, and watchlists. Integrated with customizable homepage metrics.
- ✅ **Advanced Tax Calculator** (FY 2025-26): 5-tab design covering Portfolio Tax, Tax Loss Harvesting (3 sub-tabs), SIP FIFO, Compare & Plan, and ITR Guide. Supports 12 fund types with correct STCG/LTCG rates, loss set-off priority, ₹1.25L equity LTCG exemption, carry-forward STCL/LTCL, and smart tax-saving alerts.
- ✅ **Fund Comparison Calculator** (`/calculators/compare/`): Side-by-side comparison of up to 5 funds across Overview, Returns, Risk, and Portfolio tabs. Best badge logic audited and corrected — now correctly applies "lower is better" for expense ratio, volatility, beta, drawdown, turnover, and top-10 concentration.
- ✅ **Calculator Suite Audit (July 2025)**: All 12 calculators audited end-to-end for input logic, calculation accuracy, and output presentation. One bug fixed: Tax Calculator Year-End Planner savings was always showing ₹0 (now calculates correctly). All calculation formulas verified.
- ✅ Calculator UX polish: SIP/Step-Up SIP/Lumpsum/Backtester start dates now auto-align to the **earliest inception date** across all selected funds (minimum of all fund inception dates)
- ✅ Cashflow tables in SIP and Step-Up SIP use **fund names** instead of generic "Fund 1", "Fund 2" labels
- ✅ ⓘ Info button tooltips added to all financial calculators + guide sections at the end of each calculator tab
- ✅ Blog management system: blog content backed by markdown files in `Resources/Blogs/`; blog taxation article added

**Recently validated:** Peer comparison now uses scored fingerprint-based matching for Indian mutual funds. Run the regression suite with:
```powershell
$env:DEBUG='True'; python manage.py test apps.funds apps.analytics
```

---

## 9. AI Assistant Guidelines

If you are an AI assistant inheriting this project:

1. **Never bulk-ingest all 14,000 funds.** Use `get_runtime_snapshot(scheme)` for fund detail data.
2. **Pandas over ORM in hot loops.** If editing analytics, use vectorized operations.
3. **All HTTP calls need try/except.** External APIs fail silently; handle gracefully.
4. **Info-btn tooltips for new metrics.** Any new metric shown to users needs a `data-t-*` tooltip.
5. **`initInfoTooltips(container)`** must be called after any JS re-render of result areas.
6. **`_parse_date` helpers should NOT be defined inside loops.** Define them once.
7. **`calendar` and `datetime` are imported at the top of `views.py`.** Do not re-import mid-file.
8. **Backtester API expects a specific JSON schema.** See `documentation/backtester_analysis.md` for the full reference. The API endpoint is `/portfolio/backtester/v2/run/` (POST). The hub landing page is `/portfolio/backtester/`; the builder is `/portfolio/backtester/build/`.
9. **`SavedStrategy` model** has two JSON columns: `plan_json` (the buildPlan() output) and `last_result_json` (the simulation result from the API). Never rename these without a migration.
10. **Data Pipelines:** Refer to `documentation/DATA_PIPELINE_AND_COMMANDS.md` for exact pipeline logic.
11. **Calculators:** All 12 calculators are documented in `documentation/CALCULATORS.md` including inputs, logic, output format, and audit notes. The tax calculator engine (`tax.html`) is fully client-side; never add server-side tax computation without considering data privacy.

---

## 10. Future Integrations & Enhancements

### Future AI Integration
**Robust Execution & Edge-Case Handling**
- **Structured Outputs:** Utilizing strict JSON schemas (via Pydantic and function calling) to ensure LLMs output deterministic financial summaries that don't break the PDF generation pipeline.
- **Semantic Caching:** Implementing caching for AI queries to reduce API costs and latency for frequently searched tickers.
- **Hallucination Prevention:** Enforcing strict grounding rules where the AI is only allowed to comment on the quantitative data provided by the analytics engine, preventing it from inventing financial figures.

**🔐 API Rate Limiting & Authentication**
- **User Login & API Keys:** Introduce a system where users authenticate with their credentials and submit their own API keys (e.g., OpenAI/Anthropic). This enables personalized rate limits and reduces the chance of hitting shared API quotas.
- **Selective AI Invocation:** In the Django UI, provide dedicated buttons for each AI-powered task (e.g., risk analysis, portfolio analysis, investor recommendation, etc.) across tabs and important metrics. Users can choose to run AI only on specific components using their own API key, while the platform still produces an overall base summary without AI when desired.
- **Caching & Rate-limit Guardrails:** Implement semantic caching of AI responses and a request-throttling layer that monitors usage per user API key, automatically backing off or queueing requests when limits are approached.
