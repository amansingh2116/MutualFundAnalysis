# Financial Calculators — Developer & User Reference

This document covers all financial calculators available at `/calculators/`. It describes each calculator's purpose, inputs, calculation logic, output, and the URL routes they are served from.


---

## Calculator Architecture

### Two Modes per Calculator

Most calculators support two modes:

| Mode | Description |
|------|-------------|
| **Generic (Projection)** | Uses user-supplied expected return % to project a future outcome |
| **Historical (NAV-based)** | Uses actual historical NAV data fetched on-demand from `mfapi.in` to simulate a real investment |

### Backend

All calculation APIs live in `apps/calculators/views.py`. The file exports:
- **Page views** (render templates): `sip_view`, `lumpsum_view`, `swp_view`, `research_report_calc_view`, etc.
- **API endpoints** (return JSON): `calc_sip_api`, `calc_lumpsum_api`, `calc_swp_api`, etc.
- **NAV-based endpoints**: `calc_nav_sip_api`, `calc_nav_lumpsum_api`, `calc_nav_stp_api`, etc.
- **Protected Tools**: `research_report_calc_view` requires user authentication (`@login_required`).


### Frontend

Templates live in `templates/calculators/`. All calculators use:
- Vanilla JS (no frameworks)
- Plotly.js for charts
- `initInfoTooltips()` for ⓘ info buttons — see `documentation/UI_TOOLTIPS.md`
- Consistent `info-btn` class with `data-t-*` attributes for every input/metric

---

## Calculator 1 — SIP Calculator

**Route:** `/calculators/sip/`  
**Template:** `templates/calculators/sip.html`  
**API:** `POST /api/calculators/sip/` → `calc_sip_api`  
**NAV API:** `POST /api/calculators/nav/sip/` → `calc_nav_sip_api`

### Inputs
| Field | Default | Notes |
|-------|---------|-------|
| Monthly SIP Amount (₹) | ₹10,000 | |
| Investment Period (years) | 10 | |
| Expected Annual Return (%) | 12% | Generic mode only |
| Fund selection + date range | — | Historical mode |
| SIP frequency | Monthly | Monthly / Quarterly |
| SIP day | 1st | Day of month |

### Calculation Logic
**Generic mode:**
```
For each month: total_value = (total_value + monthly) * (1 + monthly_rate)
CAGR = (FV / invested)^(1/years) - 1
```

**Historical mode:**
- Fetches actual NAV series for each selected fund
- Aligns start date to the **earliest common inception date** across all funds
- FIFO-based XIRR computed per fund using actual cashflow dates
- Side-by-side comparison table with fund names (not generic labels)

### Output
- Total Invested, Future Value, Gain (₹ and %)
- CAGR
- Year-by-year stacked area chart
- Historical mode: per-fund XIRR and absolute gain comparison table

---

## Calculator 2 — Step-Up SIP Calculator

**Route:** `/calculators/step-sip/`  
**Template:** `templates/calculators/step_sip.html`  
**API:** `POST /api/calculators/step-sip/` → `calc_step_sip_api`  
**NAV API:** `POST /api/calculators/nav/step-sip/` → `calc_nav_step_sip_api`

### Inputs
| Field | Default |
|-------|---------|
| Starting Monthly SIP (₹) | ₹5,000 |
| Annual Step-Up (%) | 10% |
| Period (years) | 10 |
| Expected Return (%) | 12% |

### Calculation Logic
```
For each year:
  For each month: total_value = (total_value + monthly_sip) * (1 + monthly_rate)
  At year end: monthly_sip *= (1 + step_up_pct)
```

### Output
- Total Invested, Future Value, Gain
- Year-by-year table showing monthly SIP amount at each year

---

## Calculator 3 — Lumpsum Calculator

**Route:** `/calculators/lumpsum/`  
**Template:** `templates/calculators/lumpsum.html`  
**API:** `POST /api/calculators/lumpsum/` → `calc_lumpsum_api`  
**NAV API:** `POST /api/calculators/nav/lumpsum/` → `calc_nav_lumpsum_api`

