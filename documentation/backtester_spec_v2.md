# Mutual Fund Strategy Backtester — Product Specification

> **Design intent:** Give the user flexible, composable primitives so they can construct and test any strategy themselves — not pre-built templates that do the thinking for them. Minimum features, maximum flexibility.

---

## Core Flow (5 steps, always visible)

```
1. Add Assets  →  2. Configure Rules  →  3. Set Simulation  →  4. Run  →  5. Analyse
```

The UI is two panels: a **left builder panel** (steps 1–4) and a **right results panel** (step 5, shown after Run). Steps 1–4 are always editable; hitting Run at any time re-runs with current settings.

---

## Step 1 — Asset Selection

### What the user does
Picks assets one at a time and adds them to a list. The list is the portfolio.

### UI controls
| Control | Detail |
|---|---|
| **Type toggle** | `Index` / `Mutual Fund` — switches the search endpoint |
| **Search box** | Type-to-search by name, AMC, or ISIN. Results appear as a dropdown, 5–10 items at a time. |
| **Add button** | Adds the selected result as a card in the asset list below |
| **Asset card** | Shows: name, scheme code, type (Index/MF), plan (Direct/Regular for MF), option (Growth/IDCW for MF), inception date, and a remove button |
| **Inception date display** | Fetched on add; shown below the fund name so the user knows the earliest valid start date |

### Data fetched on add
- Fund/index metadata (name, code, category, AMC, plan, option)
- Inception date
- NAV/index series is **not** fetched yet — only fetched when Run is hit

### Constraints
- At least one asset required to run
- No duplicates in the list
- For **Switch** rules (Step 2), both the source and destination fund must already be in the asset list

---

## Step 2 — Rule Configuration (per asset)

Each asset card has a **`+ Add Rule`** button. A rule defines *how money flows into or out of* that asset. Multiple rules per asset are allowed and they compose (e.g., a SIP + a Sell rule on the same fund).

### 2A. Rule types

#### SIP (Systematic Investment Plan)
Regular periodic investment into the asset.

| Field | Input type | Notes |
|---|---|---|
| Amount | Number (₹) | Per-instalment amount |
| Frequency | Dropdown | Daily / Weekly / Monthly / Quarterly |
| Start date | Date picker | Must be ≥ inception date; ≥ simulation start |
| End date | Date picker | Leave blank = runs until simulation end |
| Step-up | Optional toggle | Reveals step-up fields below |
| ↳ Step-up type | Dropdown | Absolute (₹/period) / Percentage (%/period) |
| ↳ Step-up amount | Number | ₹ or % depending on type selected |
| ↳ Step-up frequency | Dropdown | Every 6 months / Annually / Custom |
| Trigger condition | Optional button | Opens the Trigger Builder (Step 3) — makes this SIP conditional |

#### Lumpsum
One-time investment into the asset.

| Field | Input type | Notes |
|---|---|---|
| Amount | Number (₹) | |
| Date | Date picker | Must be ≥ inception date; ≥ simulation start |
| Trigger condition | Optional button | Opens Trigger Builder — e.g. "invest only when PE < 18" |

#### SWP (Systematic Withdrawal Plan)
Regular periodic withdrawal from the asset.

| Field | Input type | Notes |
|---|---|---|
| Withdrawal type | Toggle | Amount (₹) / Units / % of holding |
| Amount / Units / % | Number | |
| Frequency | Dropdown | Monthly / Quarterly / Annually |
| Start date | Date picker | |
| End date | Date picker | Blank = simulation end |
| Trigger condition | Optional button | Opens Trigger Builder |

#### Sell (one-time or rule-based redemption)
| Field | Input type | Notes |
|---|---|---|
| Sell type | Toggle | Amount (₹) / Units / % of holding |
| Amount / Units / % | Number | Max 100% of holding; validation enforced |
| Date | Date picker | Or leave blank and use a Trigger condition (required if no date) |
| Trigger condition | Optional button | Opens Trigger Builder — one or the other (date or trigger) must be set |

#### Switch
Sell from one asset and buy into another in the same transaction. Think: parking in debt during expensive equity, or rotating from small-cap to large-cap.

