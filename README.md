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
- **Holdings, sector allocation, and asset allocation** from Morningstar/captnemo
- **Fund manager details** and benchmark comparison
- **PDF fund report** export (WeasyPrint)

### 💼 Portfolio Analysis
- Upload CAS (Consolidated Account Statement) Excel/CSV files, or enter transactions **manually**
- **Fuzzy matching** of fund names from CAS to AMFI codes using `rapidfuzz`
- Per-fund and portfolio-level **XIRR** using SciPy root-finding
- **Portfolio value journey** chart (weekly resolution, NAV-adjusted)
- **Sector allocation, asset-class allocation** derived from scheme categories
- **Concentration score** using Herfindahl-Hirschman Index (HHI)
- **Portfolio turnover** analysis (buy activity in last 12 months)
- **Fund overlap matrix** (common stock holdings between all portfolio funds)
- **Blended benchmark comparison** with custom index weights
- Advanced risk metrics: Alpha, Beta, Sharpe, Sortino, Up/Down Capture
- **Monte Carlo simulation**, ARIMA, and ML forecasting for portfolio trajectory

### 📊 Backtester
- Build a custom **investment plan** with per-fund SIP schedules, lumpsum events, and sell rules
- Simulate against **historical NAV data** with full transaction ledger
- Five strategy variants: **Base Plan, Trend Filter, MA Filter, Volatility Control, Composite Signal**
- Tactical overlays redirect equity SIPs to a **debt parking fund** when signals are off
- Per-strategy metrics: CAGR, XIRR, Final Corpus, Max Drawdown, Sharpe, Sortino, Volatility
- **Calendar-year returns**, rolling stats, downside quarters, trailing returns
- **Annual rebalancing** and **drift-threshold rebalancing**
- AI-generated **narrative conclusions** comparing strategy outcomes
- **Prefill from recommendations**: one-click 5-year backtest from the questionnaire output

### 🎯 Recommendations Engine
- Risk-profiling **questionnaire** (experience, horizon, loss tolerance, goals)
- Maps user profile to equity/debt/gold allocation ratio
- Selects top funds in each required SEBI category
- Presents **fund cards** with key metrics and rationale
- Direct link to run a **5-year SIP backtest** of the suggested portfolio

### 🧮 Financial Calculators
- **SIP** and **Step-Up SIP** future value
- **Lumpsum** return calculator
- **SWP** (Systematic Withdrawal Plan) depletion analysis
- **XIRR** from manually entered cash flows
- **Tax calculator** (STCG/LTCG for equity and debt, indexed/non-indexed)
- **Goal planner** — how much SIP needed to reach a target corpus

### 📈 Benchmarks & Live Market Data
- NSE direct API integration for **real-time index values** (139 indices)
- Historical index data stored in DB for benchmark comparison
- Live market ticker strip in the header

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x (Python 3.11+) |
| Analytics | Pandas, NumPy, SciPy, statsmodels, scikit-learn |
| Charts | Plotly (client-side JS, no server rendering) |
| Frontend | Django Templates, vanilla CSS, vanilla JS |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Background tasks | django-q2 (ORM-backed, no Redis needed) |
| PDF export | WeasyPrint |
| Static files | WhiteNoise |
| Deployment | Render.com (see `render.yaml`) |

---

## Data Sources

All sources are free and unauthenticated.

| Source | Use |
|---|---|
| **AMFI** (`amfiindia.com/spages/NAVAll.txt`) | Scheme universe, latest NAVs, search index |
| **mfapi.in** | Full historical NAV series per scheme |
| **captnemo API** | Rich metadata (expense ratio, AUM, fund manager, inception date, SIP dates) |
| **mstarpy / Morningstar** | Holdings, sector allocation, asset allocation |
| **NSE India API** | Live and historical benchmark index data |
| **yfinance / yahooquery** | Fallback for benchmark data and fund ticker resolution |

---

## Project Structure