### Inputs
| Field | Default |
|-------|---------|
| Principal (₹) | ₹1,00,000 |
| Period (years) | 10 |
| Expected Return (%) | 12% |

### Calculation Logic
```
FV = P × (1 + r)^years  [standard compound interest]
```

### Output
- Future Value, Gain, CAGR
- Year-by-year growth chart

---

## Calculator 4 — SWP Calculator

**Route:** `/calculators/swp/`  
**Template:** `templates/calculators/swp.html`  
**API:** `POST /api/calculators/swp/` → `calc_swp_api`

### Inputs
| Field | Default |
|-------|---------|
| Corpus (₹) | ₹10,00,000 |
| Monthly Withdrawal (₹) | ₹10,000 |
| Expected Return (% p.a.) | 8% |

### Calculation Logic
```
Each month:
  interest = balance × monthly_rate
  balance = balance + interest - withdrawal
Loop until balance ≤ 0 or 600 months reached
```

### Output
- Months/years corpus sustains
- Total withdrawn, remaining corpus
- Month-by-month balance decay chart

---

## Calculator 5 — STP Calculator (Systematic Transfer Plan)

**Route:** `/calculators/stp/`  
**Template:** `templates/calculators/stp.html`  
**API:** `POST /api/calculators/stp/` → `calc_stp_api`  
**NAV API:** `POST /api/calculators/nav/stp/` → `calc_nav_stp_api`

### Inputs
| Field | Default |
|-------|---------|
| Corpus (₹) | ₹10,00,000 |
| Monthly Transfer (₹) | ₹10,000 |
| Source Fund Return (%) | 6% |
| Target Fund Return (%) | 12% |

### Calculation Logic
```
Each month:
  Source grows: source += source × source_rate
  Transfer deducted: actual_transfer = min(transfer, source); source -= actual_transfer
  Target grows: target += target × target_rate
  Target receives: target += actual_transfer
```

Standard convention: source grows first, then transfer is deducted; target grows, then receives transfer.

### Output
- Source balance, target balance, combined value over time
- Total transferred, final combined value
- Historical NAV mode: actual source and target fund XIRR

---

## Calculator 6 — XIRR Calculator

**Route:** `/calculators/xirr/`  
**Template:** `templates/calculators/xirr.html`  
**API:** `POST /api/calculators/xirr/` → `calc_xirr_api`

### Inputs
- Arbitrary cashflow rows: each row has a **Date** and **Amount** (negative = investment, positive = redemption)
- At least 2 rows required; must include both negative and positive values