| Field | Input type | Notes |
|---|---|---|
| Switch from | Dropdown | Must be an asset already in the list |
| Switch to | Dropdown | Must be an asset already in the list; different from "from" |
| Amount type | Toggle | Amount (₹) / Units / % of "from" holding |
| Amount | Number | |
| Switch date | Date picker | Or use a Trigger condition |
| Trigger condition | Optional button | Opens Trigger Builder |

> **Note:** Switch is the mechanism for: debt-parking strategies (switch equity → liquid fund when signal fires), relative-valuation rotation (switch small-cap → large-cap when ratio is elevated), and PE-band-driven reallocation.

#### Rebalance
Portfolio-level rule. Sells overweight assets and buys underweight ones back to target weights. Applied to the whole portfolio, not a single asset — so this rule lives at the portfolio level, not on an individual asset card.

| Field | Input type | Notes |
|---|---|---|
| Target allocations | Weight table | One row per asset in the list; weights must sum to 100%. OR: "Find optimal weights" button (opens Monte Carlo optimizer, Step 4B) |
| Rebalance trigger | Radio | Frequency-based / Drift-based / Both |
| ↳ Frequency | Dropdown (if freq) | Monthly / Quarterly / Half-yearly / Annually |
| ↳ Anchor month | Dropdown (if freq) | Jan–Dec |
| ↳ Drift threshold | % field (if drift) | Rebalance when any asset drifts > X% from its target |
| Drift type | Toggle (if drift) | Absolute (±X pp) / Relative (±X% of target) |

The **Rebalance rule** is added via a separate `+ Add Rebalance` button at the portfolio level, below the asset list, not per-asset.

---

## Step 3 — Trigger Builder

A trigger is an optional condition attached to any rule from Step 2. When a trigger is defined, the rule only executes when the condition is satisfied. The same trigger system works for all rule types — SIP pause/activate, lumpsum, sell, switch.

### How it works
When the user clicks "Add Trigger Condition" on any rule, a modal opens with these sections:

### 3A. Signal — what to watch
| Signal type | Fields shown | Description |
|---|---|---|
| **Drawdown from ATH** | Reference asset (dropdown: any asset in list, or a separate index), threshold % | Fire when asset/index is X% below its all-time high. Used for buy-the-dip rules (−5%, −10%, −15%, −25% dip levels) |
| **Relative valuation ratio** | Asset A (dropdown), Asset B (dropdown), ratio threshold, direction (≥ / ≤) | Fire when A÷B crosses a level. Classic use: Nifty Smallcap 250 ÷ Nifty 50 > 1.10 = expensive. Also: fund A ÷ fund B for pair strategies |
| **PE ratio** | Index (dropdown from known PE-tracked indices), band boundaries (user enters values for cheap / neutral / expensive / super-expensive zones) | Fire when the index PE is in a chosen band. Used for PE-band SIP strategies |
| **Moving average (200-DMA)** | Reference asset, position (price above 200-DMA / below 200-DMA) | Fire when the chosen asset is above or below its 200-day moving average. Combined with drawdown for buy-the-dip-in-uptrend filter |
| **RSI** | Reference asset, period (default 14), threshold (e.g. < 30 = oversold, > 70 = overbought) | Fire when RSI crosses the threshold |
| **Portfolio drawdown** | Threshold % | Fire when the user's own backtest portfolio drops X% from its own peak (distinct from any external index) |
| **Calendar date** | Specific date, or recurring (every year on a date, every month on a date) | Simple time-based trigger — for annual rebalancing, annual lumpsum, etc. |
| **Fixed return proxy** | Annual return % | Used for the "cash parking" / synthetic debt return scenario. Not a real signal — just models idle cash at a flat rate. Attach to the debt leg of a switch strategy when no real debt fund is in the portfolio |

### 3B. Action — what the rule does when the trigger fires
The action is already defined by the rule type (SIP, Sell, Switch, etc.). The trigger just controls *when* it fires and — for SIP — can also override *how much*:

