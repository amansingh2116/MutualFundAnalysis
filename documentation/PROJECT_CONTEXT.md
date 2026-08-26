# Mutual Fund Analysis Platform — Project Context

This document provides a comprehensive technical overview for developers and AI assistants inheriting this project. It covers architecture, implementation decisions, data science logic, and development patterns.

---

## 1. Project Overview & Tech Stack

**Purpose:** A full-featured mutual fund research, portfolio analysis, market intelligence, and backtesting platform built for Indian Mutual Funds. It aims to be a free, locally hostable alternative to platforms like ValueResearch, Morningstar, or AdvisorKhoj.

**Tech Stack:**
- **Backend:** Django 5.x (Python 3.11+)
- **Analytics:** Pandas, NumPy, SciPy, statsmodels, scikit-learn, xgboost
- **Frontend:** Django Templates, Vanilla CSS, Vanilla JS, Plotly.js, HTMX
- **Database:** SQLite (dev) / PostgreSQL (prod via `dj-database-url`)
- **PDF Generation:** Chrome Headless CLI (`apps/funds/report.py` + `templates/funds/report_pdf.html`)
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
   - **Analytics:** Computes all metrics in memory — trailing returns, rolling returns, risk metrics, drawdown, quarterly top/worst performance, **Macro Stress Testing (Crisis Period Behaviour across 6 crash events)**, **Market-Regime Analysis (across 5 economic cycles with per-window breakdowns)**, **Personalized Multi-Factor Scoring (Stability, Consistency, Recency, Cost, Quality)**, **Technical Pattern & Divergence Scanner**, **Parametric vs. Empirical VaR & CVaR Matrix**, **16-Model Statistical & ML/Deep Learning Forecasting Suite**, and **StrategyLab Strategy Backtester Engine**.
3. **Peer Matching:** `apps.funds.peers.get_peer_matches(scheme)` fingerprints scheme names and basic metadata to rank peers even when `scheme_category` is empty.
4. **Market Intelligence & Ticker Strip:** `apps/benchmarks/metric_providers.py` provides 24 core market metrics plus custom fund/benchmark monitor calculations.
5. **Portfolio & Benchmarks** are the only data fully persisted in the database.

---

## 3. Data Sources & Provider Priority

| Source | Primary Use | Notes |
|---|---|---|
| **AMFI** (`amfiindia.com/spages/NAVAll.txt`) | Search index, latest NAVs | Cached 6h in-process |
| **mfapi.in** | Historical NAV per scheme | Primary NAV source |
| **captnemo** (`mf.captnemo.in`) | Metadata (expense ratio, AUM, manager, inception) | Try exact ISIN first, sibling plan as fallback |
| **yfinance / yahooquery** | Live market strip prices, BSE/NSE benchmarks, global indices | Handles `^NSEI`, `^BSESN`, `^INDIAVIX`, `USDINR=X`, `^VIX`, `DX-Y.NYB`, `^TNX`, `BZ=F`, `GC=F`, `^GSPC`, `^IXIC` |
| **FRED API** | Macro economic indicators (India CPI, RBI Repo, US Fed Funds) | Validates user FRED API key, encrypts & caches responses for 6 hours |
| **mstarpy** (Morningstar) | Holdings, sector/asset allocation | Run via subprocess |

---

## 4. Django App Structure & Key Files

```text
apps/
├── core/           ← BaseModel (UUID PK), user dashboard, learn guides/blogs
├── funds/          ← Scheme, NAVHistory, SchemeMeta; runtime snapshot; peer matching; PDF report
├── analytics/      ← Analytics engine, scorer, and forecasting suites:
│   ├── engine.py       ← Pure statistical and returns calculations
│   ├── scorer.py       ← 6-pillar scoring model & personalized ranking breakdown
│   ├── forecasting.py  ← Time series, ML/DL forecasting, VaR/CVaR & StrategyLab backtester
│   └── test_quant.py   ← Automated unit test suite for quant & forecasting engines
├── benchmarks/     ← BenchmarkIndex, BenchmarkNAV, UserMarketStripProfile, UserApiKey, metric_providers.py
│   ├── metric_providers.py ← Core market metrics, FRED API integration, fund/benchmark custom monitor logic
│   ├── api_views.py        ← HTMX strip partial, manage modal endpoints, FRED key validation
│   └── models.py           ← BenchmarkIndex, BenchmarkNAV, UserMarketStripProfile, UserApiKey
├── calculators/    ← Stateless calculator views (SIP, SWP, XIRR, Tax, Goal, Overlap)
├── recommendations/← Risk questionnaire + fund recommendation engine
└── portfolio/      ← Portfolio upload, analysis dashboard, overlap, benchmark, backtester V2, Watchlist & WatchlistItem suite
```

