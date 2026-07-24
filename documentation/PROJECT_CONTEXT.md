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
- **PDF Generation:** WeasyPrint (active in `apps/funds/report.py`)
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
   - **Analytics:** Computes all metrics in memory — trailing returns, rolling returns, risk metrics, drawdown, quarterly top/worst performance, **Macro Stress Testing (Crisis Period Behaviour across 6 crash events)**, and **Market-Regime Analysis (across 5 economic cycles with per-window breakdowns)**.
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
├── analytics/      ← Analytics engine (engine.py) — pure math, zero views
├── benchmarks/     ← BenchmarkIndex, BenchmarkNAV, UserMarketStripProfile, UserApiKey, metric_providers.py
│   ├── metric_providers.py ← Core market metrics, FRED API integration, fund/benchmark custom monitor logic
│   ├── api_views.py        ← HTMX strip partial, manage modal endpoints, FRED key validation
│   └── models.py           ← BenchmarkIndex, BenchmarkNAV, UserMarketStripProfile, UserApiKey
├── calculators/    ← Stateless calculator views (SIP, SWP, XIRR, Tax, Goal, Overlap)
├── recommendations/← Risk questionnaire + fund recommendation engine
└── portfolio/      ← Portfolio upload, analysis dashboard, overlap, benchmark, backtester V2
```

---

## 5. Market Strip & Intelligence Architecture

1. **Profile Persistence (`UserMarketStripProfile`)**:
   - `metrics` (JSON field): Stores an array of selected metric keys (strings like `"nifty50"`, `"india_vix"`, `"nifty_rsi"`) and custom dictionary items (`{"type": "fund", "scheme_code": "119598", "metric": "sharpe_3y"}` or `{"type": "benchmark", "index_name": "NIFTY 50", "metric": "rolling_3y"}`).
2. **API Keys Engine (`UserApiKey`)**:
   - Stores encrypted API keys (e.g. `fred` provider key).
   - Validates live via `validate_fred_key()`.
3. **Metric Calculations (`metric_providers.py`)**:
   - `_fetch_price_metrics()`: Downloads 14 price metrics from `yfinance` in parallel.
   - `_fetch_technical_metrics()`: Downloads Nifty 50 & Midcap 150 daily data to compute RSI(14), MACD(12,26,9), Bollinger Bands %B, 50/200 DMA gap %, Dist from 52W High, Dist from ATH, and MidCap/LargeCap Relative Strength.
   - `_fetch_fred_metrics()`: Queries FRED API for CPI India, RBI Repo Rate, and Fed Funds Rate using user's key or environment key.
   - `get_fund_metric()` & `get_benchmark_metric()`: Computes fund/benchmark metrics on the fly and attaches direction (`"up"`, `"down"`, `"neutral"`) and signal badges (`"BULLISH"`, `"BEARISH"`, `"EXCELLENT"`, `"DEFENSIVE"`, `"LOW COST"`, `"CAUTION"`).
4. **Modal & Tooltips (`static/js/main.js`)**:
   - Single-source tooltip engine in `static/js/main.js` (`initInfoTooltips()`).
   - Attached to `<button class="info-btn">` elements reading `data-t-*` attributes.
   - Tooltip popup is a fixed, viewport-aware card that activates on `mouseenter` / `click` with DOM auto-purge on hide to prevent duplicate/stacked popovers.

---

## 6. Category Analysis & Comparison Suite

1. **Directory (`/research/categories/`)**:
   - Group tabs: Equity, Debt, Hybrid, Other.
   - Card grid with total AUM, 1Y/3Y/5Y CAGR averages, average Sharpe, TER, % positive 3Y rolling windows, SEBI 2017 mandate descriptions, fund quality score distribution bar, search, and float bar for 2–4 category comparison.
2. **Detail Page (`/research/categories/<slug>/`)**:
   - Official SEBI mandate badge, 21-KPI snapshot strip, 6 interactive tabs (Snapshot, Returns, Risk, Portfolio Analysis, Fees & Details, 🔍 Intelligence).
   - Cleanly excludes schemes with < 1 year of NAV history from aggregate category stats to prevent skewing averages.
3. **Comparison (`/research/categories/compare/`)**:
   - 6-dimension evaluation matrix comparing 2–4 categories side-by-side on 35+ metrics with direction-calibrated winner badges (★ Best), progress bars, and URL state persistence.

---

## 7. Developer Guidelines

- **Never mutate private third-party DOM properties**.
- **Always use explicit UTF-8 encoding** when updating template files containing emojis.
- **Inspect `python manage.py check`** after any template or view changes.
