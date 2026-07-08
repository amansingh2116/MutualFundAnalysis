# Backtester V2 — Changelog & Pending Work

## v2.2 — July 2026

### ✅ Completed (this release)

#### Backtester Hub & Strategy Management
- **Backtester Hub landing page** (`/portfolio/backtester/`) — two-card grid with _Build & Test Strategy_ and _Saved Strategies_ entry points; the old `/portfolio/backtester/` URL now routes to the hub, build UI is at `/portfolio/backtester/build/`
- **Strategy Compare page** (`/portfolio/strategies/compare/?ids=...`) — select 2–4 saved strategies from the list and compare them side-by-side with equity curves, risk metric cards, annual return bar charts, and rolling return summary tables

#### Save & Load (Fixed)
- `SavedStrategy` model: columns `plan_json` and `last_result_json` — compare page reads `last_result_json` to avoid re-running each simulation
- `loadStrategy()` now reads `plan.settings.start_date` (not `plan.start_date`) to match `buildPlan()` output
- `@json_login_required` decorator ensures unauthenticated AJAX returns JSON 401 (not HTML redirect)
- `strategies.html` — search by name/description, checkbox multi-select (max 4), "Compare Strategies" button routes to compare page

#### Tax Calculation (Re-enabled & Improved)
- Tax settings panel added to the simulation settings sidebar (collapsed by default)
- **User-configurable rates**: Equity STCG %, Equity LTCG %, LTCG annual exemption (₹), Debt/slab rate %
- Rates are saved into `plan.settings` JSON and restored on `loadStrategy()`
- Disclaimer note explains rates change over time and to update before running accuracy-critical analyses
- Tax tab in results panel shows total STCG/LTCG paid and post-tax XIRR

#### Consistency Tab — New Analysis Charts
- **Daily Return Distribution histogram** (`dailyReturnDistributionChart`) — Plotly histogram of all daily portfolio returns (violet)
- **Monthly Return Distribution histogram** (`monthlyReturnDistributionChart`) — Plotly histogram of monthly portfolio returns (green)
- **Rolling Return Trend chart** (`rollingTrendChart`) — time-series line of rolling CAGR (portfolio + benchmark) over each investment-start date; 3Y / 5Y / 7Y window buttons; metric cards showing avg, vol, best, worst
- Rolling Return Distribution chart (`rollingDistributionChart`) now shows grouped box plots per window with benchmark overlay (fixed)
- Both distribution charts and rolling-trend chart are included in the per-tab Plotly relayout set so they resize correctly when the tab is shown

#### Summary metrics for daily/monthly returns
- `renderDailyMonthlyStatCards()` function: shows Daily Avg Return, Daily Volatility, Monthly Avg Return, Monthly Volatility, Best Month, Worst Month as inline metric cards above the distribution charts

---

## v2.1 — July 2026

### ✅ Completed Fixes & Improvements

#### Backend (`backtester_v2.py`)
- **Inflation (wbgapi)**: Fixed `_fetch_wbgapi_cpi_rate()` to use `wb.data.DataFrame()` instead of the deprecated `wb.data.fetch()` — confirmed working with India CPI avg ~5%
- **Sharpe Ratio**: Trimmed leading zeros from portfolio series before computing Sharpe/Sortino to prevent division artifacts from pre-investment periods
- **Moving Average (MA) trigger**: Made the lookback period configurable (`params.period`, default 200); minimum data requirement adjusts dynamically
- **Per-asset contribution**: Fixed `_build_per_asset_summary()` with additional `logger.debug` for NAV lookup tracing

#### Frontend (`backtester.html`)
- **PE/PB/DivYield signals**: Fully removed from trigger signal dropdown, condition params renderer, and all related JS/HTML — no more failed fetches
- **Monthly Return Heatmap**: Fixed Plotly treating month abbreviations as dates by adding `xaxis.type:'category'` — now renders correct Year × Month grid with color-coded cells, month headers at top
- **Fund Contribution Chart**: Same category-axis fix — fund names now correctly shown as bar labels; added value labels above bars
- **Rolling Returns**: Removed box plot; now shows only **Best / Average / Median / Worst** metric cards per 3Y / 5Y / 7Y window
- **Drawdown Chart**: Added benchmark drawdown as orange dashed line alongside portfolio drawdown
- **Drawdown ATH trigger**: Replaced hardcoded asset `<select>` with live search (same pattern as RSI/MA) — any fund or index can be selected; quick-pick buttons for current portfolio assets shown as shortcuts
- **Considerations panel**: Updated with accurate STCG/LTCG tax rates, exit load rules, and stamp duty notes (replaces generic placeholders)
- **Save Strategy**: Fixed `@json_login_required` decorator so unauthenticated AJAX calls receive JSON 401 instead of HTML redirect (fixes "Unexpected token '<'" error)
- **Load Strategy**: Fixed `loadStrategy()` to read `plan.settings.start_date` (not `plan.start_date`) — matches `buildPlan()` output structure
- **Monte Carlo toggle**: Fixed element ID mismatch (`toggleMC` → `toggleMc`) so green "on" state correctly activates

#### Database / Models
- **`SavedStrategy` model**: Added `plan_json` and `last_result_json` columns via migration `0003_fix_savedstrategy_table` (drops and recreates table to match correct schema — old table had mismatched `payload`/`metrics` columns)
- **`strategies.html`**: Created missing template for the `/portfolio/strategies/` page

---

## Portfolio Dashboard — v2.2 (same release)

### ✅ New tabs in Portfolio Dashboard (`/portfolio/<pk>/`)
- **Overlap Matrix tab**: Inline fetch of the overlap API (`/portfolio/<pk>/overlap/?format=json`) on demand; renders an interactive Plotly heatmap (colorscale 0–100 %) + HTML table of pairwise stock-level overlaps without navigating away
- **Benchmark Analysis tab**: Inline benchmark runner — user builds a custom blended benchmark by adding indices + weights, then runs the analysis; displays Portfolio, Default Blended Benchmark, Custom Benchmark (if set), and NIFTY 50 equity growth curves alongside a metrics table (XIRR, Alpha, Beta, Sharpe, Sortino, Capture Ratios)
- Both tabs call the existing `/portfolio/<pk>/overlap/` and `/portfolio/<pk>/benchmark/` views with `?format=json` (the views now return JSON when `Accept: application/json` is set)

---

## 🔴 Pending (Not Yet Implemented)

1. **Date Validation** — Validate rule/sim dates against fund inception dates in the frontend; auto-adjust start date with per-fund error messages
2. **Custom Weighted Benchmark (backtester)** — UI to pick funds/indices with weights; backend blended series computation for the backtester benchmark (separate from the portfolio dashboard benchmark)
3. **PE/PB/DivYield triggers** — Deferred; niftyindices.com blocks server-side requests. Will revisit if a reliable data source is found
4. **Expanded Drawdown Index** — Select any index for the ATH drawdown chart in the Consistency tab (separate from trigger conditions)
5. **Manual Testing** — Do manual testing of some strategies and compare with backtester results for accuracy

---

## 🗑️ Removed Features (by design)

- Exit Load simulation UI (informational note added to Considerations panel instead)
- Transaction Cost input (stamp duty ~0.005% noted in Considerations panel)
- Synthetic Debt Rate global setting (moved to per-rule parameter if Switch rule is used)
- CAGR metric cards (XIRR is used as the primary return metric throughout)
- PE/PB/DivYield trigger signals (removed from UI — data source unavailable server-side)