---

## 5. Market Strip & Intelligence Architecture

1. **Profile Persistence (`UserMarketStripProfile`)**:
   - `metrics` (JSON field): Stores an array of selected metric keys (strings like `"nifty50"`, `"india_vix"`, `"nifty_rsi"`) and custom dictionary items (`{"type": "fund", "scheme_code": "119598", "metric": "sharpe_3y"}` or `{"type": "benchmark", "index_name": "NIFTY 50", "metric": "rolling_3y"}`).
2. **API Keys Engine (`UserApiKey`)**:
   - Stores encrypted API keys (e.g. `fred` provider key).
   - Validates live via `validate_fred_key()`.
3. **Metric Calculations (`metric_providers.py`)**:
   - `_fetch_price_metrics()`: Downloads 14 price metrics from `yfinance` in parallel (indices, global benchmarks, USD/INR).
   - `_fetch_technical_metrics()`: Downloads Nifty 50 & Midcap 150 daily data to compute RSI(14), MACD(12,26,9), Bollinger Bands %B, 50/200 DMA gap %, Dist from 52W High, Dist from ATH, and MidCap/LargeCap Relative Strength.
   - `_fetch_fred_metrics()`: Queries FRED API for India CPI, India 10Y G-Sec Yield (INDIRLTLT01STM), and Fed Funds Rate using user's personal FRED API key.
   - `_fetch_valuation_metrics()`: Fetches Nifty 50 PE/PB/Dividend Yield via `nsepython.index_pe_pb_div()`, computes Earnings Yield–Bond Gap, and fetches Buffett Indicator (Market Cap/GDP) via `wbgapi` (World Bank, annual, 1-week cache).
   - `_fetch_nse_sentiment_metrics()`: Fetches PCR (NSE option chain), FII Net Activity (NSE fiidiiTradeReact), Advance/Decline Ratio (NSE allIndicesConsumer), and SIP Inflows (AMFI, monthly, 24h cache). All NSE endpoints use a cookie-authenticated session.
   - `get_fund_metric()` & `get_benchmark_metric()`: Computes fund/benchmark metrics on the fly and attaches direction (`"up"`, `"down"`, `"neutral"`) and signal badges (`"BULLISH"`, `"BEARISH"`, `"EXCELLENT"`, `"DEFENSIVE"`, `"LOW COST"`, `"CAUTION"`).
4. **Modal & Tooltips (`static/js/main.js`)**:
   - Single-source tooltip engine in `static/js/main.js` (`initInfoTooltips()`).
   - Attached to `<button class="info-btn">` elements reading `data-t-*` attributes.
   - Tooltip popup is a fixed, viewport-aware card that activates on `mouseenter` / `click` with DOM auto-purge on hide to prevent duplicate/stacked popovers.

---

## 6. Category & AMC Analysis Suite
 
 1. **Category Analysis & Comparison**:
    - **Directory (`/research/categories/`)**: Group tabs (Equity, Debt, Hybrid, Other), card grid with AUM, CAGR averages, average Sharpe, TER, % positive 3Y rolling windows, SEBI 2017 mandate descriptions, fund quality score distribution bar, search, and float bar for 2–4 category comparison.
    - **Detail Page (`/research/categories/<slug>/`)**: Official SEBI mandate badge, 21-KPI snapshot strip, 6 interactive tabs (Snapshot, Returns with trailing/calendar/rolling subtabs, Risk, Portfolio Analysis with sector breakdown for equity funds and asset allocation/concentration fallback for debt/liquid funds, Fees & Details, and Intelligence).
    - **Comparison (`/research/categories/compare/`)**: 6-dimension evaluation matrix comparing 2–4 categories side-by-side on 35+ metrics with direction-calibrated winner badges (★ Best), progress bars, and URL state persistence.
 2. **AMC Analysis & Comparison**:
    - **Directory (`/research/amcs/`)**: Browse all ~50 fund houses with aggregate AUM, fund count, 3Y returns, expense ratios, quality scores, and multi-select 2–4 AMC comparison.
    - **Detail Page (`/research/amcs/<slug>/`)**:
      - **KPI Overview**: AUM, fund count (active vs ETF), 3Y return, Jensen's Alpha, TER, model score, Sharpe, and unique manager count.
      - **Portfolio Insights Tab**: Historical AMC monthly AUM trend line, AUM-weighted SEBI market-cap blend (Large/Mid/Small), top 20 holdings, sector exposure, and recent full exits.
      - **Intelligence Tab**: Cross-fund high conviction stock holdings (stocks in 3+ schemes), revealed sector tilts, and unique stock universe size.
      - **Philosophy & Categories**: Turnover, active vs passive ratio, category breadth, and manager-to-fund rosters.
    - **Comparison (`/research/amcs/compare/`)**: Side-by-side comparison of 2–4 AMCs across all core metrics.

