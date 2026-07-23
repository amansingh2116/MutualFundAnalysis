# MutualFundAnalysis

> **A full-featured, India-focused mutual fund research, portfolio analysis, market intelligence, and strategy backtesting platform built with Django.**

**Disclaimer:** Mutual fund investments are subject to market risk. This platform is for research and educational purposes only. It is not financial, legal, or tax advice and does not guarantee returns.

---

## Features

### Market Intelligence & Ticker Strip
- **Customizable Top Market Strip** *(login required)*: Real-time scrolling ticker bar displaying broad market indices, sentiment, technicals, macro indicators, global benchmarks, custom fund metrics, and custom index metrics.
- **24 Built-in Market Metrics**:
  - **Indices**: Nifty 50, Sensex, Nifty 200, Nifty Midcap 150, Nifty Smallcap 250
  - **FX & Sentiment**: USD/INR, India VIX
  - **Technicals**: Nifty RSI(14), Nifty MACD, Nifty BB %B, Nifty 50/200 DMA, Nifty Dist 52W High, Nifty Dist from ATH, MidCap/LargeCap Relative Strength
  - **Macro (India & FRED)**: RBI Repo Rate, India CPI (YoY), Fed Funds Rate *(supports personal FRED API key validation & storage)*
  - **Global**: US VIX, DXY, US 10Y Treasury Yield, Brent Crude, Gold, S&P 500, NASDAQ
- **Fund & Benchmark Monitors**: Track any mutual fund or benchmark index live in your top strip on 10 specific metrics (1D Return, Rolling 3Y CAGR, Distance from ATH, Max Drawdown, Sharpe, Sortino, Alpha, Beta, Tracking Error, Expense Ratio).
- **Directional Signals & Color Badges**: All metrics display direction-calibrated colors (Green ▲ for bullish/healthy, Red ▼ for bearish/caution) and contextual signal badges (`BULLISH`, `BEARISH`, `EXCELLENT`, `DEFENSIVE`, `LOW COST`, `CAUTION`, `NEUTRAL`).
- **Hover Tooltips Engine**: Hovering over any ⓘ icon opens a non-intrusive, viewport-aware card explaining what the metric is, how to interpret it, and key decision thresholds.
- **Reference Guide**: See [mf_market_metrics_reference.md](documentation/ideas/mf_market_metrics_reference.md) for the complete mathematical and decision-map reference.

---

### Fund Research & Discovery
- Browse and search across **all Direct Growth mutual funds and all ETFs** (~2,000+ Direct Growth + ~300+ ETFs) with real-time AMFI cache fallback
- Full **fund detail pages** with NAV history, metadata, and analytics
- **Performance**: Calendar-year returns, trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y, Max)
- **Risk Metrics**: Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Quarterly Performance Analysis
- **Rolling return distributions** with win rates, medians, and min/max ranges
- **Composition**: Holdings, sector allocation, and asset allocation from Morningstar
- **Advanced Fund Screener** *(login required)*: Filter, sort, and export across the complete Direct Growth + ETF universe on 30+ metrics — see [SCREENER.md](documentation/SCREENER.md) for a full feature guide
- **Quartile Rankings** *(Research → Quartile Rankings)*: Dynamic on-the-fly peer ranking computed live against the full sub-category cohort on every request
- **AMC Analysis** *(Research → AMC Analysis)*: Comprehensive fund house research suite to evaluate, analyze, and compare Indian Asset Management Companies (`/research/amcs/`, `/research/amcs/<slug>/`, `/research/amcs/compare/`)
- **Category Analysis & Compare Suite** *(Research → Category Analysis)*:
  - **Category Directory & Screener** (`/research/categories/`): Interactive card grid of all SEBI categories with total category AUM, 1Y/3Y/5Y CAGR averages, average Sharpe, TER, % positive 3Y rolling windows, SEBI mandate descriptions, fund quality score distribution, search, and 2–4 category comparison bar.
  - **Category Detail Page** (`/research/categories/<slug>/`): Deep-dive category page featuring official SEBI mandate badges, a 21-KPI snapshot strip, 6 interactive tabs (Snapshot, Returns, Risk, Portfolio Analysis, Fees & Details, 🔍 Intelligence).
  - **Side-by-Side Category Comparison** (`/research/categories/compare/`): 6-dimension evaluation matrix comparing 2–4 categories side-by-side on 35+ metrics with direction-calibrated winner badges (★ Best), progress bars, and URL state persistence.
