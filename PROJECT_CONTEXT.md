# Mutual Fund Analysis Platform - Comprehensive Project Context

This document provides a deep, comprehensive overview of the Mutual Fund Analysis Platform. It is designed to be passed into an LLM or shared with developers to instantly transfer context regarding the architecture, logic, data science implementations, and feature set of the application.

---

## 1. Project Overview & Tech Stack

**Purpose:** A full-featured mutual fund tracking, screening, and analytics platform built for Indian Mutual Funds. It aims to be a free, locally hostable or deployable alternative to commercial platforms like ValueResearch or Morningstar.

**Tech Stack:**
- **Backend:** Django (Python), Pandas, NumPy, SciPy (for financial math).
- **Frontend:** Django Templates, HTMX (for SPA-like dynamic partial updates without React/Vue), Bootstrap 5 (Styling), Plotly (Interactive Charts).
- **Database:** SQLite (local development) / PostgreSQL (production-ready via `dj-database-url`).
- **PDF Generation:** WeasyPrint (HTML to PDF).

---

## 2. Core Architecture: "On-Demand Lazy Loading"

The most crucial architectural decision in this project is the **Lazy-Loading Data Model**.
Indian mutual funds comprise over 14,000 active schemes. Downloading and updating NAVs for all of them daily requires immense compute.
Instead, the platform operates entirely on-demand:

1. **Initial State:** The database starts completely empty.
2. **Search (AMFI Cache):** When a user searches for a fund, the app fetches a lightweight text file (NAVAll.txt, ~300KB) from AMFI, caches it in memory for 6 hours, and uses it to power instant auto-complete suggestions.
3. **Fund Visit (The Orchestrator):** When a user clicks on a fund (e.g., `Parag Parikh Flexi Cap`), the `apps.funds.services.prepare_fund_for_display(amfi_code)` function intercepts the request:
   - **Checks DB:** Does the fund exist? 
   - **Fetches if Missing:** If not, it hits `mfapi.in` for NAV history and `captnemo.in` for rich metadata.
   - **Updates if Stale:** If the NAV is older than 24 hours, it fetches the delta.
   - **Computes:** It triggers the Pandas analytics engine to compute all metrics inline.
   - **Serves:** Renders the page.
4. **Result:** The system only consumes API limits and database storage for funds that users actually care about.

---

## 3. Data Sources

The project relies entirely on free, open APIs with built-in fallbacks.

1. **AMFI (Association of Mutual Funds in India):**
   - **URL:** `https://www.amfiindia.com/spages/NAVAll.txt`
   - **Use:** Used to build the lightweight search index and get the latest NAVs globally.
2. **MFAPI.in:**
   - **URL:** `https://api.mfapi.in/mf/{amfi_code}`
   - **Use:** The primary source of historical NAV data (often spanning 15-20 years for a single fund).