---

## 7. Financial Calculators & Peer Comparison Engine

1. **Peer Comparison Calculator (`/calculators/peers/`)**:
   - Powered by `get_peer_matches` (`apps/funds/peers.py`) & `peer_comparison_api` (`apps/analytics/api_views.py`).
   - Dynamically selects 5 closest peer funds in the same SEBI category using multi-factor fingerprint matching (category, plan, asset allocation, AUM).
   - Generates side-by-side comparison tables across returns, risk, expense ratio, and model scores with direct 1-click launch into the full Fund Comparison Calculator (`/calculators/compare/`).
2. **Access Control & Navigation Rules**:
   - **Login Required**: AMC Analysis (`/research/amcs/`), Category Analysis (`/research/categories/`), Quartile Rankings (`/research/quartiles/`), PDF Guides (`/learn/resources/guides/`), and Fund Screener (`/funds/screener/`).
   - **Public Access**: Browse Funds (`/funds/`), Category Return Meter (`/research/categories/meter/`), and Benchmark Monitor default views.
   - **Sidebar Navigation**: Active state glowing CSS is dynamically applied across all 17 calculators (including Peer Comparison, AMC Compare, Category Compare, Child Education, and Retirement Planners).

---

## 8. Fund & ETF Multi-Watchlist Suite

1. **Architecture & Persistence (`apps/portfolio/models.py`)**:
   - `Watchlist`: Owned by `User`, supports `is_default` flag for the primary watchlist and custom user-named lists with optional descriptions.
   - `WatchlistItem`: Unique `(watchlist, scheme)` pair storing scheme references, personalized research notes, target entry prices, and timestamps.
2. **REST Endpoints & Hub (`apps/portfolio/views.py`)**:
   - `watchlist_hub_view` (`/portfolio/watchlist/`): Interactive hub with tabbed switching between default and custom watchlists, real-time fund/ETF search and addition via AMFI index, inline editable research notes, CSV export, and 1-click scheme removal.
   - APIs:
     - `POST /portfolio/watchlist/api/toggle/`: 1-click toggle from fund detail pages.
     - `POST /portfolio/watchlist/api/items/add/`: Adds schemes to specific watchlists.
     - `POST /portfolio/watchlist/api/items/<id>/notes/`: Updates inline notes without reloading.
     - `POST /portfolio/watchlist/api/items/<id>/delete/`: Removes scheme from watchlist.
     - `POST /portfolio/watchlist/api/create/`: Creates custom-themed watchlists.
     - `POST /portfolio/watchlist/api/manage/`: Edits and deletes watchlists.

---

## 9. Investor Community & Discussion Feed Architecture

1. **Data Model (`apps/core/models.py`)**:
   - **`CommunityProfile`**: Extends Django's `User` via 1-to-1 relationship. Contains `display_name`, `bio`, `investor_tag` (*SEBI RIA*, *Quant Researcher*, *DIY Investor*, *Portfolio Investor*), `avatar_color`, and `avatar_initials`. Auto-created on user sign-up via signals.
   - **`CommunityPost`**: Stores discussion threads with title, content, `ImageField` (uploaded to `media/community/posts/`), `tags` (comma-separated or JSON list of hashtags), `is_pinned` flag, and denormalized `likes_count` and `replies_count` (`sync_counts()` helper).
   - **`CommunityComment`**: Threaded replies attached to posts with author and timestamps.
   - **`CommunityLike`**: Unique `(post, user)` like mapping.
   - **`CommunityFollow`**: Unique `(follower, following)` relationship graph.