| Option | Notes |
|---|---|
| **Execute once** | Fires on the first date the condition is met and never again |
| **Execute every period while true** | Fires every scheduled period (SIP instalment date, etc.) while the condition holds — e.g. pause SIP every month while PE > 28 |
| **Increase amount by X% / ₹X when fired** | For SIP top-ups at dip levels. Example: base SIP ₹10,000; trigger fires at −10% drawdown → invest an extra ₹5,000 |
| **Reduce amount by X% / ₹X when fired** | For SIP scale-down when expensive |

### 3C. Multiple conditions (AND/OR logic)
Users can add more than one condition to a trigger, combined with AND or OR. This allows compound filters like: "fire when PE < 18 **AND** market is in drawdown > 10%."

Limit to 3 conditions max (keeps the UI simple; compound strategies beyond this should be decomposed into multiple rules).

---

## Step 4 — Simulation Settings

Lives at the bottom of the left panel, always visible.

| Setting | Control | Notes |
|---|---|---|
| **Simulation start date** | Date picker | Must be ≥ latest inception date across all selected assets. The app auto-suggests the latest inception date. |
| **Simulation end date** | Date picker | Default: today |
| **Benchmark** | Search box | Same search as Step 1 — pick any index or fund as the performance yardstick |
| **Synthetic debt return rate** | % field | Annual flat rate earned on any idle cash (when no real debt fund is selected for a switch/parking leg). Default 7%. This generalizes the "liquid fund" and "FD" proxies from the transcripts. |
| **Tax** | Toggle: On / Off | If On, show: equity STCG rate, equity LTCG rate, LTCG exemption threshold (₹/year), debt tax rate — all user-editable, pre-filled with current Indian defaults |
| **Exit load** | Toggle: On / Off | If On, each asset's exit load schedule (fetched from metadata) is applied to redemptions/switches |
| **Transaction cost** | Number (₹ or bps) | Flat cost per buy/sell/switch event. Default 0. |
| **Inflation adjustment** | Toggle: On / Off | If On, shows a CPI assumption field (default 6% p.a.) for calculating real returns |

### 4B. Monte Carlo Allocation Optimizer (optional, within Rebalance rule)
Triggered by the "Find optimal weights" button in the Rebalance rule.

| Setting | Control |
|---|---|
| Number of simulations | Slider: 500 / 1,000 / 2,000 (default 1,000) |
| Objective function | Dropdown: Maximize ROMAD / Maximize XIRR / Minimize Max Drawdown / Minimize Volatility / Maximize Sharpe / Maximize Sortino |
| Weight constraints per asset | Optional: min % and max % per asset (prevents extreme concentrations) |

**What it does:** Runs N random weight combinations summing to 100%, simulates each, picks the one scoring best on the chosen objective. Returns: best weight vector, its score, and a scatter plot of all simulated outcomes (risk vs return) so the user sees how sensitive results are to allocation choice.

---

## Step 5 — Data Fetch & Simulation (on Run)

When the user clicks **Run Backtest**:

1. **Fetch** NAV/index series for all selected assets over the simulation window, on demand. No pre-stored data.
2. **Validate** all rules for constraint violations (see Constraints section).
3. **Simulate** day by day:
   - Evaluate any active triggers (Module D logic — signal values computed, conditions checked)
   - Execute scheduled cashflows (SIPs, SWPs, lumpsums) due on this date, respecting trigger conditions
   - Execute any triggered one-time actions (buys, sells, switches)
   - Check the rebalance trigger (if rebalance rule exists); execute rebalance if triggered
   - Apply exit load / transaction cost to anything that traded
   - Update unit holdings (FIFO lots for tax purposes if tax is on), market value, and allocation weights
   - Log every action to the transaction ledger (date, fund, type, units, NAV, ₹ amount, trigger that fired it)
4. **Compute** all analytics (Step 6 metrics)
5. **Display** results in the right panel

A progress indicator is shown during fetch + simulation. If data is unavailable for a date range, a clear error is shown identifying which asset is missing data and what the earliest available date is.

---

## Step 6 — Results & Analytics

Results are organized into tabs, not one giant scroll. Each tab answers one clear question.

