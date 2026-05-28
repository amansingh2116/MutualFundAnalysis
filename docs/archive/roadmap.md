# Django Implementation Plan — Mutual Fund Analysis Platform

> **Reference documents:** `README.md` · `docs/workflow.md` · `notebooks/01_data_source_exploration.ipynb`  
> **Validated data sources:** Live-tested in notebook; all confirmed outputs used below.  
> **Status:** Phase 0 complete → ready to implement Phase 1.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Django Project Structure](#2-django-project-structure)
3. [Data Source Routing & Fallback Strategy](#3-data-source-routing--fallback-strategy)
4. [Django Apps — Responsibilities](#4-django-apps--responsibilities)
5. [Database Models](#5-database-models)
6. [Adapter Layer — Data Ingestion](#6-adapter-layer--data-ingestion)
7. [Background Jobs (django-q2)](#7-background-jobs)
8. [Analytics Computation Engine](#8-analytics-computation-engine)
9. [URL Structure & Views](#9-url-structure--views)
10. [Templates & Frontend](#10-templates--frontend)
11. [Phase-by-Phase Build Sequence](#11-phase-by-phase-build-sequence)
12. [Settings, Config, and Dev Setup](#12-settings-config-and-dev-setup)

---

## 1. Project Overview

### What We Are Building

A Python-Django web application for Indian mutual fund research, comparison, portfolio analysis, and personalized guidance.

| Layer | Choice | Reason |
|-------|--------|--------|
| Web framework | **Django 5.x** | ORM, admin, auth, forms, routing |
| Frontend | **Django Templates + HTMX** | Server-side HTML; HTMX for dynamic partials |
| Charts | **Plotly** (JSON → Plotly.js) | Interactive charts, no JS build step |
| Database | **SQLite** (dev) → **PostgreSQL** (prod) | Fast local dev; Postgres for production |
| Background tasks | **django-q2** | Daily NAV, nightly analytics |
| Analytics | **pandas + numpy + scipy** | All metric computation server-side |
| Deployment | **Render / Railway** | Django-compatible PaaS |

### Five Core Capabilities (from README)

1. **Fund Research** — Complete fund profile: NAV, returns, risk, holdings, costs, managers
2. **Screening & Comparison** — Filterable fund universe with side-by-side comparison
3. **Calculators** — SIP, XIRR, rolling returns, STP/SWP, goal planner, tax
4. **Portfolio Analysis** — CAS PDF import, XIRR, benchmark simulation, overlap
5. **Recommendations** — Questionnaire → risk profiling → curated portfolio + backtesting

---

## 2. Django Project Structure

```
mfanalysis/                          ← Django project root (manage.py lives here)
│
├── manage.py
├── requirements.txt
├── .env                             ← SECRET_KEY, DB_URL, API keys (never commit)
├── .gitignore
│
├── config/                          ← Django project package
│   ├── __init__.py
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py                   ← SQLite, DEBUG=True
│   │   └── prod.py                  ← PostgreSQL, DEBUG=False
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py                    ← Optional: Celery app init
│
├── apps/
│   ├── funds/                       ← Scheme universe, NAV history, metadata
│   ├── analytics/                   ← All metric computation
│   ├── benchmarks/                  ← Index/benchmark data
│   ├── holdings/                    ← Portfolio holdings, sector allocation
│   ├── portfolio/                   ← User portfolio: transactions, XIRR
│   ├── screener/                    ← Fund discovery, filter, comparison
│   ├── calculators/                 ← SIP, XIRR, STP, SWP, goal, tax
│   ├── recommendations/             ← Questionnaire, risk profiling
│   └── core/                        ← Shared utilities, base models
│
├── adapters/                        ← Data ingestion adapters (not Django apps)
│   ├── base.py
│   ├── amfi_adapter.py
│   ├── captnemo_adapter.py
│   ├── mstarpy_adapter.py
│   ├── benchmark_adapter.py
│   ├── yahooquery_adapter.py
│   └── registry.py                  ← DataSourceRegistry
│
├── tasks/                           ← Background job definitions
│   ├── ingest_nav.py
│   ├── ingest_benchmarks.py
│   ├── ingest_metadata.py
│   ├── ingest_holdings.py
│   └── compute_analytics.py
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
└── templates/
    ├── base.html
    ├── funds/
    ├── screener/
    ├── portfolio/
    ├── calculators/
    └── recommendations/
```

---

## 3. Data Source Routing & Fallback Strategy

> **Critical principle:** The app must keep working even if 2–3 libraries fail simultaneously. Every data need has a primary source, a fallback, and a "compute from stored data" last resort.

### 3.0 Current Runtime Implementation

The current Django implementation follows the routing strategy without bulk
persisting full fund detail datasets. `apps/funds/runtime.py` builds a
request-scoped snapshot for each fund, and chart/API/compare views read from
that snapshot. SQLite is still used for Django state and the lightweight scheme
registry, but NAV histories, enriched metadata, risk/return tables, holdings,
sectors, and asset allocation are fetched or computed on demand.

Current provider order:

- Scheme search and latest NAV: AMFI scheme universe, then mfapi-style fund
  history/metadata responses.
- Historical NAV: mfapi response data, normalized and used directly for charts
  and analytics.
- Metadata and costs: captnemo by exact ISIN first, then same-fund sibling
  growth-plan fallback when exact-plan data is unavailable. Sibling-plan values
  must be labelled as reference data in the UI.
- Holdings, sector allocation, and asset allocation: `mstarpy` first, validated
  through ISIN/fund-family matching where possible. Because `mstarpy` uses
  process signal handling, Django calls it through `apps/funds/mstarpy_fetch.py`
  in a subprocess.
- Yahoo fallback: `yahooquery`/`yfinance` after normalized fund-name queries and
  NAV/date sanity checks find a plausible ticker.
- Analytics: trailing, calendar, rolling, drawdown, SIP, and risk metrics are
  computed from the runtime NAV series with Pandas instead of saved analytics
  rows.

### 3.1 The Fallback Registry Pattern

```python
# adapters/registry.py
class DataSourceRegistry:
    """
    Routes each data request through a prioritised chain of adapters.
    If the primary raises an exception or returns None/empty,
    the next adapter in the chain is tried automatically.
    All failures are logged with source name and exception.
    """
    def fetch(self, data_type: str, **kwargs):
        chain = ROUTING_TABLE[data_type]  # ordered list of adapters
        last_error = None
        for adapter_cls, method, arg_mapper in chain:
            try:
                result = getattr(adapter_cls(), method)(**arg_mapper(kwargs))
                if result is not None and not _is_empty(result):
                    return SourcedResult(data=result, source=adapter_cls.SOURCE_NAME)
            except Exception as e:
                last_error = e
                logger.warning(f"[{adapter_cls.SOURCE_NAME}] failed for {data_type}: {e}")
                continue
        raise DataUnavailableError(f"{data_type} unavailable. Last error: {last_error}")
```

### 3.2 Complete Data Source Routing Table

> Variable names, API endpoints, and field names are **exactly** as confirmed in `01_data_source_exploration.ipynb`.

#### NAV & Scheme Universe

| Data Need | Primary Source | Fallback 1 | Fallback 2 | Key Fields |
|-----------|---------------|-----------|-----------|------------|
| Scheme universe (~14,364) | `AMFIAdapter.fetch_scheme_universe()` → AMFI NAVAll.txt | `mftool.Mftool().get_available_schemes()` | — | `amfi_code`, `isin_growth`, `scheme_name`, `nav`, `date`, `amc` |
| Current NAV | `AMFIAdapter.fetch_scheme_meta(amfi_code)` → mfapi.in | `mftool.Mftool().get_scheme_quote(amfi_code)` | `captnemo[0]['nav']['nav']` | mfapi: `data[0].nav`; mftool: `nav`; captnemo: `nav.nav` |
| Full NAV history | `AMFIAdapter.fetch_nav_history(amfi_code)` → mfapi.in → `response['data']` | `mftool.Mftool().get_scheme_historical_nav(amfi_code)['data']` | — | Both: list of `{'date': 'DD-MM-YYYY', 'nav': '...'}` |
| Scheme metadata | `AMFIAdapter.fetch_scheme_meta()` → `response['meta']` | `mftool.Mftool().get_scheme_details()` | — | `scheme_name`, `fund_house`, `scheme_type`, `scheme_category` |

#### Enrichment Metadata (captnemo.in → primary for all)

| Data Need | Primary: captnemo field | Fallback 1 | Variable Name |
|-----------|------------------------|-----------|--------------|
| Expense ratio | `response[0]['expense_ratio']` (float) | `mstarpy.Funds(term=id).feesExpenses()` | `expense_ratio` |
| Expense ratio date | `response[0]['expense_ratio_date']` (`'YYYY-MM-DD'`) | Snapshot timestamp | `expense_ratio_date` |
| AUM (₹ Cr) | `response[0]['aum']` (int) | `yf.Ticker(tick).info['totalAssets'] / 1e7` | `aum` |
| Fund manager name | `response[0]['fund_manager']` (semicolon-separated) | `mstarpy.Funds(term=id).managementData()` | `fund_manager` |
| Investment objective | `response[0]['investment_objective']` | `mstarpy` objective | `investment_objective` |
| Fund start date | `response[0]['start_date']` (`'YYYY-MM-DD'`) | First NAV date from history | `start_date` |
| CRISIL rating | `response[0]['crisil_rating']` (str) | — | `crisil_rating` |
| Fund rating (Kuvera 1-5) | `response[0]['fund_rating']` (int) | — | `fund_rating` |
| Lock-in (days) | `response[0]['lock_in_period']` (int) | — | `lock_in_period` |
| Min lumpsum | `response[0]['lump_min']` (float) | — | `lump_min` |
| Min SIP | `response[0]['sip_min']` (float) | — | `sip_min` |
| SIP available | `response[0]['sip_available']` (`'Y'`/`'N'`) | — | `sip_available` |
| Direct plan flag | `response[0]['direct']` (`'Y'`/`'N'`) | Parse scheme name | `direct` |
| Plan type | `response[0]['plan']` (`'GROWTH'`/`'IDCW'`) | Parse scheme name | `plan` |
| Pre-calc returns | `response[0]['returns']` → `{week_1, year_1, year_3, year_5, inception}` | Compute from NAV | `returns_*` |
| Peer comparison list | `response[0]['comparison']` (list of dicts) | mstarpy category peers | `comparison_peers` |

> ⚠️ **captnemo.in API quirk — CONFIRMED IN NOTEBOOK:** The API always returns a **list**, never a plain dict.
> ```python
> raw = requests.get(url).json()
> data = raw[0] if isinstance(raw, list) else raw  # ALWAYS DO THIS
> # Then prefer Direct Growth: [p for p in raw if p.get('direct')=='Y' and p.get('plan')=='GROWTH']
> ```

#### Holdings & Portfolio Composition

| Data Need | Primary | Fallback | Key Columns |
|-----------|---------|---------|------------|
| Full equity holdings (all stocks) | `mstarpy.Funds(term=id).holdings()` → DataFrame | AMC PDF parse (monthly) | `securityName`, `weighting`, `marketValue`, `shareChange`, `country`, `ticker`, `totalReturn1Year`, `forwardPERatio`, `sector`, `isin`, `holdingType` |
| Top-10 holdings | `yahooquery.Ticker(tick).fund_top_holdings` | mstarpy top-10 slice | `holdingName`, `symbol`, `holdingPercent` |
| Sector allocation | `mstarpy.Funds(term=id).sectorAllocation()` | `yahooquery.Ticker(tick).fund_sector_weightings` | mstarpy: `sector`, `weight`; yahooquery: per-sector dict |
| Market cap blend | `mstarpy.Funds(term=id).portfolioStatistics()` | `yahooquery.Ticker(tick).fund_holding_info` | yahooquery: `largeCapPercentage`, `midCapPercentage`, `smallCapPercentage` |
| Asset allocation (equity/debt/cash %) | `yahooquery.Ticker(tick).fund_holding_info` | mstarpy portfolioStatistics | `cashPosition`, `stockPosition`, `bondPosition` |
| Per-holding P/E ratio | mstarpy holdings DataFrame `'forwardPERatio'` column | yahooquery per ticker | `forwardPERatio` |

> ⚠️ **mstarpy constructor — CONFIRMED IN NOTEBOOK (v10.0.0):**
> ```python
> # WRONG (breaks on v10+): mstarpy.Funds(term=id, country='IN')
> # RIGHT: use MstarpyAdapter._init_fund() which inspects signature at runtime
> import inspect
> params = list(inspect.signature(mstarpy.Funds.__init__).parameters.keys())
> if 'country' in params:
>     fund = mstarpy.Funds(term=mstar_id, country='IN')
> else:
>     fund = mstarpy.Funds(term=mstar_id)   # v10.0.0 confirmed working
> ```

#### Risk Metrics & Morningstar Ratings

| Data Need | Primary | Fallback | mstarpy dict keys |
|-----------|---------|---------|------------------|
| Morningstar rating (stars 1-5) | `mstarpy.Funds(term=id).trailingReturn()['overallMorningstarRating']` | `yf.Ticker(tick).info.get('morningStarOverallRating')` | `overallMorningstarRating` |
| MS category | `mstarpy.Funds(term=id).trailingReturn()['categoryName']` | `mfapi meta.scheme_category` | `categoryName` |
| Risk metrics 3Y/5Y | `mstarpy.Funds(term=id).riskVolatilityMeasures()` → indexed by `'3Year'`/`'5Year'` | **Compute from stored NAV** (see §8) | `standardDeviation`, `sharpeRatio`, `beta`, `alpha`, `rSquared`, `informationRatio` |
| Max drawdown | `mstarpy.Funds(term=id).maxDrawDown()` | **Compute from stored NAV** | — |
| Category average returns | `mstarpy.Funds(term=id).trailingReturn()['totalReturnCategory']` | Compute mean of all schemes in same SEBI category | — |

#### Benchmark Indices

| Data Need | Primary | Fallback | Field Names |
|-----------|---------|---------|------------|
| 139 NSE indices live | `BenchmarkAdapter` → `GET https://www.nseindia.com/api/allIndices` | — | `data[i]['index']`, `data[i]['last']` |
| NIFTY50 full history | `BenchmarkAdapter` → NSE historical API (chunked by year) | `yfinance.Ticker('^NSEI').history(period='max')['Close']` | NSE: `EOD_TIMESTAMP` (→ `'DD-MMM-YYYY'`), `EOD_CLOSE_INDEX_VAL` |
| International indices | `yfinance.Ticker('^NDX').history(period='max')['Close']` | `yahooquery.Ticker('^NDX').history()['close']` | yfinance: `Close`; yahooquery: `close` |

### 3.3 Benchmark Ticker Mapping Table

```python
# adapters/benchmark_adapter.py
BENCHMARK_TICKERS = {
    # Index Name            Yahoo ticker        field
    'NIFTY 50':          ('^NSEI',          'Close'),
    'NIFTY NEXT 50':     ('^NSMIDCP',       'Close'),
    'NIFTY 100':         ('^CNX100',         'Close'),
    'NIFTY 500':         ('^CRSLDX',         'Close'),
    'NIFTY MIDCAP 50':   ('NIFMID50.NS',     'Close'),
    'NIFTY MIDCAP 100':  ('NIFMIDCAP100.NS', 'Close'),
    'NIFTY MIDCAP 150':  ('NIFMID150.NS',    'Close'),
    'NIFTY SMALLCAP 100':('NIFSMCP100.NS',   'Close'),
    'NIFTY SMALLCAP 250':('NIFSMCP250.NS',   'Close'),
    'NIFTY BANK':        ('^NSEBANK',        'Close'),
    'S&P 500':           ('^GSPC',           'Close'),
    'NASDAQ 100':        ('^NDX',            'Close'),
}

# SEBI category → benchmark (for risk metric computation)
CATEGORY_BENCHMARK_MAP = {
    'Equity Scheme - Large Cap Fund':         'NIFTY 100',
    'Equity Scheme - Mid Cap Fund':           'NIFTY MIDCAP 150',
    'Equity Scheme - Small Cap Fund':         'NIFTY SMALLCAP 250',
    'Equity Scheme - Flexi Cap Fund':         'NIFTY 500',
    'Equity Scheme - Multi Cap Fund':         'NIFTY 500',
    'Equity Scheme - ELSS':                   'NIFTY 500',
    'Equity Scheme - Large & Mid Cap Fund':   'NIFTY 200',
    'Equity Scheme - Value Fund':             'NIFTY 500',
    'Equity Scheme - Focused Fund':           'NIFTY 500',
    'Equity Scheme - Index Funds':            'NIFTY 50',
    'Hybrid Scheme - Aggressive Hybrid Fund': 'NIFTY 500',
    'Hybrid Scheme - Balanced Hybrid Fund':   'NIFTY 500',
    'Debt Scheme - Liquid Fund':              None,
    'Debt Scheme - Short Duration Fund':      None,
    # Expand for all AMFI categories
}
```

### 3.4 AMFI Code → Morningstar ID Mapping

mstarpy requires a Morningstar `SecId` (e.g. `'F00000PDX2'`). This is not in AMFI data. Build via:

```python
# apps/funds/management/commands/build_mstar_mapping.py
# For each scheme: call mstarpy search API, fuzzy-match fund name,
# store if confidence > 0.9. Store as Scheme.morningstar_id (nullable).
# If null → skip mstarpy calls for that fund entirely.
```

### 3.5 AMFI Code → Yahoo Finance Ticker Mapping

Indian MF Yahoo tickers follow `0P000XXXXX.BO` pattern. Discover via:

```python
# yfinance.Search(fund_name).quotes  or
# yahooquery.Ticker.search(fund_name)
# Store as Scheme.yahoo_ticker (nullable)
# If null → skip yahooquery/yfinance fund-specific calls
```

---

## 4. Django Apps — Responsibilities

### `apps/core/`
- `BaseModel`: `created_at`, `updated_at` timestamps on all models
- `DataProvenance`: which source fetched which field and when
- Template context processors: global market indices, last updated date
- Utility functions: `format_inr()`, `format_pct()`, `safe_div()`, `trailing_return()`

### `apps/funds/`
**The central app. All other apps FK to it.**
- `Scheme`, `NAVHistory`, `SchemeMeta` models
- Management commands:
  - `build_scheme_master` — import all 14,364 schemes from AMFI NAVAll.txt
  - `build_mstar_mapping` — search and store Morningstar IDs
  - `build_yahoo_mapping` — search and store Yahoo Finance tickers
  - `ingest_nav` — daily NAV update
  - `ingest_metadata` — weekly captnemo + mstarpy enrichment
- Views: `FundDetailView`, NAV chart JSON API

### `apps/analytics/`
- `TrailingReturn`, `CalendarReturn`, `RollingReturn`, `RiskMetrics`, `SIPResult` models
- `engine.py` — all computation (Sharpe, Beta, XIRR, rolling returns, etc.)
- `compute_all_metrics(scheme_id)` — orchestrates nightly job per scheme
- JSON API views for chart data

### `apps/benchmarks/`
- `BenchmarkIndex`, `BenchmarkNAV`, `BenchmarkMap` models
- `ingest_benchmarks` management command
- NSE Direct API adapter with yfinance fallback

### `apps/holdings/`
- `Holding`, `SectorAllocation`, `MarketCapAllocation` models
- `ingest_holdings` — monthly mstarpy fetch
- Overlap computation utility (shared between funds app and portfolio app)

### `apps/portfolio/`
- `Portfolio`, `Transaction` models (user-owned, always private)
- CAS PDF parsing via `casparser`
- Fuzzy scheme matching via `rapidfuzz`
- Views: upload, dashboard, XIRR, overlap, benchmark simulation, rebalancing

### `apps/screener/`
- `FundFilter` Django form (all filter fields)
- `FundListView` with annotated queryset (no Python sorting — all DB-level)
- `FundCompareView` for up to 4 funds
- HTMX partial: `_results.html`

### `apps/calculators/`
- Stateless views only — no models needed
- POST form → compute in Python → return JSON
- All calculators: SIP, XIRR, STP, SWP, goal, tax, rolling, overlap, PPF-ELSS, step-up SIP

### `apps/recommendations/`
- `RiskProfile`, `PortfolioRecommendation` models
- Questionnaire form → 5 questions → score → Defensive/Moderate/Aggressive
- Backtesting engine (from `workflow.md` §Backtesting): 5 rebalancing strategies

---

## 5. Database Models

### `apps/funds/models.py`

```python
class Scheme(BaseModel):
    amfi_code        = models.CharField(max_length=10, unique=True, db_index=True)
    isin_growth      = models.CharField(max_length=15, null=True, blank=True, db_index=True)
    isin_idcw        = models.CharField(max_length=15, null=True, blank=True)
    scheme_name      = models.CharField(max_length=300)
    fund_house       = models.CharField(max_length=200)
    scheme_type      = models.CharField(max_length=100)           # 'Open Ended' / 'Close Ended'
    scheme_category  = models.CharField(max_length=200, db_index=True)  # Full SEBI category string
    plan             = models.CharField(max_length=10, db_index=True)   # 'GROWTH' / 'IDCW'
    is_direct        = models.BooleanField(default=False, db_index=True)
    is_active        = models.BooleanField(default=True, db_index=True)

    # Cross-source identifiers (populated by mapping commands)
    morningstar_id   = models.CharField(max_length=20, null=True, blank=True)  # e.g. 'F00000PDX2'
    yahoo_ticker     = models.CharField(max_length=30, null=True, blank=True)  # e.g. '0P000PDX2.BO'
    kuvera_code      = models.CharField(max_length=30, null=True, blank=True)  # captnemo 'code' field

    # Denormalized for fast screener queries (updated nightly)
    expense_ratio    = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    aum_cr           = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    nav_latest       = models.DecimalField(max_digits=12, decimal_places=4, null=True)
    nav_date         = models.DateField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=['scheme_category', 'is_direct', 'plan']),
            models.Index(fields=['fund_house', 'is_active']),
        ]


class NAVHistory(BaseModel):
    scheme  = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='nav_history')
    date    = models.DateField(db_index=True)
    nav     = models.DecimalField(max_digits=12, decimal_places=4)
    class Meta:
        unique_together = ('scheme', 'date')
        indexes = [models.Index(fields=['scheme', 'date'])]


class SchemeMeta(BaseModel):
    """Rich metadata from captnemo.in (62 fields confirmed in notebook)."""
    scheme              = models.OneToOneField(Scheme, on_delete=models.CASCADE, related_name='meta')
    # Investment rules
    lump_available      = models.BooleanField(default=True)
    lump_min            = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    lump_min_additional = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    sip_available       = models.BooleanField(default=True)
    sip_min             = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    sip_dates           = models.JSONField(default=list)
    redemption_allowed  = models.BooleanField(default=True)
    lock_in_period      = models.IntegerField(default=0)             # days
    tax_period          = models.IntegerField(default=0)
    # Analytics (snapshotted weekly from captnemo)
    expense_ratio       = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    expense_ratio_date  = models.DateField(null=True)
    aum                 = models.BigIntegerField(null=True)          # in crores
    fund_rating         = models.IntegerField(null=True)             # Kuvera 1-5
    volatility          = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    returns_1w          = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    returns_1y          = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    returns_3y          = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    returns_5y          = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    returns_inception   = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    # Textual info
    fund_manager        = models.TextField(blank=True)               # "Name1; Name2"
    crisil_rating       = models.CharField(max_length=100, blank=True)
    investment_objective= models.TextField(blank=True)
    portfolio_turnover  = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    start_date          = models.DateField(null=True)
    comparison_peers    = models.JSONField(default=list)
    last_fetched        = models.DateTimeField(auto_now=True)
    fetch_source        = models.CharField(max_length=50, default='captnemo')
```

### `apps/analytics/models.py`

```python
class TrailingReturn(BaseModel):
    scheme   = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='trailing_returns')
    period   = models.CharField(max_length=10)   # '1M','3M','6M','1Y','2Y','3Y','5Y','7Y','10Y','SI'
    years    = models.DecimalField(max_digits=5, decimal_places=2)
    cagr_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    bm_cagr  = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    excess   = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    as_of    = models.DateField()
    class Meta:
        unique_together = ('scheme', 'period', 'as_of')

class CalendarReturn(BaseModel):
    scheme       = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='calendar_returns')
    year         = models.IntegerField()
    return_pct   = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    bm_return    = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    outperformed = models.BooleanField(null=True)
    class Meta:
        unique_together = ('scheme', 'year')

class RollingReturn(BaseModel):
    scheme      = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='rolling_returns')
    window      = models.CharField(max_length=5)     # '1Y', '3Y', '5Y'
    window_days = models.IntegerField()               # 252, 756, 1260
    min_pct     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    max_pct     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    mean_pct    = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    std_dev     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    win_rate_0  = models.DecimalField(max_digits=5, decimal_places=2, null=True)  # % periods > 0%
    win_rate_12 = models.DecimalField(max_digits=5, decimal_places=2, null=True)  # % periods > 12%
    as_of       = models.DateField()
    class Meta:
        unique_together = ('scheme', 'window', 'as_of')

class RiskMetrics(BaseModel):
    scheme           = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='risk_metrics')
    period           = models.CharField(max_length=5)   # '3Y', '5Y'
    period_days      = models.IntegerField()
    std_dev_ann      = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    sharpe_ratio     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    sortino_ratio    = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    max_drawdown     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    beta             = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    alpha_ann        = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    r_squared        = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    upside_capture   = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    downside_capture = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    tracking_error   = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    info_ratio       = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    rf_rate_used     = models.DecimalField(max_digits=5, decimal_places=3, default=0.065)
    benchmark        = models.ForeignKey('benchmarks.BenchmarkIndex', on_delete=models.SET_NULL, null=True)
    as_of            = models.DateField()
    # Morningstar supplement (if available, from mstarpy)
    ms_std_dev_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    ms_sharpe_3y     = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    ms_beta_3y       = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    ms_alpha_3y      = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    class Meta:
        unique_together = ('scheme', 'period', 'as_of')

class MorningstarData(BaseModel):
    scheme             = models.OneToOneField(Scheme, on_delete=models.CASCADE, related_name='ms_data')
    ms_rating          = models.IntegerField(null=True)     # 1-5 stars
    ms_category        = models.CharField(max_length=100, blank=True)
    ms_category_rank   = models.IntegerField(null=True)
    category_return_1y = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    category_return_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True)
    last_fetched       = models.DateTimeField(auto_now=True)
```

### `apps/benchmarks/models.py`

```python
class BenchmarkIndex(BaseModel):
    name         = models.CharField(max_length=100, unique=True)  # 'NIFTY 50'
    nse_type_str = models.CharField(max_length=100, blank=True)   # NSE API indexType param
    yahoo_ticker = models.CharField(max_length=20, blank=True)    # '^NSEI'
    description  = models.TextField(blank=True)

class BenchmarkNAV(BaseModel):
    index = models.ForeignKey(BenchmarkIndex, on_delete=models.CASCADE, related_name='nav_history')
    date  = models.DateField(db_index=True)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    class Meta:
        unique_together = ('index', 'date')
```

### `apps/holdings/models.py`

```python
class Holding(BaseModel):
    """Individual security held by a fund (from mstarpy monthly)."""
    scheme        = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE)
    as_of_month   = models.DateField()                          # YYYY-MM-01
    security_name = models.CharField(max_length=300)
    isin          = models.CharField(max_length=15, blank=True)
    ticker        = models.CharField(max_length=20, blank=True)
    weight_pct    = models.DecimalField(max_digits=7, decimal_places=4)
    market_value  = models.DecimalField(max_digits=18, decimal_places=2, null=True)
    sector        = models.CharField(max_length=100, blank=True)
    country       = models.CharField(max_length=50, default='IN')
    forward_pe    = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    holding_type  = models.CharField(max_length=20, default='equity')
    source        = models.CharField(max_length=20, default='mstarpy')
    class Meta:
        unique_together = ('scheme', 'as_of_month', 'security_name')
        indexes = [models.Index(fields=['scheme', 'as_of_month'])]

class SectorAllocation(BaseModel):
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE)
    as_of_month = models.DateField()
    sector      = models.CharField(max_length=100)
    weight_pct  = models.DecimalField(max_digits=7, decimal_places=4)
    source      = models.CharField(max_length=20, default='mstarpy')
    class Meta:
        unique_together = ('scheme', 'as_of_month', 'sector')
```

### `apps/portfolio/models.py`

```python
class Portfolio(BaseModel):
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name        = models.CharField(max_length=100)
    is_private  = models.BooleanField(default=True)  # Always True for CAS data

class Transaction(BaseModel):
    TYPES = [('BUY','Buy'),('SELL','Sell'),('SIP','SIP'),('REDEEM','Redeem'),
             ('SWITCH_IN','Switch In'),('SWITCH_OUT','Switch Out')]
    portfolio   = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='transactions')
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE, null=True)
    scheme_name = models.CharField(max_length=300)    # raw name from CAS before matching
    amfi_code   = models.CharField(max_length=10, blank=True)
    tx_type     = models.CharField(max_length=15, choices=TYPES)
    tx_date     = models.DateField()
    units       = models.DecimalField(max_digits=15, decimal_places=4)
    nav         = models.DecimalField(max_digits=12, decimal_places=4, null=True)
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    folio       = models.CharField(max_length=30, blank=True)
    class Meta:
        indexes = [models.Index(fields=['portfolio', 'tx_date'])]
```

---

## 6. Adapter Layer — Data Ingestion

### 6.1 Base Adapter

```python
# adapters/base.py
class BaseAdapter:
    SOURCE_NAME: str = 'base'
    RATE_LIMIT_DELAY: float = 1.0

    def _get_with_retry(self, url, session=None, max_retries=3, backoff=2, **kwargs):
        """HTTP GET with exponential backoff."""
        import requests, time
        s = session or requests.Session()
        delay = self.RATE_LIMIT_DELAY
        for attempt in range(max_retries):
            try:
                r = s.get(url, timeout=15, **kwargs)
                r.raise_for_status()
                return r
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"[{self.SOURCE_NAME}] Retry {attempt+1}: {e}")
                time.sleep(delay)
                delay *= backoff
```

### 6.2 AMFI / mfapi Adapter

```python
# adapters/amfi_adapter.py
class AMFIAdapter(BaseAdapter):
    SOURCE_NAME = 'amfi_mfapi'
    AMFI_URL    = 'https://www.amfiindia.com/spages/NAVAll.txt'
    MFAPI_BASE  = 'https://api.mfapi.in/mf'

    def fetch_scheme_universe(self) -> list:
        """Parse NAVAll.txt → list of dicts."""
        r = self._get_with_retry(self.AMFI_URL)
        lines = r.text.strip().split('\n')
        schemes, current_amc = [], ''
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith('Open Ended') or line.startswith('Close Ended'):
                current_amc = line.split('(')[0].strip()
                continue
            parts = line.split(';')
            if len(parts) >= 6 and parts[0].isdigit():
                schemes.append({
                    'amfi_code':   parts[0].strip(),
                    'isin_growth': parts[1].strip() or None,
                    'isin_idcw':   parts[2].strip() or None,
                    'scheme_name': parts[3].strip(),
                    'nav':         parts[4].strip(),
                    'date':        parts[5].strip(),
                    'amc':         current_amc,
                })
        return schemes

    def fetch_nav_history(self, amfi_code: str) -> list:
        """Returns list of {'date': 'DD-MM-YYYY', 'nav': '123.456'}."""
        r = self._get_with_retry(f'{self.MFAPI_BASE}/{amfi_code}')
        return r.json().get('data', [])

    def fetch_scheme_meta(self, amfi_code: str) -> dict:
        """Returns {'scheme_name', 'fund_house', 'scheme_type', 'scheme_category'}."""
        r = self._get_with_retry(f'{self.MFAPI_BASE}/{amfi_code}')
        return r.json().get('meta', {})
```

### 6.3 captnemo Adapter

```python
# adapters/captnemo_adapter.py
class CaptnemoAdapter(BaseAdapter):
    SOURCE_NAME = 'captnemo'
    BASE_URL    = 'https://mf.captnemo.in'

    def fetch_fund_info(self, isin: str) -> dict:
        """
        Fetch fund enrichment by ISIN (Growth ISIN preferred).
        ⚠️ CONFIRMED: API returns a LIST — always use [0].
        Prefer Direct Growth plan when multiple plans returned.
        """
        r = self._get_with_retry(f'{self.BASE_URL}/kuvera/{isin}')
        raw = r.json()
        if isinstance(raw, list):
            direct_growth = [p for p in raw
                             if p.get('direct') == 'Y'
                             and str(p.get('plan', '')).upper() == 'GROWTH']
            return direct_growth[0] if direct_growth else raw[0]
        return raw

    def extract_returns(self, fund_info: dict) -> dict:
        returns = fund_info.get('returns', {})
        return {
            'returns_1w':        returns.get('week_1'),
            'returns_1y':        returns.get('year_1'),
            'returns_3y':        returns.get('year_3'),
            'returns_5y':        returns.get('year_5'),
            'returns_inception': returns.get('inception'),
        }
```

### 6.4 mstarpy Adapter

```python
# adapters/mstarpy_adapter.py
import inspect, mstarpy

class MstarpyAdapter(BaseAdapter):
    SOURCE_NAME = 'mstarpy'
    _FUNDS_PARAMS = None

    @classmethod
    def _get_funds_params(cls):
        if cls._FUNDS_PARAMS is None:
            sig = inspect.signature(mstarpy.Funds.__init__)
            cls._FUNDS_PARAMS = list(sig.parameters.keys())
        return cls._FUNDS_PARAMS

    def _init_fund(self, mstar_id: str) -> mstarpy.Funds:
        """Version-agnostic Funds() constructor (v10.0.0 confirmed no country kwarg)."""
        params = self._get_funds_params()
        if 'country' in params:
            return mstarpy.Funds(term=mstar_id, country='IN')
        elif 'region' in params:
            return mstarpy.Funds(term=mstar_id, region='ASIA')
        else:
            return mstarpy.Funds(term=mstar_id)   # v10.0.0

    def fetch_trailing_returns(self, mstar_id: str) -> dict:
        return self._init_fund(mstar_id).trailingReturn()

    def fetch_risk_metrics(self, mstar_id: str) -> dict:
        """Returns dict keyed by '3Year'/'5Year' with
        standardDeviation, sharpeRatio, beta, alpha, rSquared, informationRatio."""
        f = self._init_fund(mstar_id)
        return f.riskVolatilityMeasures()

    def fetch_holdings(self, mstar_id: str):
        """DataFrame: securityName, weighting, marketValue, sector, isin, forwardPERatio, etc."""
        return self._init_fund(mstar_id).holdings()

    def fetch_sector_allocation(self, mstar_id: str):
        return self._init_fund(mstar_id).sectorAllocation()

    def fetch_max_drawdown(self, mstar_id: str) -> dict:
        return self._init_fund(mstar_id).maxDrawDown()
```

### 6.5 Benchmark Adapter

```python
# adapters/benchmark_adapter.py
class BenchmarkAdapter(BaseAdapter):
    SOURCE_NAME = 'nse_direct'
    NSE_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Referer': 'https://www.nseindia.com/',
    }

    def _make_nse_session(self):
        """NSE requires cookie session — CONFIRMED: must warm up with 2 GETs."""
        s = requests.Session()
        try:
            s.get('https://www.nseindia.com/', headers=self.NSE_HEADERS, timeout=10)
            s.get('https://www.nseindia.com/market-data/live-equity-market',
                  headers=self.NSE_HEADERS, timeout=10)
        except Exception:
            pass
        return s

    def fetch_all_indices_live(self) -> list:
        s = self._make_nse_session()
        r = s.get('https://www.nseindia.com/api/allIndices',
                  headers=self.NSE_HEADERS, timeout=15)
        return r.json().get('data', [])   # [{'index': 'NIFTY 50', 'last': 23913.7, ...}]

    def fetch_index_history(self, index_type: str, from_date, to_date) -> list:
        """
        index_type: plain string e.g. 'NIFTY 50' (URL-encoded internally).
        Returns: [{'date': datetime.date, 'close': float}]
        Response date field: EOD_TIMESTAMP → 'DD-MMM-YYYY' e.g. '01-Jan-2024'
        Response close field: EOD_CLOSE_INDEX_VAL
        """
        import urllib.parse, datetime as dt
        s = self._make_nse_session()
        url = (f'https://www.nseindia.com/api/historical/indicesHistory'
               f'?indexType={urllib.parse.quote(index_type)}'
               f'&from={from_date.strftime("%d-%m-%Y")}'
               f'&to={to_date.strftime("%d-%m-%Y")}')
        r = s.get(url, headers=self.NSE_HEADERS, timeout=15)
        rows = r.json().get('data', {}).get('indexCloseOnlineRecords', [])
        results = []
        for row in rows:
            try:
                parsed_date = dt.datetime.strptime(row['EOD_TIMESTAMP'], '%d-%b-%Y').date()
                results.append({'date': parsed_date, 'close': float(row['EOD_CLOSE_INDEX_VAL'])})
            except (ValueError, KeyError):
                continue
        return results

    def fetch_yfinance_fallback(self, yahoo_ticker: str):
        import yfinance as yf, time
        time.sleep(2)
        h = yf.Ticker(yahoo_ticker).history(period='max')
        if h is None or h.empty:
            return None
        h.index = h.index.tz_localize(None)
        return h[['Close']].rename(columns={'Close': 'close'})
```

---

## 7. Background Jobs

Use **django-q2** (no Redis required in dev). Upgrade to Celery + Redis for production scale.

```python
# config/settings/base.py
Q_CLUSTER = {
    'name': 'mfanalysis',
    'workers': 2,
    'timeout': 3600,
    'retry': 7200,
    'orm': 'default',
}
```

| Job | Cron | Description |
|-----|------|-------------|
| `tasks.ingest_nav.run` | `30 19 * * *` | Daily after 7:30PM IST — fetch latest NAV for all Direct Growth schemes |
| `tasks.ingest_benchmarks.run` | `45 19 * * *` | Daily after 7:45PM IST — NSE Direct API + yfinance fallback |
| `tasks.compute_analytics.run` | `0 21 * * *` | Nightly 9PM — trailing/rolling/risk metrics for all schemes |
| `tasks.ingest_metadata.run` | `0 2 * * 0` | Weekly Sunday 2AM — captnemo + mstarpy enrichment |
| `tasks.ingest_holdings.run` | `0 3 * * 0` | Weekly Sunday 3AM — mstarpy holdings + sector alloc |

---

## 8. Analytics Computation Engine

### `apps/analytics/engine.py`

All formulas verified and tested in `notebooks/01_data_source_exploration.ipynb` Section 13.

```python
import pandas as pd, numpy as np
from scipy import stats

RF_ANNUAL    = 0.065   # 6.5% risk-free (Indian T-bill; update quarterly in settings)
RF_DAILY     = RF_ANNUAL / 252
TRADING_DAYS = 252

def compute_all_metrics(scheme):
    nav = _load_nav_series(scheme)
    bm  = _load_benchmark_series(scheme)
    if len(nav) < 252:
        return
    _compute_trailing_returns(scheme, nav, bm)
    _compute_calendar_returns(scheme, nav, bm)
    _compute_rolling_returns(scheme, nav)
    _compute_risk_metrics(scheme, nav, bm)

def _load_nav_series(scheme) -> pd.Series:
    from apps.funds.models import NAVHistory
    qs = NAVHistory.objects.filter(scheme=scheme).values('date', 'nav').order_by('date')
    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    df['nav']  = pd.to_numeric(df['nav'], errors='coerce')
    return df.set_index('date')['nav'].dropna()

def _compute_trailing_returns(scheme, nav, bm):
    from apps.analytics.models import TrailingReturn
    today = nav.index[-1]
    PERIODS = {
        '1M': 30, '3M': 91, '6M': 182,
        '1Y': 365, '2Y': 730, '3Y': 1096,
        '5Y': 1826, '7Y': 2556, '10Y': 3652,
    }
    rows = []
    for label, days in PERIODS.items():
        cutoff = today - pd.Timedelta(days=days)
        sub = nav[nav.index >= cutoff]
        if len(sub) < 5: continue
        years = days / 365.25
        fund_cagr = _cagr(sub.iloc[0], sub.iloc[-1], years)
        bm_cagr = None
        if bm is not None:
            bm_sub = bm[bm.index >= cutoff]
            if len(bm_sub) > 5:
                bm_cagr = _cagr(bm_sub.iloc[0], bm_sub.iloc[-1], years)
        rows.append(TrailingReturn(
            scheme=scheme, period=label, years=years, cagr_pct=fund_cagr,
            bm_cagr=bm_cagr,
            excess=(fund_cagr - bm_cagr) if (fund_cagr and bm_cagr) else None,
            as_of=today.date()
        ))
    # Since inception
    si_yrs = (today - nav.index[0]).days / 365.25
    rows.append(TrailingReturn(scheme=scheme, period='SI', years=si_yrs,
                               cagr_pct=_cagr(nav.iloc[0], nav.iloc[-1], si_yrs),
                               as_of=today.date()))
    TrailingReturn.objects.filter(scheme=scheme, as_of=today.date()).delete()
    TrailingReturn.objects.bulk_create(rows)

def _compute_risk_metrics(scheme, nav, bm):
    """
    Computes: Std Dev, Sharpe, Sortino, Max Drawdown, Beta, Alpha, R², 
              Upside/Downside Capture, Tracking Error, Info Ratio.
    Risk-free rate: RF_ANNUAL = 6.5% (update in settings).
    Beta/Alpha vs category benchmark (from CATEGORY_BENCHMARK_MAP).
    """
    from apps.analytics.models import RiskMetrics
    today = nav.index[-1].date()
    daily_ret = nav.pct_change().dropna()

    for label, days in [('3Y', 756), ('5Y', 1260)]:
        cutoff  = nav.index[-1] - pd.Timedelta(days=days)
        nav_sub = nav[nav.index >= cutoff]
        if len(nav_sub) < 126: continue
        ret_sub = nav_sub.pct_change().dropna()
        excess_ret = ret_sub - RF_DAILY
        std_ann = ret_sub.std() * np.sqrt(TRADING_DAYS) * 100
        sharpe  = (excess_ret.mean() / excess_ret.std()) * np.sqrt(TRADING_DAYS)
        downside = ret_sub[ret_sub < RF_DAILY]
        sortino  = (excess_ret.mean() * TRADING_DAYS / (downside.std() * np.sqrt(TRADING_DAYS))) if len(downside) > 0 else None
        running_max = nav_sub.cummax()
        max_dd = ((nav_sub - running_max) / running_max * 100).min()

        beta = alpha = r_sq = upside_cap = downside_cap = track_err = info_ratio = None
        if bm is not None:
            bm_sub  = bm[bm.index >= cutoff]
            bm_ret  = bm_sub.pct_change().dropna()
            aligned = pd.DataFrame({'fund': ret_sub, 'bm': bm_ret}).dropna()
            if len(aligned) > 20:
                slope, intercept, r, *_ = stats.linregress(aligned['bm'], aligned['fund'])
                beta  = slope
                alpha = intercept * TRADING_DAYS * 100
                r_sq  = r**2 * 100
                up   = aligned[aligned['bm'] > 0]
                down = aligned[aligned['bm'] < 0]
                upside_cap   = (up['fund'].mean() / up['bm'].mean() * 100) if len(up) > 0 else None
                downside_cap = (down['fund'].mean() / down['bm'].mean() * 100) if len(down) > 0 else None
                diff = aligned['fund'] - aligned['bm']
                track_err  = diff.std() * np.sqrt(TRADING_DAYS) * 100
                info_ratio = (diff.mean() * TRADING_DAYS * 100 / track_err) if track_err else None

        RiskMetrics.objects.update_or_create(
            scheme=scheme, period=label, as_of=today,
            defaults=dict(
                period_days=days, std_dev_ann=std_ann, sharpe_ratio=sharpe,
                sortino_ratio=sortino, max_drawdown=max_dd,
                beta=beta, alpha_ann=alpha, r_squared=r_sq,
                upside_capture=upside_cap, downside_capture=downside_cap,
                tracking_error=track_err, info_ratio=info_ratio, rf_rate_used=RF_ANNUAL,
            )
        )

def simulate_sip(nav_series, monthly_amount=10000, start_date=None):
    """SIP simulation with XIRR. Verified in notebook Section 13.6."""
    from scipy.optimize import brentq
    if start_date is None:
        start_date = nav_series.index[0]
    nav_series.index = pd.to_datetime(nav_series.index)
    monthly = nav_series.resample('MS').first().dropna()
    monthly = monthly[monthly.index >= pd.Timestamp(start_date)]
    if len(monthly) == 0:
        return None
    units_held, invested, cashflows, dates = 0, 0, [], []
    for date_, nav_val in monthly.items():
        units_held += monthly_amount / nav_val
        invested   += monthly_amount
        cashflows.append(-monthly_amount)
        dates.append(date_)
    final_value = units_held * nav_series.iloc[-1]
    cashflows.append(final_value)
    dates.append(nav_series.index[-1])
    def xnpv(rate, cfs, ds):
        t0 = ds[0]
        return sum(cf / (1+rate)**((d-t0).days/365) for cf, d in zip(cfs, ds))
    try:
        xirr = brentq(lambda r: xnpv(r, cashflows, dates), -0.5, 100)
    except Exception:
        xirr = float('nan')
    return {
        'total_invested': invested, 'current_value': final_value,
        'absolute_gain': final_value - invested,
        'absolute_return_pct': (final_value / invested - 1) * 100,
        'xirr_pct': xirr * 100, 'units_held': units_held,
        'sip_instalments': len(monthly), 'avg_cost': invested / units_held,
        'current_nav': float(nav_series.iloc[-1]),
    }

def _cagr(start_val, end_val, years):
    if years <= 0 or start_val <= 0:
        return None
    return ((float(end_val) / float(start_val)) ** (1 / years) - 1) * 100
```

---

## 9. URL Structure & Views

### Root URLs (`config/urls.py`)

```python
urlpatterns = [
    path('admin/',         admin.site.urls),
    path('',               include('apps.funds.urls')),
    path('screener/',      include('apps.screener.urls')),
    path('compare/',       include('apps.screener.urls', namespace='compare')),
    path('calculators/',   include('apps.calculators.urls')),
    path('portfolio/',     include('apps.portfolio.urls')),
    path('recommend/',     include('apps.recommendations.urls')),
    path('api/',           include('apps.analytics.api_urls')),
]
```

### Complete URL Map

```
/                                  → Home (market indices, top funds, news)
/funds/                            → SEBI category browser
/funds/<amfi_code>/                → Fund detail (full profile, 6 tabs)
/funds/<amfi_code>/export/         → PDF/Excel fund report export

/api/funds/<amfi_code>/nav/        → NAV chart JSON (Plotly)
/api/funds/<amfi_code>/returns/    → Trailing + rolling returns JSON
/api/funds/<amfi_code>/risk/       → Risk metrics JSON
/api/funds/<amfi_code>/holdings/   → Holdings table JSON
/api/funds/<amfi_code>/sector/     → Sector allocation JSON
/api/funds/<amfi_code>/sip/        → POST: SIP simulation result JSON

/screener/                         → Fund screener (filter form + table)
/screener/results/                 → HTMX partial: filtered results
/compare/                          → Multi-fund comparison (up to 4)
/compare/api/                      → POST amfi_codes → comparison JSON

/calculators/                      → Calculator hub
/calculators/sip/                  → SIP calculator
/calculators/xirr/                 → XIRR calculator
/calculators/stp/                  → STP calculator
/calculators/swp/                  → SWP calculator
/calculators/goal/                 → Goal planner
/calculators/tax/                  → Tax calculator (STCG/LTCG)
/calculators/rolling/              → Rolling return calculator
/calculators/overlap/              → Fund overlap checker
/calculators/ppf-elss/             → PPF vs ELSS comparison
/calculators/step-sip/             → Step-up SIP calculator
/calculators/api/<name>/           → POST → JSON (all calculators)

/portfolio/                        → Portfolio hub (login required)
/portfolio/upload/                 → CAS PDF upload (casparser)
/portfolio/manual/                 → Manual transaction entry form
/portfolio/<id>/                   → Portfolio dashboard
/portfolio/<id>/xirr/              → XIRR breakdown by fund
/portfolio/<id>/overlap/           → Stock-level overlap matrix
/portfolio/<id>/benchmark/         → Benchmark simulation (missed gains)
/portfolio/<id>/rebalance/         → Rebalancing suggestions
/portfolio/<id>/redflags/          → Red flag analysis

/recommend/                        → Risk questionnaire (5 questions)
/recommend/result/                 → Recommended portfolio (POST)
/recommend/backtest/               → Portfolio backtesting tool
/recommend/backtest/results/       → HTMX: backtest results charts
```

### Fund Detail View Structure

```python
# apps/funds/views.py
class FundDetailView(DetailView):
    model            = Scheme
    template_name    = 'funds/detail.html'
    slug_field       = 'amfi_code'
    slug_url_kwarg   = 'amfi_code'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scheme = self.object
        today  = date.today()
        latest_month = date(today.year, today.month, 1)
        ctx.update({
            # Tab 1: Overview
            'meta':             getattr(scheme, 'meta', None),
            'ms_data':          getattr(scheme, 'ms_data', None),
            # Tab 2: Performance
            'trailing_returns': scheme.trailing_returns.filter(as_of=today).order_by('years'),
            'calendar_returns': scheme.calendar_returns.order_by('-year'),
            'rolling_1y':       scheme.rolling_returns.filter(window='1Y').first(),
            'rolling_3y':       scheme.rolling_returns.filter(window='3Y').first(),
            'rolling_5y':       scheme.rolling_returns.filter(window='5Y').first(),
            # Tab 3: Risk
            'risk_3y':          scheme.risk_metrics.filter(period='3Y', as_of=today).first(),
            'risk_5y':          scheme.risk_metrics.filter(period='5Y', as_of=today).first(),
            # Tab 4: Portfolio / Holdings
            'top_holdings':     Holding.objects.filter(scheme=scheme, as_of_month=latest_month).order_by('-weight_pct')[:20],
            'sector_alloc':     SectorAllocation.objects.filter(scheme=scheme, as_of_month=latest_month),
            # Tab 5: Costs & Rules
            'benchmark_name':   CATEGORY_BENCHMARK_MAP.get(scheme.scheme_category),
            # Tab 6: Managers
            'managers':         scheme.meta.fund_manager.split(';') if hasattr(scheme, 'meta') else [],
        })
        return ctx
```

---

## 10. Templates & Frontend

### Template Hierarchy

```
templates/
├── base.html                       ← Global nav, footer, Plotly.js CDN, HTMX CDN
├── home.html
├── funds/
│   ├── detail.html                 ← Full fund profile (Bootstrap tabs)
│   │   Tabs: Overview | Performance | Risk | Portfolio | Costs | Managers
│   ├── category_list.html
│   └── partials/
│       ├── _nav_chart.html         ← Plotly NAV chart partial
│       ├── _trailing_returns.html
│       └── _holdings_table.html
├── screener/
│   ├── index.html
│   └── _results.html              ← HTMX partial (fund rows)
├── compare/
│   └── index.html
├── calculators/
│   ├── hub.html
│   ├── sip.html
│   └── ... (one per calculator)
├── portfolio/
│   ├── dashboard.html
│   ├── upload.html
│   └── transactions.html
└── recommendations/
    ├── questionnaire.html
    └── result.html
```

### Plotly Chart Pattern

```python
# In view or JSON endpoint:
import plotly.graph_objects as go, plotly.utils, json

def nav_chart_api(request, amfi_code):
    navs  = NAVHistory.objects.filter(scheme__amfi_code=amfi_code).values('date','nav').order_by('date')
    dates = [r['date'].isoformat() for r in navs]
    vals  = [float(r['nav']) for r in navs]
    fig = go.Figure(go.Scatter(x=dates, y=vals, mode='lines',
                               line=dict(color='#2563EB', width=2)))
    fig.update_layout(template='plotly_dark', margin=dict(l=0,r=0,t=30,b=0))
    return JsonResponse({'chart': json.loads(plotly.utils.PlotlyJSONEncoder().encode(fig))})
```

```html
<!-- In fund detail template -->
<div id="nav-chart" style="height:400px"></div>
<script>
  fetch('/api/funds/{{ scheme.amfi_code }}/nav/')
    .then(r => r.json())
    .then(d => Plotly.newPlot('nav-chart', d.chart.data, d.chart.layout));
</script>
```

### HTMX Pattern (Screener)

```html
<!-- screener/index.html -->
<form hx-post="/screener/results/" hx-target="#results" hx-trigger="change, input delay:300ms">
  <select name="scheme_category" id="cat-filter">
    {% for cat in categories %}<option>{{ cat }}</option>{% endfor %}
  </select>
  <input id="min-aum"  name="min_aum"  type="number" placeholder="Min AUM (Cr)">
  <input id="min-ret3" name="min_return_3y" type="number" placeholder="Min 3Y return (%)">
  <!-- ... more filters ... -->
</form>
<div id="results">{% include 'screener/_results.html' %}</div>
```

---

## 11. Phase-by-Phase Build Sequence

### Phase 1 — Data Foundation (Weeks 1–6)

**Week 1–2: Project scaffold**
- [ ] `django-admin startproject config .`
- [ ] Create all 8 apps with `manage.py startapp`
- [ ] `settings/base.py`, `dev.py`, `prod.py`
- [ ] `requirements.txt` (see §12)
- [ ] All models + migrations
- [ ] Django admin registration for all models

**Week 2–3: Adapter layer**
- [ ] `AMFIAdapter` with NAVAll.txt parser + mfapi.in client
- [ ] Management command `build_scheme_master` → 14,364 rows in `Scheme` table
- [ ] Management command `ingest_nav` (with progress bar, idempotent)
- [ ] `BenchmarkAdapter` (NSE Direct + yfinance fallback)
- [ ] Management command `ingest_benchmarks`
- [ ] `CaptnemoAdapter` + `ingest_metadata`
- [ ] `MstarpyAdapter` + `ingest_mstarpy`

**Week 3–4: Analytics engine**
- [ ] `engine.py` with all metric functions (formulas from notebook §13)
- [ ] `compute_analytics` management command + django-q2 schedule
- [ ] Verify metrics match notebook outputs for Quant Small Cap (amfi_code: 120828)

**Week 5–6: Basic fund page**
- [ ] `FundDetailView` with Overview tab
- [ ] NAV chart (Plotly JSON endpoint)
- [ ] Trailing returns table
- [ ] Data freshness badges

---

### Phase 2 — Fund Report MVP (Weeks 7–12)

**All 6 tabs on fund detail page:**

| Tab | Key Content | Data Source |
|-----|-------------|-------------|
| Overview | Status badge (On track/Off track), Morningstar stars, key stats grid | mstarpy + captnemo |
| Performance | Trailing returns table + bar chart, Calendar year chart, Rolling return chart, SIP simulator | NAV DB + computed |
| Risk | Risk metrics table (11 metrics), Drawdown chart | NAV DB + computed |
| Portfolio | Holdings table (top 20 + "show all"), Sector donut, Market cap blend, Equity/debt bar | mstarpy + yahooquery |
| Costs & Rules | Expense ratio trend, Exit load schedule, SIP/lumpsum table, Tax treatment | captnemo |
| Managers | Fund manager cards (name + other funds), AMC overview | captnemo + mstarpy |

- [ ] Peer comparison section (5 similar funds, key metrics)
- [ ] Data provenance tooltip on each section
- [ ] PDF report export (via WeasyPrint or ReportLab)

---

### Phase 3 — Screener & Comparison (Weeks 13–16)

- [ ] Screener: filter by category, AUM, expense ratio, 1Y/3Y/5Y returns, Sharpe, Beta, direct/regular, ELSS, min SIP
- [ ] DB-level queryset filtering + annotation (no Python sorting)
- [ ] Paginated, sortable results table (50 rows/page)
- [ ] Column visibility toggle (stored in localStorage)
- [ ] Fund comparison page: up to 4 funds, all metrics side-by-side
- [ ] Category browser with top-5 funds per category

---

### Phase 4 — Portfolio Analysis (Weeks 17–21)

- [ ] CAS PDF upload using `casparser.read_cas_pdf()`
- [ ] Fuzzy scheme matching: `rapidfuzz.fuzz.WRatio(scheme_name, candidate)` > 0.85
- [ ] Transaction storage (in-memory parse → DB, no PDF stored)
- [ ] Portfolio dashboard: cards (current value, XIRR, 1D return, total return, invested)
- [ ] Benchmark simulation: replay transactions in NIFTY50 → missed gains
- [ ] Stock-level overlap matrix (join `Holding` table across portfolio funds)
- [ ] XIRR vs category average per fund (simulate transactions in category benchmark)
- [ ] Rebalancing suggestions: target asset allocation by risk profile vs actual
- [ ] Privacy: all portfolio routes behind `@login_required` + object permission check

---

### Phase 5 — Recommendations & Backtesting (Weeks 22–27)

- [ ] 5-question risk questionnaire → Defensive/Moderate/Aggressive scoring
- [ ] Curated fund lists per risk profile with rationale (data-backed)
- [ ] Backtesting engine: given fund weights + amounts, simulate using stored NAV
- [ ] 5 rebalancing strategies from `workflow.md`:
  1. 12-month momentum signal
  2. 10-month moving average filter
  3. 6-month realized volatility threshold
  4. PE > 90th percentile → pause equity SIP
  5. Combined signal (average of #1 + #2)
- [ ] Backtest output: CAGR, XIRR, rolling returns, drawdown, SIP analysis
- [ ] Optional AI summary layer: Gemini/OpenAI API to summarize computed metrics
  - **Only enabled after deterministic metrics are validated**
  - All AI output labeled as AI-generated with underlying data shown

---

## 12. Settings, Config, and Dev Setup

### `requirements.txt`

```
# Core
django>=5.0
python-decouple>=3.8

# Data adapters
mftool>=2.0
mstarpy>=10.0.0
yfinance>=0.2.55
yahooquery>=2.3.0
requests>=2.31

# Analytics
pandas>=2.2
numpy>=1.26
scipy>=1.12
rapidfuzz>=3.6

# Charts
plotly>=5.20

# Background tasks
django-q2>=1.7

# Portfolio
casparser>=1.6

# Utils
tabulate>=0.9
python-dateutil>=2.8

# Dev
jupyter
ipykernel

# Prod
gunicorn
psycopg2-binary
whitenoise
weasyprint              # PDF report export
```

### `.env` Template

```ini
SECRET_KEY=your-long-random-secret-key-here
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1

# Risk-free rate (update quarterly)
RF_ANNUAL_RATE=0.065

# Optional integrations
OPENAI_API_KEY=        # Phase 5 AI summary
GEMINI_API_KEY=        # Alternative AI

# Production
# DATABASE_URL=postgres://user:pass@host:5432/mfanalysis
# REDIS_URL=redis://localhost:6379/0
```

### Dev Setup Commands (in order)

```bash
# 1. Virtual environment
python -m venv venv
venv\Scripts\activate          # Windows

# 2. Install
pip install -r requirements.txt

# 3. Migrations
python manage.py migrate

# 4. Build scheme master (~2 min, one-time)
python manage.py build_scheme_master

# 5. Ingest NAV — test with 100 schemes first
python manage.py ingest_nav --limit=100

# 6. Ingest benchmarks
python manage.py ingest_benchmarks

# 7. Ingest metadata (captnemo + mstarpy)
python manage.py ingest_metadata --limit=50

# 8. Run analytics
python manage.py compute_analytics --limit=50

# 9. Create superuser for admin
python manage.py createsuperuser

# 10. Start worker (separate terminal)
python manage.py qcluster

# 11. Start dev server
python manage.py runserver
```

---

## Key Implementation Notes

> These are critical gotchas confirmed from live notebook testing — do not skip.

### 1. captnemo always returns a list
```python
raw = requests.get(f'https://mf.captnemo.in/kuvera/{isin}').json()
data = raw[0] if isinstance(raw, list) else raw   # ALWAYS required
# Then filter for Direct Growth if multiple plans returned
```

### 2. mstarpy constructor changed in v10.0.0
```python
# v10.0.0: country kwarg removed. Check at runtime:
params = list(inspect.signature(mstarpy.Funds.__init__).parameters.keys())
# If 'country' in params: use country='IN'. If not (v10): no country arg.
```

### 3. NSE Direct API needs session warmup
```python
# TWO warm-up GETs required before any NSE API call — confirmed in notebook
session.get('https://www.nseindia.com/')
session.get('https://www.nseindia.com/market-data/live-equity-market')
# Then call: session.get('https://www.nseindia.com/api/historical/indicesHistory?...')
```

### 4. Date format consistency
```python
# AMFI/mfapi NAV dates: 'DD-MM-YYYY' → datetime.strptime(s, '%d-%m-%Y').date()
# NSE historical dates: 'DD-MMM-YYYY' → datetime.strptime(s, '%d-%b-%Y').date()
# captnemo dates: 'YYYY-MM-DD' (ISO) → date.fromisoformat(s)
```

### 5. Risk-free rate is a setting, not a constant
```python
# config/settings/base.py
RF_ANNUAL_RATE = float(env('RF_ANNUAL_RATE', default=0.065))
# In engine.py: from django.conf import settings; RF = settings.RF_ANNUAL_RATE
```

### 6. Portfolio data privacy
```python
# CAS PDF: parse in-memory only — never write to disk or DB
# Transaction data: always private (is_private=True)
# All portfolio views: @login_required + get_object_or_404 with user check
# Never expose portfolio queryset without user filter:
Portfolio.objects.filter(id=pk, user=request.user)  # always include user
```

### 7. Data freshness on every UI section
```python
# Display "Data as of DD-MMM-YYYY (Source: captnemo)" on every data card
# Flag data older than 7 days with a yellow warning badge
# Flag data older than 30 days with a red error badge
```

### 8. TRI vs Price Index limitation
```
All NSE Direct API and yfinance index data is PRICE INDEX, not TRI.
TRI (Total Return Index) includes dividends and is the SEBI-mandated benchmark.
Document this limitation clearly in the UI: "Benchmark shown is price index;
actual TRI returns are slightly higher. Contact NSE/AMFI for TRI data."
```

---

*Last updated: 2026-05-27. This is the definitive implementation reference — update after each phase completion.*