- **Advanced Quantitative Analysis Suite** *(Fund Detail → Advanced Quant Suite)*: Institutional-grade quantitative research suite with technical oscillators, interactive Plotly charts, measure/draw tools, 1,000-path Monte Carlo simulations, ARIMA/XGBoost/LSTM return forecasting, and GARCH volatility modeling — see [ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md).

---

### Portfolio Analysis
- Upload CAS (Consolidated Account Statement) files or enter transactions manually
- Fuzzy matching of fund names from CAS to AMFI codes
- Per-fund and portfolio-level **XIRR** using SciPy root-finding
- **Blended benchmark comparison** weighted by actual capital allocation
- **Concentration score** (Herfindahl-Hirschman Index) and Portfolio turnover analysis
- **Portfolio Dashboard tabs**: Overview, Analytics & Performance, Rebalancing & Alerts, **Overlap Matrix**, **Benchmark Analysis**

---

### Strategy Backtester V2
- **Backtester Hub** landing page with two entry points: *Build & Test Strategy* and *Saved Strategies*
- Build a custom portfolio with **mutual funds and/or NSE indices**
- Simulate **SIP, Step-Up SIP, Lumpsum, SWP, and Switch** investment strategies
- Attach **conditional triggers** (Drawdown from ATH, 200-day Moving Average, RSI, Relative Valuation, Calendar Date)
- Rebalancing engine, inflation adjustment (World Bank CPI), tax engine (STCG/LTCG FIFO), Monte Carlo projections (200–1000 scenarios)
- Compare up to 4 saved strategies side-by-side — see [backtester_analysis.md](documentation/backtester_analysis.md).

---

### Financial Calculators
- **Calculator Hub** (`/calculators/`) — all 12 calculators accessible from a single dashboard:
  - SIP, Step-Up SIP, Lumpsum, SWP, STP, XIRR, Goal Planner, Net Worth, Rolling Returns, Fund Overlap Checker, Fund Comparison, and FY 2025-26 Tax Calculator — see [CALCULATORS.md](documentation/CALCULATORS.md).

---

### Learn & Community
- **PDF Guides** (`/learn/resources/guides/`) with canvas-based in-app PDF.js viewer, zoom toolbar, security controls, and downloadable toggles.
- **Blogs** (`/learn/resources/blogs/`) with cover hero banners, sticky desktop ToC, mobile ToC drawer, and dynamic scroll highlight.
- **Community Feed** (`/learn/community/`).

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.x (Python 3.11+) |
| Analytics | Pandas, NumPy, SciPy, statsmodels |
| Charts | Plotly.js (client-side) |
| Frontend | Django Templates, Vanilla CSS, Vanilla JS, HTMX |
| Database | SQLite (Dev) / PostgreSQL (Prod) |
| External APIs | yfinance, FRED API, mfapi.in, Morningstar, AMFI |

---

## Technical Documentation & Guides

- [SCREENER.md](documentation/SCREENER.md) — Fund Screener guide & metric catalogue
- [ADVANCED_ANALYSIS.md](documentation/ADVANCED_ANALYSIS.md) — Technical indicators, ML forecasting & risk models
- [CALCULATORS.md](documentation/CALCULATORS.md) — Documentation for all 12 financial calculators
- [backtester_analysis.md](documentation/backtester_analysis.md) — Strategy Backtester V2 user & developer guide
- [mf_market_metrics_reference.md](documentation/ideas/mf_market_metrics_reference.md) — Market Strip metrics & investment decision framework
- [PROJECT_CONTEXT.md](documentation/PROJECT_CONTEXT.md) — Complete repository structure and architecture overview