---

### Tab 1 — Summary ("Did it work?")

**Portfolio-level summary card (top, always shown):**

| Metric | Description |
|---|---|
| Total invested | Sum of all cashflows in |
| Total redeemed | Sum of all cashflows out |
| Final portfolio value | Market value of all holdings on end date |
| Absolute gain | Final value + redeemed − invested |
| XIRR | IRR over actual cashflow dates — the right return metric when cashflows are irregular (SIPs, lumpsums, withdrawals) |
| CAGR | For any lumpsum-equivalent or full-period view |
| vs Benchmark | Same-period return on the benchmark (as a simple buy-and-hold, same start amount) |

**Per-asset breakdown table:**
One row per asset in the portfolio. Columns: Asset name, invested, redeemed, current value, XIRR, % contribution to total return.

---

### Tab 2 — Risk ("How safe was it?")

| Metric | Description |
|---|---|
| Max drawdown | Largest peak-to-trough decline in portfolio value, shown as % |
| Max drawdown period | Start date → trough date → recovery date |
| Max drawdown days | Days from peak to trough |
| Recovery days | Days from trough back to prior peak |
| Volatility | Annualised standard deviation of daily returns |
| Downside deviation | Std dev computed only over negative-return periods |
| Worst month | Single worst rolling 1-month return |
| Worst quarter | Single worst rolling 3-month return |
| VaR (95%) | The 5th-percentile daily return — "95% of days, you won't lose more than X%" |
| CVaR (95%) | Average of all days worse than VaR |

**Risk ratios card:**

| Metric | Formula |
|---|---|
| Sharpe | (XIRR − risk-free rate) ÷ volatility |
| Sortino | (XIRR − risk-free rate) ÷ downside deviation |
| Calmar | CAGR ÷ \|max drawdown\| |
| ROMAD | XIRR ÷ \|max drawdown\| |

---

### Tab 3 — Consistency ("How reliable was it?")

**Plots (interactive — zoom/pan/fullscreen on each):**

1. **Equity curve** — portfolio value over time, with benchmark overlaid; event markers (rebalances, triggers fired, lumpsums) shown as dots/flags on the curve
2. **Drawdown / underwater chart** — mirrors the equity curve; shows depth and duration of every drawdown; benchmark drawdown overlaid
3. **Annual returns bar chart** — one bar per calendar year; benchmark bar alongside
4. **Monthly return heatmap** — Year × Month grid; colour-coded green/red; makes seasonality and crisis periods immediately visible
5. **Daily return series** — small-multiple scatter or bar chart for volatility/tail inspection

**Rolling return box plots (per-fund and portfolio):**
One panel each for 1Y / 3Y / 5Y / 7Y rolling windows. Each box shows: min, Q1, median, mean, Q3, max. Benchmark shown as a reference box alongside. A smaller box = more consistent regardless of entry date.

**Custom period selector:**
User picks any start + end date from the simulation window and re-runs the Tab 1 + 2 metrics for just that sub-period — useful for isolating a specific market regime (COVID crash, 2018 NBFC crisis, etc.).

---

### Tab 4 — Attribution ("What drove the result?")

**Rule impact table:**
Shows each rule (SIP on Fund A, Switch from Fund A to Fund B, Rebalance, etc.) alongside:
- How many times it fired
- Estimated ₹ impact on final corpus (computed by diffing the simulation with that rule disabled)
- Net of transaction cost and tax attributable to that rule specifically

**Fund contribution chart:**
Bar chart — each fund's contribution to total portfolio return in ₹ and %, so the user can see at a glance which fund did the real work and which was a drag.

**Trigger-event timeline:**
A small chart showing on which dates each trigger condition fired, so the user can verify their rule actually behaved as intended. Click any event to see the signal value that day.

---

### Tab 5 — Adjusted Returns ("Real-world view")

Only relevant if Tax and/or Inflation were turned on in Step 4.