```
MutualFundAnalysis/
├── manage.py
├── requirements.txt
├── .env.example             ← copy to .env and fill secrets
├── render.yaml              ← Render.com deployment config
├── Procfile                 ← gunicorn entrypoint for Render
│
├── config/                  ← Django project config
│   ├── settings/
│   │   ├── base.py          ← shared settings (all envs)
│   │   ├── dev.py           ← SQLite + debug toolbar
│   │   └── prod.py          ← PostgreSQL + WhiteNoise + security headers
│   └── urls.py              ← root URL routing
│
├── apps/
│   ├── core/                ← BaseModel (UUID pk, timestamps)
│   ├── funds/               ← Scheme master, NAV history, SchemeMeta, runtime snapshot
│   ├── analytics/           ← Analytics engine (engine.py) — zero views, pure math
│   ├── benchmarks/          ← BenchmarkIndex, BenchmarkNAV, live market API
│   ├── holdings/            ← Fund underlying stock/bond holdings
│   ├── calculators/         ← Stateless financial calculator views
│   ├── recommendations/     ← Risk profiling questionnaire + fund recommendation engine
│   └── portfolio/           ← Portfolio upload, analysis, overlap, benchmark, backtester
│       └── services/
│           ├── analytics.py     ← XIRR, benchmark simulation, portfolio journey
│           ├── backtester.py    ← Full investment plan simulation engine
│           └── forecasting.py   ← Monte Carlo, ARIMA, ML forecasting
│
├── adapters/                ← External API adapters (AMFI, benchmark, captnemo, mstarpy)
│
├── templates/               ← Django HTML templates
├── static/
│   ├── css/                 ← Global stylesheets
│   └── js/                  ← main.js (tooltip engine, charts, navigation)
│
├── scripts/                 ← One-off analysis and data scripts
│
└── docs/                    ← Architecture documentation
    ├── roadmap.md           ← Feature backlog and implementation roadmap
    ├── backtester_analysis.md ← Backtester design, math, and API reference
    ├── SCORING_MODEL.md     ← Fund scoring model design
    ├── recommendation_engine.md ← Recommendation engine logic
    ├── UI_TOOLTIPS.md       ← Info-button tooltip system reference
    ├── data-source-exploration.md ← API exploration notes
    └── tejasblog2.md        ← Referenced performance-comparison methodology
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

## Management Commands

| Command | Purpose |
|---|---|
| `build_scheme_master` | Populate Scheme table from AMFI NAVAll.txt |
| `ingest_nav` | Update latest NAVs for all active schemes |
| `ingest_benchmarks` | Fetch/update NSE index history |
| `ingest_metadata` | Enrich schemes with captnemo metadata |
| `ingest_holdings` | Fetch fund holdings from Morningstar |

---

## Deployment (Render.com)

See [`DEPLOYMENT.md`](DEPLOYMENT.md) and [`render.yaml`](render.yaml) for full production deployment instructions.

Key points:
- Set `DJANGO_SETTINGS_MODULE=config.settings.prod` in environment variables
- Set `DATABASE_URL` (Render PostgreSQL auto-provides this)
- Set `SECRET_KEY`, `ALLOWED_HOSTS`, `DEBUG=False`
- `collectstatic` is run automatically via `render.yaml` build command

---

## Architecture: On-Demand Runtime Loading

The core architectural principle is **"load only what you need, when you need it"**.

With 14,000+ schemes, bulk-ingesting all NAV, metadata, and holdings data daily is impractical. Instead:

1. **Search** uses an in-memory AMFI cache (NAVAll.txt, ~300 KB, refreshed every 6 hours)
2. **Fund detail pages** trigger `get_runtime_snapshot(scheme)` which fetches NAV, metadata, and holdings on demand from external APIs
3. **Analytics** are computed in-memory from the fetched data — nothing is written back to the DB
4. **Benchmarks** and **portfolio** data are the only things fully persisted in the DB

This keeps the database small, the codebase simple, and avoids data freshness problems.

---

## Research References

- [AdvisorKhoj](https://www.advisorkhoj.com/), [ValueResearch](https://www.valueresearchonline.com/), [ET Money](https://www.etmoney.com/mutual-funds/), [Morningstar India](https://www.morningstar.in/)
- Tejas Ekawade's Python study: [getting and analyzing mutual funds](https://medium.com/@TejasEkawade/getting-and-analyzing-mutual-funds-in-python-c2d0feb09881) and [benchmarking and comparing funds](https://medium.com/@TejasEkawade/analyzing-mutual-funds-using-python-benchmarking-and-comparing-funds-215350bf58b7)
- Related open source projects: [mftool](https://github.com/NayakwadiS/mftool), [mstarpy](https://github.com/Mael-J/mstarpy), [folioman](https://github.com/codereverser/folioman), [casparser](https://github.com/codereverser/casparser)

---

## License

See [LICENSE](LICENSE) for repository licensing information.