2. **Views & REST APIs (`apps/core/views.py`)**:
   - `learn_community_view`: Login-required interactive feed with automatic initial discussion seeding, dual tabs (`Explore` and `Following`), dynamic trending hashtags ranking, and who-to-follow suggestions.
   - `POST /learn/community/api/posts/`: Multipart upload for publishing posts with images and tags.
   - `POST /learn/community/api/posts/<id>/like/`: Atomic 1-click optimistic like toggle.
   - `POST /learn/community/api/posts/<id>/reply/`: Real-time discussion reply submission.
   - `POST /learn/community/api/users/<id>/follow/`: Follow / unfollow toggle.
   - `GET /learn/community/api/users/<id>/profile/`: Returns JSON investor profile card data and recent posts.
   - `POST /learn/community/api/profile/update/`: Profile customization endpoint.
   - `GET /learn/community/api/users/<id>/network/`: Returns followers / followings list.

---

## 10. Advanced Portfolio Intelligence & Diagnostic Models

1. **Granular Asset Allocation Lookthrough**:
   - Decomposes holdings into Equity (Large/Mid/Small-cap via `CapClassifier`), Debt (Sovereign G-Sec, AAA, AA, A1+ Corporate, Below-Investment Grade, Cash), Hybrid Arbitrage, Gold/Commodities, REITs/InvITs, and International Equities.
2. **Concentration & Overlap Analysis**:
   - Stock-level lookthrough overlap matrix identifying hidden cross-fund duplicate exposures.
   - Sector Herfindahl-Hirschman Index (HHI) measuring portfolio concentration vs. diversified benchmarks.
3. **Debt Portfolio Risk Breakdown**:
   - Weighted Average Maturity (WAM), Modified Duration, Yield to Maturity (YTM), and Credit Rating Breakdown.
4. **Automated CAS Parsing Architecture (Upcoming)**:
   - Pipeline using `casparser` to extract consolidated PDF statements (CAMS / KFintech), decrypt passwords securely in-memory, normalize ISINs and folio numbers, and build transaction ledgers automatically.

---

## 11. AI Integration & Deterministic Financial Guardrails

1. **Deterministic Structured Outputs**:
   - All AI-generated research summaries and diagnostic reports must be parsed through strict Pydantic schemas before rendering in templates or institutional PDF exports.
2. **Grounding & Semantic Caching**:
   - Prompts strictly inject computed mathematical metrics (Alpha, Sharpe, VaR/CVaR, Rolling Returns) as factual context. Hallucination guardrails reject ungrounded assertions.
   - Semantic response caching with 24-hour TTL to minimize API costs.
3. **Bring Your Own Key (BYOK)**:
   - User settings provide encrypted storage for OpenAI, Anthropic, and Gemini API keys to grant users higher rate limits.

---

## 12. Automated Testing Suite & Quality Assurance

1. **Test Coverage Hierarchy**:
   - **Quant & Analytics Engines** (`apps/analytics/test_quant.py`): Verifies statistical accuracy of Sharpe, Sortino, VaR/CVaR, Monte Carlo simulations, and forecasting models.
   - **Portfolio & Calculators** (`apps/portfolio/tests.py`, `apps/calculators/tests.py`): Validates portfolio XIRR, overlap matrices, tax rules (FY 2025-26), and calculator equations.
   - **Community Feed Suite** (`apps/core/tests.py`): Tests post creation, like toggles, reply threads, follow graphs, network APIs, profile customization, and hashtag filtering.
   - **Database & Migration Check**: Every release runs `python manage.py check` and automated test suites against both SQLite and Docker PostgreSQL.
2. **Continuous Integration**:
   - Automated GitHub Actions CI workflow triggers migrations, static file collection, and unit test suites on every pull request and push to `main`.

---

## 13. Developer Guidelines

- **Never mutate private third-party DOM properties**.
- **Always use explicit UTF-8 encoding** when updating template files containing emojis.
- **Inspect `python manage.py check`** and execute `python manage.py test` after any template, view, or model changes.