| Metric | Notes |
|---|---|
| Pre-tax XIRR | Standard — same as Tab 1 |
| Post-tax XIRR | After applying STCG/LTCG rules, lot by lot |
| STCG paid | Total short-term capital gains tax across simulation |
| LTCG paid | Total long-term capital gains tax across simulation |
| Tax drag | Pre-tax XIRR − post-tax XIRR — the cost of the strategy's activity level |
| Inflation-adjusted XIRR | Real return after CPI assumption |
| Inflation-adjusted final corpus | What the ending value is worth in today's rupees |

**Disclaimer note (always visible on this tab):**
> Tax calculations use the rates and rules you entered and assume perfect FIFO lot matching. Actual tax liability depends on your personal situation, other gains in the same year, and may change if tax law changes. This is an estimate, not tax advice.

---

### Tab 6 — Transaction Ledger

A filterable, sortable, exportable (CSV) table of every single action the simulation took:

| Column | Description |
|---|---|
| Date | |
| Asset | Fund/index name |
| Rule type | SIP / Lumpsum / SWP / Sell / Switch / Rebalance |
| Direction | Buy / Sell |
| Units | |
| NAV | Price on that date |
| Amount (₹) | |
| Trigger fired | Which trigger condition, if any, caused this action |
| Exit load (₹) | Amount deducted, if applicable |
| Transaction cost (₹) | If set |

Total rows = every trade across the simulation. Filter by asset or rule type to isolate what you want to inspect.

---

### Considerations Panel (always shown alongside results)

A small, persistent side note — not a tab. Appears as a collapsible info card:

> **Things to keep in mind about this backtest:**
> - Results assume **perfect execution** — every trigger fires exactly at the threshold with no delay, hesitation, or missed entry. Real-world execution is harder, especially during fast-moving markets.
> - **Taxes** are estimated. High-turnover strategies (frequent switches, rebalancing) pay more tax and have a larger gap between pre- and post-tax return than it appears before taxes are toggled on.
> - **Liquidity** — some rules assume you have the capital available to deploy exactly when a trigger fires. If you don't, the actual result will differ.
> - **Survivorship bias** — if you're comparing only funds that exist today, you're picking from survivors. Funds that closed or merged aren't in the search results.
> - **Not investment advice.** Past performance is not indicative of future results.

---

## Step 7 — Strategy Save & Compare

### Save
- A **Save Strategy** button (top right of the builder panel, always visible).
- Saves the full configuration: every asset, every rule, every trigger, all simulation settings, and the result headline metrics (XIRR, max drawdown, ROMAD, Sharpe).
- User names the strategy before saving. Saved strategies appear in a **Strategy Library** view (separate page/tab).

### Strategy Library
A list view of all saved strategies. Each row shows:
- Strategy name
- Date saved
- Assets in the strategy (chip list)
- Headline metrics: XIRR, Max DD, ROMAD, Sharpe

Actions per row:
- **Open** — loads the full configuration back into the builder for editing/re-running
- **Compare** — adds this strategy to the comparison selection (up to 4 at once)
- **Delete**

### Compare mode
Selecting 2–4 saved strategies and clicking **Compare** opens a side-by-side view:

**Metrics table:** Every Tab 1 + 2 metric in columns (one column per strategy). Highest/best value in each row highlighted.

**Overlaid charts:**
- Equity curves of all compared strategies on one chart, with benchmark
- Drawdown charts overlaid
- Rolling return box plots side by side

**What-if toggle:**
Inside the compare view, the user can quickly toggle one setting across all compared strategies at once — e.g. "turn Tax on for all" or "change benchmark for all" — and re-run the comparison without going back to edit each strategy individually.

---

## Constraints & Validation (enforced at Run-time and as live warnings in the UI)