### Calculation Logic
- Delegates to `_compute_xirr()` in `apps/analytics/engine.py`
- Uses `scipy.optimize.brentq` (via Newton's method) to find the IRR
- Returns `None` if it fails to converge

### Output
- Annualised XIRR (%)
- Convergence error shown if XIRR cannot be computed

---

## Calculator 7 — Goal Planner

**Route:** `/calculators/goal/`  
**Template:** `templates/calculators/goal.html`  
**API:** `POST /api/calculators/goal/` → `calc_goal_api`

### Inputs
| Field | Default |
|-------|---------|
| Target Amount (₹) | ₹50,00,000 |
| Time Horizon (years) | 15 |
| Expected Return (%) | 12% |
| Inflation Rate (%) | 6% |

### Calculation Logic
```python
# Inflation-adjusted target
real_target = target × (1 + inflation)^years

# Monthly SIP required (annuity-due formula)
monthly_rate = annual_rate / 100 / 12
monthly_sip = real_target × r / ((1+r)^n - 1) × (1+r)

# Lumpsum alternative
lumpsum_needed = real_target / (1 + annual_rate/100)^years
```

### Output
- Inflation-adjusted target amount
- Required monthly SIP
- Lumpsum alternative to invest today

---

## Calculator 8 — Net Worth Calculator

**Route:** `/calculators/net-worth/`  
**Template:** `templates/calculators/net_worth.html`

Fully client-side (no API call). All computation in browser JS.

### Inputs
25+ asset classes across:
- **Liquid**: Savings, FD, Liquid funds
- **Investments**: Equity MF, Debt MF, Direct Equity, NPS, etc.
- **Physical**: Real estate, gold, vehicle, etc.

9 liability classes:
- Home loan, car loan, personal loan, credit card, education loan, etc.

### Output
- Total Assets, Total Liabilities, Net Worth
- Solvency Ratio (Assets ÷ Liabilities) with color-coded bar
- Plotly donut chart (assets by category)
- Breakdown bar chart by category

---

## Calculator 9 — Rolling Returns Calculator

**Route:** `/calculators/rolling/`  
**Template:** `templates/calculators/rolling.html`

### Inputs
- Up to 5 funds (by AMFI code or name search)
- Date range: start date, end date
- Rolling window: 1Y, 2Y, 3Y, 5Y, 7Y, 10Y
- Custom benchmark override

### Calculation Logic
- Fetches historical NAV for each fund
- Applies `pandas.rolling(window_days).apply(cagr_fn)` over the NAV series
- Returns daily rolling CAGR time-series for each fund and benchmark

### Output
- Line chart: rolling CAGR vs time for all selected funds + benchmark
- Color-coded fund chips
- Stats table: min, max, median, win rate vs benchmark per fund

---

## Calculator 10 — Fund Overlap Checker

**Route:** `/calculators/overlap/`  
**Template:** `templates/calculators/overlap.html`  
**API:** `POST /api/calculators/overlap/` → `calc_overlap_api`

### Inputs
- Two AMFI fund codes (searched by name)

### Calculation Logic — Minimum Weight Method

For each stock present in **both** funds:
```
overlap_contribution = min(weight_fund1, weight_fund2)
overlap_score = Σ overlap_contribution
```

This is the industry-standard method — it represents true duplicated exposure (as a % of AUM), and avoids double-counting.

**Venn Diagram values:**  
Each circle's displayed percentage is count-based: `exclusive_count / total_count` for that fund. This shows the proportion of *unique stocks* (not weights) for visual differentiation.

### Output
- Venn Diagram: three regions (Fund A exclusive, Overlap, Fund B exclusive)
- Overlap Score %
- Three tabbed tables: Common Holdings, Only in Fund A, Only in Fund B
- Inline horizontal weight bars (blue = Fund A, orange = Fund B)
- Methodology explanation box

---

## Calculator 11 — Fund Comparison Calculator

**Route:** `/calculators/compare/`  
**Template:** `templates/calculators/compare.html`  
**API:** `/api/funds/<amfi_code>/compare-summary/` (per-fund summary fetch)

### Inputs
- Up to 5 funds (searched by name, added as chips)

### Sections
| Tab | Metrics |
|-----|---------|
| **Overview** | AUM, Inception Date, Expense Ratio, Min SIP, Min Lumpsum, Portfolio Turnover, Fund Manager |
| **Returns** | Trailing returns (1M, 3M, 6M, 1Y, 3Y, 5Y), CAGR chart |
| **Risk** | Volatility (Std Dev), Sharpe, Sortino, Alpha, Beta, Max Drawdown, Downside Capture, Upside Capture, R², Tracking Error, Information Ratio |
| **Portfolio** | Top 10 Holdings weight, Sector allocation, Cash % |

### Best Badge Logic

Each metric has a correct "higher is better" or "lower is better" determination:

| Metric | Better |
|--------|--------|
| AUM | Higher |
| Inception Date | Earlier (older) |
| Expense Ratio | Lower |
| Portfolio Turnover | Lower |
| Returns (all periods) | Higher |
| Sharpe, Sortino, Alpha, Information Ratio | Higher |
| Volatility (Std Dev), Beta, Max Drawdown, Downside Capture, Tracking Error | Lower |
| Top 10 Holdings Weight | Lower (= more diversified) |
| R² | No best badge (context-dependent) |
| Min SIP / Min Lumpsum | No best badge |

---

## Calculator 12 — Tax Calculator (FY 2025-26)

**Route:** `/calculators/tax/`  
**Template:** `templates/calculators/tax.html`

Fully client-side — all computation in browser JS. No sensitive data is sent to the server. Compliant with Budget 2024 and Budget 2025 tax rules.

### Tab 1 — Portfolio Tax Calculator

Multi-fund capital gains calculator. Add multiple funds with their actual purchase/sale data.

**Per-fund inputs:**
- Fund Name (optional label)
- Fund Type (12 types supported)
- Purchase Date, Sale Date
- Invested (₹), Redeemed (₹)
- IDCW Received (₹)
- Exit Load (₹)

**Tax profile inputs:**
- Income Tax Slab (0%, 5%, 10%, 15%, 20%, 30%)
- LTCG from Stocks used (₹) — to track your ₹1.25L annual equity LTCG exemption
- Carry-forward STCL (₹), LTCL (₹) from prior years

**Fund Type → Tax Classification:**

| Fund Type | STCG | LTCG | LT Threshold |
|-----------|------|------|-------------|
| Equity Fund | 20% | 12.5% | > 12 months |
| ELSS | Always LTCG | 12.5% | Lock-in 36 months |
| Arbitrage | 20% | 12.5% | > 12 months |
| Aggressive Hybrid | 20% | 12.5% | > 12 months |
| Balanced Advantage | 20% | 12.5% | > 12 months (if ≥65% equity) |
| Debt Fund (post Apr 2023) | Slab rate | Slab rate | No LT — always slab |
| Debt Fund (pre Apr 2023) | Slab rate | 12.5% | > 36 months |
| Gold ETF (listed) | Slab rate | 12.5% | > 12 months |
| Gold FoF (unlisted) | Slab rate | 12.5% | > 24 months |
| International ETF | Slab rate | 12.5% | > 12 months |
| International FoF | Slab rate | 12.5% | > 24 months |
| Conservative Hybrid | Slab rate | 12.5% | > 24 months |
| Liquid / Ultra-Short | Slab rate | Slab rate | No LT — always slab |

**Set-off rules (applied in priority order):**
1. STCL → Equity STCG (saves 20%)
2. STCL → Debt/Other STCG (saves slab %)
3. STCL → Equity LTCG (saves 12.5%)
4. STCL → Non-Equity LTCG (saves 12.5%)
5. LTCL → Equity LTCG only
6. LTCL → Non-Equity LTCG only
7. ₹1.25L Equity LTCG Exemption applied last

**Output:**
- Per-fund summary pill (STCG/LTCG/Loss) with estimated tax
- Total Tax Payable (with 4% health & education cess)
- Post-tax value and net return
- Set-off box (what losses offset what, and savings amount)
- Breakdown table (gain, rate, tax per category)
- Donut chart (Principal / Post-Tax Gain / Tax Paid)
- Smart Alerts: "Hold X more days to save ₹Y", unused loss carry-forward warnings, exemption tips

---

### Tab 2 — Tax Loss Harvesting

Three sub-tabs:

**2a. Harvesting Savings Calculator**
- Enter current-year gains (Equity STCG, Equity LTCG, Debt STCG, Non-Equity LTCG) + tax slab
- Add unrealised loss positions (name, loss amount, holding, type, exit load)
- Output: Tax before vs after harvesting, % reduction, per-position exit load vs saving comparison

**2b. Priority Order**
- Ranks your loss positions by tax impact (highest saving first)
- STCL ranked before LTCL (STCL is more flexible — can offset both STCG and LTCG)
- Accounts for exit load in net saving calculation

**2c. Year-End Planner**
- Add all positions (losses as positive numbers, gains as negative)
- Generates sell/hold action plan per position
- Shows potential tax saved by booking all loss positions

---

### Tab 3 — SIP FIFO Tax Calculator

Calculates tax on SIP redemptions using **FIFO (First In, First Out)** method — exactly as SEBI requires.

**Inputs:**
- SIP installment table: date, amount, buy NAV (units auto-computed)
- Fund type
- Redemption date, sell NAV, redemption amount (₹ or partial)

**Logic:**
- Sorts installments oldest-first (FIFO)
- For each installment, determines gain = `(current_value - cost)` per unit
- Applies holding period (purchase date → redemption date) for STCG/LTCG classification
- Applies ₹1.25L LTCG exemption on long-term equity installments

**Output:**
- Per-installment breakdown table: units, buy NAV, cost, sale value, gain, holding period, STCG/LTCG tag
- Total LTCG, STCG, tax payable (with cess)
- Alert: how much you'd save by waiting for remaining installments to turn long-term

---

### Tab 4 — Compare & Plan

Three sub-tabs:

**4a. Growth vs IDCW**
- Compares tax liability if gains are taken as Growth (LTCG/STCG) vs IDCW (always slab rate)
- Shows which option saves more tax in your scenario

**4b. Fund Switch Tax Calculator**
- Enter source fund type, purchase date, switch date, purchase cost, current value
- Calculates exact capital gains tax triggered by switching
- Shows "Wait X months to save ₹Y" if approaching long-term threshold

**4c. Arbitrage vs Liquid Fund**
- Compares post-tax return for short-term parking in Arbitrage (equity tax, 20% STCG) vs Liquid (debt, slab rate)
- Shows tax saving from arbitrage at your slab

---

### Tab 5 — ITR & Filing Guide

- **ITR Form Selector**: Checkboxes for STCG, LTCG > ₹1.25L, losses to carry forward, debt fund redemptions → recommends ITR-1 or ITR-2
- **Key Deadlines** for FY 2025-26 (31 March 2026, 31 July 2026, 31 December 2026)
- **Documents Checklist**: CAMS, KFintech, AIS, Form 26AS, Form 16
- **Schedule CG Guide**: Step-by-step ITR-2 Schedule CG filling instructions
- **Tax-Saving Strategies Recap**: Loss harvesting, hold for LT, ₹1.25L exemption, Growth > IDCW, Arbitrage parking

---

---

## Calculator 13 — Child Education Planner

**Route:** `/calculators/child-education/`  
**Template:** `templates/calculators/child_education.html`  
**API:** `POST /api/calculators/child-education/` → `calc_child_education_api`

### Overview
Calculates the inflation-adjusted future cost of higher education and computes the exact monthly SIP or lump sum needed to fund your child's college degree.

### Presets (Today's Value)
- 🎓 B.Tech / Engineering (India): ₹15,00,000
- 💼 MBA / IIM (India): ₹25,00,000
- 🩺 MBBS / Medical (India): ₹35,00,000
- ✈️ Foreign University Degree: ₹60,00,000

### Inputs
| Field | Default | Notes |
|-------|---------|-------|
| Child Current Age (yrs) | 3 | Range: 0 to 17 |
| College Entry Age (yrs) | 18 | Range: 15 to 25 |
| Current Course Cost Today (₹) | ₹25,00,000 | Total cost of 4Y/2Y degree today |
| Education Inflation Rate (% p.a.) | 10.0% | Education CPI in India (typically 8–12%) |
| Expected Annual Return (%) | 12.0% | Pre-college equity portfolio CAGR |
| Existing Savings Allocated (₹) | ₹0 | Initial lump sum set aside |

### Calculation Logic
```
Years until college N = target_age - current_age
Future Course Cost = current_cost * (1 + edu_inflation)^N
FV Existing Savings = existing_savings * (1 + expected_rate)^N
Net Target Deficit = max(0, Future Course Cost - FV Existing Savings)
Monthly SIP Required = Net Deficit * r_m / (((1 + r_m)^(12*N) - 1) * (1 + r_m))
where r_m = expected_rate / 12
```

### Output
- Required Monthly SIP (₹/mo)
- Inflation-Adjusted Target Cost vs Existing Savings Growth
- Alternative One-Time Lumpsum Today
- Year-by-Year Growth Trajectory Table (Child Age, Total Invested, Portfolio Value, College Cost Projection)
- Educational guide card on Education Inflation & Equity-to-Debt Glide Path Strategy

---

## Calculator 14 — Retirement Planner

**Route:** `/calculators/retirement/`  
**Template:** `templates/calculators/retirement.html`  
**API:** `POST /api/calculators/retirement/` → `calc_retirement_api`

### Overview
Calculates the target retirement corpus using the 25x Annual Expenses Rule (4% Safe Withdrawal Rate / FIRE Rule) and determines the exact monthly SIP required today.

### Inputs
| Field | Default | Notes |
|-------|---------|-------|
| Current Age (yrs) | 30 | Range: 20 to 60 |
| Retirement Age (yrs) | 60 | Range: 40 to 70 |
| Monthly Expenses Today (₹) | ₹50,000 | Core living expenses in today's value |
| Expected Inflation Rate (%) | 6.0% | India average CPI (doubles expenses ~12 yrs) |
| Pre-Retirement Return (% p.a.) | 12.0% | Portfolio CAGR before retirement |
| Existing Retirement Corpus (₹) | ₹0 | Current PF, NPS, MF savings |

### Calculation Logic
```
Years to Retire N = retirement_age - current_age
Future Monthly Expense = monthly_expenses * (1 + inflation)^N
Future Annual Expense = Future Monthly Expense * 12
Target Corpus (25x FIRE Rule) = Future Annual Expense * 25
FV Existing Savings = existing_savings * (1 + pre_rate)^N
Net Corpus Deficit = max(0, Target Corpus - FV Existing Savings)
Monthly SIP Required = Net Deficit * r_m / (((1 + r_m)^(12*N) - 1) * (1 + r_m))
where r_m = pre_rate / 12
```

### Output
- Prominent Retirement Target Corpus Card (e.g. `₹8.62 Cr`)
- Years to Retirement & Inflation-Adjusted Monthly Expense at Retirement
- Required Monthly SIP (₹/mo) & Total SIP Investment Outgo
- Year-by-Year Growth Progression Table (Age, Year, Invested, Portfolio Value, Target Benchmark)
- Educational guide card on 25x Rule & 3-Bucket SWP Strategy

---

## Tool 15 — AMC Comparison Tool

**Route:** `/research/amcs/compare/`  
**Template:** `templates/research/amc_compare.html`  
**API:** `GET /research/amcs/api/compare/?amcs=slug1,slug2,...`

### Overview
Side-by-side comparison of 2–4 Indian Asset Management Companies (AMCs) across AUM, returns, risk, expense ratios, portfolio turnover, sector allocations, and high-conviction stock consensus.

### Features
- Searchable inline AMC picker grid to select/deselect AMCs with real-time filtering
- 22 metrics grouped across 7 dimensions (Scale & Growth, Returns, Risk, Fund Quality, Costs, Philosophy, People)
- Direction-calibrated winner highlights (best metric highlighted in green)
- Side-by-side sector allocation bar charts
- High-conviction stock overlap matrix (stocks held in 3+ funds at each AMC)

---

## Tool 16 — Category Comparison Tool

**Route:** `/research/categories/compare/`  
**Template:** `templates/research/category_compare.html`  
**API:** `GET /research/categories/api/compare/?cats=slug1,slug2,...`

### Overview
Side-by-side comparison of 2–4 SEBI mutual fund sub-categories across 35+ metrics including official SEBI mandates, returns, risk-adjusted metrics, TERs, rolling return consistency, and fund quality score distributions.

---

## Tool 17 — Peer Comparison Calculator

**Route:** `/calculators/peers/`  
**Template:** `templates/calculators/peers.html`  
**API:** `GET /api/funds/<amfi_code>/peers/?max=5` → `peer_comparison_api` (`apps/analytics/api_views.py`)

### Overview
Dedicated peer matching & comparison engine that takes any target mutual fund (selected via search or URL parameter `?amfi=...`) and automatically identifies its 5 closest peers in the same SEBI category using multi-factor fingerprint matching (`apps/funds/peers.py`).

### Key Capabilities
- **Multi-Factor Fingerprint Engine**: Ranks candidate funds by SEBI sub-category, plan type (Direct Growth / ETF), asset class allocation, and AUM size.
- **Side-by-Side Metric Matrix**: Compares target fund against 5 closest peers across NAV, AUM, Expense Ratio, 1Y/3Y/5Y Trailing CAGR, Sharpe Ratio, Sortino Ratio, Max Drawdown, Alpha, Beta, and Model Quality Scores.
- **Winner Highlights**: Highlights top performers per metric with direction-calibrated color badges.
- **One-Click Launch**: Direct "Launch Full Comparison" trigger to populate selected peers into the Fund Comparison Calculator (`/calculators/compare/`).

---

## Calculator 18 — Institutional Research Report Generator

**Route:** `/calculators/research-report/`  
**Template:** `templates/calculators/research_report.html`  
**Access Control:** `@login_required` (Authentication required)  
**Query Params:** `?scheme=<amfi_code>&auto=1`  

### Purpose
Allows authenticated users to generate, view, and download a wall-street grade, multi-page institutional PDF research report for any Indian mutual fund scheme or ETF.

### Key Capabilities
- **Autocomplete Fund Search**: Instant scheme lookups with popular sample pills.
- **Real-Time Async Pre-Fetching**: Progress bar animates through a 5-step analysis sequence while Chrome Headless compiles the PDF in the background. Zero 404 or page-reload delays.
- **In-App PDF Canvas Viewer (`PDF.js`)**: Displays the compiled report inside an in-app viewer with zoom controls, fullscreen toggle, page jump input, and **dynamic scroll-based page number tracking** (`Page X of Y`).
- **Instant Blob Download**: `📥 Download PDF Report` button delivers the pre-rendered PDF file instantly without triggering extra server renders.

---

## URL Reference

| Route | Calculator / Tool | Category |
|-------|------------------|----------|
| `/calculators/` | Hub page (Search & Filter Pills) | Dashboard |
| `/calculators/sip/` | SIP Calculator | 📈 Investment & Growth |
| `/calculators/lumpsum/` | Lumpsum Calculator | 📈 Investment & Growth |
| `/calculators/swp/` | SWP Calculator | 📈 Investment & Growth |
| `/calculators/step-sip/` | Step-Up SIP Calculator | 📈 Investment & Growth |
| `/calculators/stp/` | STP Calculator | 📈 Investment & Growth |
| `/calculators/xirr/` | XIRR Calculator | 📈 Investment & Growth |
| `/calculators/rolling/` | Rolling Returns Calculator | 📈 Investment & Growth |
| `/calculators/research-report/` | Research Report Generator | 🔍 Research & Comparison |
| `/calculators/peers/` | Peer Comparison Calculator | 🔍 Research & Comparison |
| `/research/categories/compare/` | Category Comparison | 🔍 Research & Comparison |
| `/research/amcs/compare/` | AMC Comparison | 🔍 Research & Comparison |
| `/calculators/compare/` | Fund Comparison Calculator | 🔍 Research & Comparison |
| `/calculators/overlap/` | Fund Overlap Checker | 🔍 Research & Comparison |
| `/calculators/goal/` | Goal Planner | 🎯 Goals & Life Events |
| `/calculators/retirement/` | Retirement Planner (25x Rule) | 🎯 Goals & Life Events |
| `/calculators/child-education/` | Child Education Planner | 🎯 Goals & Life Events |
| `/calculators/tax/` | Tax Calculator (FY 2025-26) | 🧾 Tax & Wealth |
| `/calculators/net-worth/` | Net Worth Calculator | 🧾 Tax & Wealth |

---

## Audit & Accuracy Notes

All 18 financial calculators and tools were audited for calculation accuracy, input validation, and UI response:

- **Research Report Generator**: Async fetch stream converts binary PDF to in-memory Blob, rendering high-resolution PDF pages on Canvas via PDF.js with live scroll page tracking.
- **Peer Comparison Calculator**: Fingerprint matching engine strictly enforces category and plan boundaries, returning 5 closest peer matches with side-by-side metrics.
- **Child Education Planner**: 10% default inflation accurately reflects Indian education fee growth. Net gap calculation handles existing savings compound growth.
- **Retirement Planner**: Uses 25x annual expense rule (4% Safe Withdrawal Rate) to compute inflation-adjusted corpus requirement.
- **AMC & Category Compare**: Real-time searchable picker, URL state persistence, guarded API fetches, and side-by-side metric tables.
- **Hub Navigation**: Filter pills and search input allow instant drill-down across all 18 calculators.


