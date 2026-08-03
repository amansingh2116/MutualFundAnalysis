# Fund Screener — Feature Guide & Developer Reference

The **Mutual Fund Screener** (`/funds/screener/`) is a login-required, full-featured fund discovery tool that lets users filter, sort, and evaluate the complete universe of **Open-Ended Direct Growth mutual funds and all ETFs** (~2,280+ active snapshots) across 30+ metrics.

---

## Key Features

### 1. Persistent Filter Sidebar
The left sidebar contains all always-visible core filters split into sections:

- **Scheme Info**: Scheme Type (Equity/Debt/Hybrid/ETF), Scheme Sub-type, Plan Type
- **Scheme Info (Range)**: AUM, Expense Ratio, Fund Age, NAV, Model Score
- **Returns**: 1M, 3M, 6M, 1Y, 3Y, 5Y, 7Y, 10Y Returns, Rolling 5Y
- **Risk & Consistency**: 3Y Volatility, 5Y Volatility, 5Y Sharpe, 3Y/5Y Sortino, 5Y Max Drawdown, Current Drawdown, 3Y Portfolio Turnover
- **Relative Stats**: 3Y Tracking Error, 3Y Alpha, 5Y Alpha, 3Y Beta, 3Y Info Ratio, 3Y R², Upside/Downside Capture, ROMAD

Every filter has an `ⓘ` info button with a detailed tooltip explaining what the metric means, how to interpret it, and tips for analysis.

### 2. Add Filters Panel
A full-screen overlay panel accessible via the **"+ Add Filter"** button (pinned to the filter sidebar footer). Contains optional filters grouped into categories:

| Category | Filters |
|---|---|
| **Scheme Info** | AUM, Expense Ratio, Fund Age, NAV, Model Score, CRISIL Rating, Fund House, Benchmark, Score Badge |
| **Returns** | 1M, 3M, 6M, 1Y, 7Y, 10Y Returns, 5Y Rolling Return |
| **Risk** | 5Y Volatility, 5Y Sharpe, 3Y/5Y Sortino, 5Y Drawdown, Current Drawdown |
| **Relative Stats** | 3Y Tracking Error, 3Y/5Y Alpha, 3Y Beta, 3Y Info Ratio, 3Y R², ROMAD, Upside/Downside Capture, Min SIP, Min Lumpsum, Lock-in Period, Portfolio Turnover |
| **Returns vs Sub-Category** | Excess Category Returns for 1Y, 3Y, 5Y, and 7Y — how much a fund beats or lags its sub-category average |
| **Median Rolling Returns** | 1Y, 3Y, 5Y, 7Y median rolling returns — consistent long-term performance distribution |
| **Category Peer Metrics** | Avg Alpha (3Y), Avg Beta (3Y), Avg Expense Ratio, Avg Portfolio Turnover across fund's sub-category |

All items in the Add Filters panel also have `ⓘ` info buttons. Categorical filters (Fund House, Benchmark, CRISIL Rating, Model Score Badge, SIP Available) appear as **dynamic sidebar sections** when added.

### 3. Active Filters Popover
Clicking the **"X active filters"** badge at the top opens a full-featured popover:

- **Range metrics** (e.g., AUM, Volatility, Sharpe): Rendered as editable text inputs — type a new value directly.
- **Categorical metrics** (e.g., Fund House, Benchmark, Scheme Category): Rendered as interactive `<select multiple>` dropdowns — pre-selected with current values, change on the fly.
- **Search Query**: Labelled as "Search Query" (not just "q") for clarity.
- **Remove any filter** individually with the `✕` button.
- **Apply Changes** button: applies all edits at once (no page reload until explicitly clicked).
- **Clear All** link: resets all filters instantly.

### 4. Saved Screens (Login Required)
Users can **Save** and **Load** named screener configurations (filters + view settings):

- **Save Screen** button: opens a modal to enter a screen name. Shows all existing screens with an **Overwrite** button so users can update a screen without re-naming it.
- **Screens** button: opens a dropdown showing all saved screens with **Load** buttons.
- Same-name saves are blocked with an error; user must rename or overwrite explicitly.

### 5. View Tab (Column Selection)
A **View** button in the toolbar opens a dropdown listing all available columns. Users can toggle any column on/off. View settings are persisted per saved screen.

### 6. Column Headers with Tooltips
Every sortable column header in the results table has an `ⓘ` tooltip button. Clicking a column header sorts the table ascending/descending.

### 7. Benchmark Column
Long benchmark names (e.g., "NIFTY 50 HYBRID COMPOSITE DEBT 65:35 INDEX") are constrained within their column width with word-wrap — no overflow into adjacent cells.

---

## JavaScript Architecture

All screener JavaScript is embedded inline in `templates/funds/screener.html`. Key sections:

| Section | Purpose |
|---|---|
| `const FILTER_META` | Metadata for each range filter (label, min, max, step, presets, param name) |
| `const TOOLTIPS` | Tooltip attribute strings for all dynamic filters (used in dynamically-built widgets) |
| `buildRangeWidget(key, meta)` | Renders a collapsible range-slider filter block |
| `buildCategoricalWidget(key, data)` | Renders a collapsible checkbox filter block |
| `initRangeControls(ctx)` | Initialises dual-range slider + value display for any context |
| `initInfoTooltips(ctx)` | Binds `ⓘ` tooltip popups (delegates to `main.js` engine) |
| Active Filters popover handler | Dynamically reads URL params, builds editable inputs/dropdowns for each |
| Dynamic Filters panel | Tracks which optional filters are active; shows/hides sidebar sections |
| Save/Load Screens | Reads/writes named screens to `localStorage`; supports overwrite |

---

## Data Flow

1. User submits filter form → Django view (`apps/funds/views.py` → `ScreenerView`) receives GET params
2. View queries `FundScreenerSnapshot` table (pre-computed by `populate_screener` management command)
3. Results paginated and returned to template as context
4. Client-side JS handles sort-toggle, view-column toggles, range sliders, active filter popover

---

## Screener Snapshot Model

Pre-computed snapshots are stored in `apps/funds/models.py` → `FundScreenerSnapshot`. Run the following to rebuild:

```bash
python manage.py populate_screener
# Or with a limit for testing:
python manage.py populate_screener --limit=100
```

Each snapshot contains computed values for all 30+ metrics including CAGR, Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Tracking Error, excess category returns (1Y/3Y/5Y/7Y), and more.

> **Note on short-history funds:** Funds with less than 1 year of NAV history appear in the screener with `null` for metrics that require more data (e.g. 1Y CAGR, 3Y volatility). These display as `--` in the UI and sort to last in sortable columns.

---

## Access Control

The screener requires login. Unauthenticated users are redirected to the login page with `?next=/funds/screener/` so they return after logging in.

---

## CSS

Screener-specific styles are in `static/css/screener.css`. Key class namespaces:

| Prefix | Purpose |
|---|---|
| `.filter-block` | Collapsible sidebar filter sections (range + categorical) |
| `.dyn-*` | Dynamically added categorical filter blocks |
| `.fp-*` | Add Filters panel items and layout |
| `.afp-*` | Active Filters popover layout |
| `.toolbar-button` | Header action buttons (Save Screen, Screens, Reset) |
| `.active-filter-badge` | "X active filters" badge button |
| `.score-pill` | Coloured score badge in results table |