| Rule | Constraint | Error / Warning |
|---|---|---|
| Start date | Must be ≥ latest inception date of all assets, and ≥ simulation start date | "Start date is before inception of [fund name]. Earliest valid start: [date]." |
| Sell amount | Cannot exceed 100% of holding at that point in time | "Cannot sell more than 100% of holding. Short selling is not allowed in mutual funds." |
| Sell amount | Cannot exceed the actual ₹ value of the holding on the sell date | "Insufficient units. Portfolio holds ₹X of this asset at this date." |
| Portfolio weight on rebalance | Target weights must sum to exactly 100% | "Weights sum to [X]%. Adjust to reach 100%." |
| Switch | Source and destination must both be in the asset list, and must be different | "Switch destination not in portfolio. Add [fund name] to your asset list first." |
| Switch sell % | Cannot exceed 100% of the source holding | "Cannot switch more than 100% of source holding." |
| PE trigger | Only available for indices with PE data tracked | "PE ratio data not available for this index." (clearly labelled on the signal dropdown) |
| Trigger: "execute once" + SIP | Makes the SIP conditional on a one-time event — system shows a warning that the SIP will only ever fire once | "This SIP will only invest once (when trigger fires). Did you mean 'execute every period while true'?" |
| Simulation window | Cannot be shorter than 1 month | |
| Monte Carlo | Only available when Rebalance rule exists and ≥ 2 assets are in the portfolio | Button is greyed out otherwise |

---

## Data Architecture (Fetch-on-Demand)

No pre-ingestion. All data is fetched at Run time:

| Data | Source | When fetched |
|---|---|---|
| Fund/index search results | mfapi.in / NSE API | As user types in search box (debounced) |
| Scheme metadata + inception date | mfapi.in | On add to asset list |
| NAV history | mfapi.in | On Run, for simulation window only |
| Index / TRI history | NSE API / captnemo.in | On Run |
| Index PE ratio | NSE Indices / captnemo.in | On Run, if PE trigger is used |
| CPI / inflation series | RBI / MOSPI | On Run, if inflation toggle is on |

Results are **cached per (asset + date range)** for the current session so re-runs after minor config changes don't re-fetch data. Cache is cleared on browser refresh.

If a fetch fails, the error is shown inline (which asset failed, why, and a retry button). The simulation does not proceed with partial data.

---

## Build Roadmap

### Phase 1 — Core Simulation (builds on what you already have)
1. Asset selection with search (Index + MF), inception date fetch, asset card list
2. SIP and Lumpsum rules (the two most common cases)
3. Step-Up SIP (absolute and percentage)
4. Simulation engine: cashflow-native, day-by-day loop, FIFO unit tracking
5. Results: Summary tab (XIRR, CAGR, benchmark) + Equity curve + Drawdown chart + Transaction ledger

### Phase 2 — Sell, Switch, Rebalance
6. Sell rule (amount / units / %)
7. Switch rule (the mechanism for all rotation and parking strategies)
8. Rebalance rule (frequency + drift-based, with target weight editor)
9. Exit load and transaction cost modeling
10. Results: Risk tab (all I.2/I.3 metrics) + Attribution tab + Annual/monthly return charts + Heatmap

### Phase 3 — Triggers (unlocks all the "smart" strategies)
11. Drawdown-from-ATH trigger (unlocks buy-the-dip, SIP-pause-when-expensive)
12. Relative valuation ratio trigger (unlocks small-cap/large-cap pair strategies)
13. PE ratio trigger (unlocks PE-band SIP — this is your existing Strategy 4, just needs PE data)
14. Calendar-date trigger (simplest case — already partially there)
15. 200-DMA and RSI triggers
16. Portfolio-drawdown trigger
17. Compound trigger (AND/OR between any two of the above)

### Phase 4 — Realism & Adjusted Returns
18. Tax engine: STCG/LTCG with lot-level FIFO, post-tax XIRR
19. Inflation adjustment toggle
20. Synthetic debt return rate (generalizes existing "Synthetic Debt Return Rate" in your Tactical Overlay)
21. Behavioral-realism note panel (disclaimer card in results)
22. SWP rule

### Phase 5 — Optimization, Statistics & Strategy Management
23. Monte Carlo allocation optimizer (within Rebalance rule)
24. Rolling return box plots (1Y/3Y/5Y/7Y)
25. Consistency metrics (upside/downside capture, % positive months)
26. Strategy save/load (Strategy Library)
27. Multi-strategy compare view with overlaid charts and metrics table
28. What-if toggle inside compare view
29. CSV export of ledger and results
30. Custom period selector inside results
