# Backtester V2 — Changelog & Pending Work

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

### 🔴 Pending (Not Yet Implemented)

1. **Date Validation** — Validate rule/sim dates against fund inception dates in the frontend; auto-adjust start date with per-fund error messages
2. **Custom Weighted Benchmark** — UI to pick funds/indices with weights; backend blended series computation
3. **Strategies Compare Page** — Side-by-side comparison of two or more saved strategies
4. **PE/PB/DivYield triggers** — Deferred; niftyindices.com blocks server-side requests. Will revisit if a reliable data source is found
5. **Expanded Drawdown Index** — Select any index for the ATH drawdown chart in the Consistency tab (separate from trigger conditions)
6. Do manual Testing of some strategies and comparing them with backtester results for accuracy
7. saving and comparing strategies

etc...

---

### 🗑️ Removed Features (by design)

- Exit Load simulation UI (informational note added to Considerations panel instead)
- Transaction Cost input (stamp duty ~0.005% noted in Considerations panel)
- Tax simulation UI (STCG/LTCG noted in Considerations panel — full tax mode may return later)
- Synthetic Debt Rate global setting (moved to per-rule parameter if Switch rule is used)
- CAGR metric cards (XIRR is used as the primary return metric throughout)