3. **Captnemo API (Mutual Fund API):**
   - **URL:** `https://api.mfapi.in/mf/{amfi_code}` (Note: We use Captnemo's fork/dataset for extended meta).
   - **Use:** Rich metadata (Expense ratio, AUM, Fund Manager, Inception Date). *Quirk handled in code: Captnemo always returns a list, so we index `[0]` and filter for `direct='Y'` and `plan='GROWTH'`.*
4. **Yahoo Finance (`yfinance`) & NSE India:**
   - **Use:** Fetches daily benchmark index data (Nifty 50, Sensex, etc.) for live market strips and alpha/beta regression baselines.

---

## 4. Project Structure (Django Apps)

The repository is modularized into specific business domains inside the `apps/` folder:

*   **`apps/core/`**: Base models (UUIDs, timestamps) and shared utilities (HTTP clients, rate limiters).
*   **`apps/funds/`**: The heart of the app. Contains the `Scheme`, `SchemeMeta`, and `NAVHistory` models. Houses the `services.py` orchestrator and the `report.py` PDF generator.
*   **`apps/benchmarks/`**: Fetches and stores index data (Nifty 50). Provides HTMX API endpoints for the live market ticker strip on the homepage.
*   **`apps/analytics/`**: The Data Science engine. Contains zero views, only mathematical logic (`engine.py`) and models to persist results (CAGR, Risk metrics).
*   **`apps/holdings/`**: Manages the underlying stocks/bonds a mutual fund holds. (Future capability for parsing monthly portfolios).
*   **`apps/calculators/`**: Stateless views for financial calculators (SIP, Step-Up, XIRR, Lumpsum, SWP, Tax).
*   **`apps/screener/`**: Dynamic filtering of funds using Django forms and HTMX partials.
*   **`apps/portfolio/`**: Uploading and parsing user CAS (Consolidated Account Statement) Excel/CSV files.
*   **`apps/recommendations/`**: Risk profiling questionnaire and automated fund suggestions with backtesting.
*   **`apps/tasks/`**: Background Celery/Cron jobs for nightly data refreshes.

---

## 5. Feature Deep-Dive & Implementation Logic

### A. The Analytics Engine (`apps/analytics/engine.py`)
This is the quantitative core of the platform. It strictly uses Pandas/NumPy and avoids Django ORM inside hot loops.

*   **Trailing Returns (CAGR):** Uses standard Compounded Annual Growth Rate formula `((End Value / Start Value) ^ (1 / Years)) - 1`. Calculated for 1M, 3M, 6M, 1Y, 3Y, 5Y, and Since Inception.
*   **Rolling Returns:** Computes 1Y, 3Y, 5Y rolling windows by shifting the Pandas series. Calculates minimum, maximum, average returns, and Win Rates (e.g., % of time returns were > 12%).
*   **Risk Metrics (Modern Portfolio Theory):**
    *   **Standard Deviation:** Annualized volatility `nav.pct_change().std() * sqrt(252)`.
    *   **Sharpe Ratio:** `(Return - RiskFreeRate) / StdDev`. Uses a dynamic Risk-Free Rate (default 6.5%).
    *   **Sortino Ratio:** Similar to Sharpe, but only penalizes downside volatility (returns below risk-free rate).
    *   **Max Drawdown:** Calculates the deepest peak-to-trough drop in NAV history using `nav.cummax()`.
    *   **Alpha & Beta:** Uses `scipy.stats.linregress` to run a linear regression of the Fund's daily returns against the Benchmark's daily returns. Slope = Beta, Intercept = Alpha.

### B. Portfolio Analyzer (`apps/portfolio/`)
Users can upload their CAMS/KFintech CAS (exported as Excel/CSV).
1.  **Parsing:** `apps/portfolio/parsers.py` reads the file using Pandas and standardizes columns via heuristic dictionary mapping (e.g., mapping 'txn date', 'transaction date' to `tx_date`).
2.  **Fuzzy Matching:** Because user CAS files have slightly different fund names than AMFI (e.g., "Parag Parikh Flexi Cap Regular Growth" vs "Parag Parikh Flexi Cap Fund - Direct Plan"), we use the `rapidfuzz` library to fuzzy-match strings and link the transaction to the correct `Scheme` UUID in the DB.
3.  **XIRR Calculation:** Uses SciPy's `brentq` root-finding algorithm to solve the NPV equation to exactly 0, giving the exact annualized Internal Rate of Return across irregular cash flows.

### C. Recommendations & Backtester (`apps/recommendations/`)
1.  **Risk Profiling:** Users answer a questionnaire to determine their profile (Conservative, Moderate, Aggressive) and horizon.
2.  **Asset Allocation Engine:** `apps/recommendations/engine.py` maps the profile to an Equity/Debt/Gold ratio (e.g., Conservative = 30/60/10).
3.  **Fund Selection:** The engine fetches the top-ranked funds in the required SEBI categories (e.g., Flexi Cap for Equity, Liquid for Debt). To bypass the "Lazy Loading" cold start problem, the engine has a hardcoded list of historically strong AMFI codes to pre-fetch on-demand.
4.  **Backtesting:** The app uses historical NAV data to simulate a standard ₹10,000 monthly SIP into the newly recommended portfolio over the last 5 years, plotting the exact historical trajectory.

### D. Screener & HTMX Integration
*   The Screener (`apps/screener/views.py`) uses standard Django filters.
*   Instead of reloading the page on every filter change, the HTML form has `hx-get="/screener/results/" hx-target="#results-table"`. Django returns just the `_results.html` fragment, making the screener feel like a fast React Single Page Application.

### E. Financial Calculators (`apps/calculators/`)
*   **SIP / Step-Up SIP:** Future value of annuities formulas.
*   **SWP (Systematic Withdrawal Plan):** Calculates depletion over time by adding monthly expected return and subtracting withdrawal amount.
*   **Tax Calculator:** Implements current Indian Mutual Fund taxation rules (e.g., 12.5% LTCG above ₹1.25 Lakh for Equity, standard income slab for Debt).

---

## 6. How to Use This Document

If you are an AI assistant inheriting this project, follow these guidelines:
1.  **Never try to pre-load all 14,000 funds.** Stick to the lazy-loading architecture utilizing `services.prepare_fund_for_display(amfi_code)`.
2.  **Data Processing:** If editing metrics, edit `apps/analytics/engine.py` and ensure you use vectorized Pandas operations. Do not iterate over Django querysets for math.
3.  **HTMX Principles:** Keep JavaScript to an absolute minimum. Use HTMX for interactivity (e.g., the market ticker, search bar, and screener).
4.  **Resilience:** All APIs (`mfapi.in`, `captnemo`) have rate limits or downtime. Ensure all HTTP calls are wrapped in `try/except` with sensible UI fallbacks.

## 7. Current Project Status
- Phase 1 (Lazy Loading Backend, Caching, Core Models) -> **COMPLETED**.
- Phase 2 (Calculators, Screener, Portfolio Parser, Recommendations Engine, WeasyPrint PDF Reports) -> **COMPLETED**.
- **Next Steps:** Open source release, containerization (Docker), and deployment (Postgres + Render).
