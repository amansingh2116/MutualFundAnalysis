# Advanced Mutual Fund Tax Calculator — Implementation Plan
### FY 2025-26 (AY 2026-27) | Budget 2024 & 2025 Compliant

---

## 0. Vision & Principles

**What this calculator does that others don't:**  
Most existing calculators handle one fund at a time, ignore carry-forward losses from previous years, treat IDCW as an afterthought, and give no strategic guidance. This calculator handles a full portfolio of mixed fund types in a single session, applies the correct set-off hierarchy automatically, quantifies every available tax-saving strategy with actual rupee numbers, and explains every result inline — the way a CA would, not the way a form does.

**Design philosophy:**  
- Every technical term has an **ⓘ tooltip** with a one-sentence plain-English explanation  
- Every result comes with a short **"Why this number"** breakdown  
- Inputs give **instant feedback** — no submit button for the calculator tabs  
- The interface is **mobile-first** with a desktop sidebar layout  
- Color language: green = tax-free or saving, amber = taxable, red = tax paid, blue = informational

---

## 1. Application Architecture

The calculator is built as a **single-page React application** with five top-level tabs:

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 MF Tax Calculator  [FY 2025-26]              [🌙] [Share ↗] │
├─────────────────────────────────────────────────────────────────┤
│  [1. Portfolio & Tax]  [2. Tax Loss Harvesting]  [3. SIP Mode]  │
│  [4. Compare & Plan]   [5. ITR Guide]                           │
├──────────────────────────┬──────────────────────────────────────┤
│                          │                                      │
│     LEFT PANEL           │        RIGHT PANEL                   │
│   (Inputs & Funds)       │   (Live Results & Charts)            │
│                          │                                      │
└──────────────────────────┴──────────────────────────────────────┘
```

**State management:** A single global `portfolioState` object (React context or Zustand) holds all fund entries, user tax profile, and carry-forward data. All five tabs read from and write to this shared state so changes in one tab instantly update all others.

---

## 2. Design System

### 2.1 Color Tokens

```css
/* Background & Surfaces */
--bg-page:        #0F1117;   /* deep navy-black */
--bg-card:        #1A1D27;   /* card surface */
--bg-card-hover:  #212536;
--bg-input:       #252837;

/* Text */
--text-primary:   #F0F2FF;
--text-secondary: #9BA3C0;
--text-muted:     #5C6280;

/* Semantic Colors */
--green-gain:     #22C55E;   /* tax-free / savings */
--green-light:    #DCFCE7;
--amber-tax:      #F59E0B;   /* taxable amounts */
--amber-light:    #FEF3C7;
--red-paid:       #EF4444;   /* tax paid / loss */
--red-light:      #FEE2E2;
--blue-info:      #3B82F6;   /* i-button, tips */
--blue-light:     #DBEAFE;
--purple-accent:  #8B5CF6;   /* LTCG highlights */
--teal-accent:    #14B8A6;   /* equity badge */

/* Chart Palette (sequential for fund entries) */
--chart-1: #3B82F6;
--chart-2: #8B5CF6;
--chart-3: #F59E0B;
--chart-4: #22C55E;
--chart-5: #EF4444;
--chart-6: #14B8A6;
```

### 2.2 Typography

```
Display / Headline:  "Plus Jakarta Sans", 700  — large result numbers  
Body:                "Inter", 400/500           — all form text and labels  
Mono:                "JetBrains Mono", 400      — rupee amounts in inputs  
Caption:             "Inter", 12px, #9BA3C0     — tooltip text, footnotes  
```

### 2.3 Key UI Primitives

**FundCard** — expandable card for each fund entry, with a color-coded left border per fund type:

```
┌─ [teal border] ──────────────────────────────── [↑↓ expand] [✕] ─┐
│  🔵 Fund #1 — Mirae Asset Large Cap Fund                          │
│  Type: Equity Fund   |   Invested: ₹1,00,000   |   Gain: ₹34,200│
│  [LTCG] [>12 months] [12.5%]                                     │
└──────────────────────────────────────────────────────────────────┘
```

**InfoTooltip (ⓘ)** — clicking or hovering shows a small floating card:

```
┌─────────────────────────────────────────┐
│ ⓘ  LTCG (Long-Term Capital Gain)        │
│ Profit from selling an equity fund you  │
│ held for more than 12 months. Taxed at  │
│ 12.5% above ₹1.25 lakh per year.        │
└─────────────────────────────────────────┘
```

**TaxBadge** — colored pill showing gain type:

- `[STCG @ 20%]` — amber  
- `[LTCG @ 12.5%]` — purple  
- `[Slab Rate @ 30%]` — red  
- `[Tax Free]` — green  

**SavingChip** — appears in results whenever a strategy saves money:

```
💡 Holding 2 more months saves ₹8,750 in tax
```

---

## 3. Tab 1 — Portfolio & Tax Summary

This is the main calculator. It contains the full portfolio entry, tax profile setup, and a live consolidated tax summary.

### 3.1 Left Panel: Tax Profile

```
┌─────────────────────────────────────────────┐
│  YOUR TAX PROFILE                           │
│                                             │
│  Tax Slab  ⓘ                               │
│  [0% No Tax] [5%] [10%] [15%] [20%] [30%]  │
│                                             │
│  LTCG from Stocks/ETFs this year  ⓘ         │
│  ₹ [____________]                           │
│  (Shares the ₹1.25L equity exemption)       │
│                                             │
│  Carry-Forward Losses (prev. years)  ⓘ      │
│  STCL brought forward: ₹ [__________]       │
│  LTCL brought forward: ₹ [__________]       │
│                                             │
│  Surcharge applicable?  ⓘ                   │
│  [No — income < ₹50L]  [Yes — select tier]  │
└─────────────────────────────────────────────┘
```

**ⓘ tooltips in this section:**

| Term | Tooltip Text |
|------|-------------|
| Tax Slab | Your income tax bracket. Affects tax on debt fund gains and IDCW dividends, which are taxed at your slab rate. |
| LTCG from Stocks this year | If you've also sold stocks or ETFs this year, enter those long-term gains. They share the same ₹1.25 lakh annual exemption with your MF gains. |
| Carry-Forward Losses | Capital losses from past ITR filings that you can still use (up to 8 years from the year they were booked). |
| Surcharge | An extra tax on high income. For income between ₹50L–₹1Cr: 10%; ₹1Cr–₹2Cr: 15%; above ₹2Cr: 15% cap on capital gains surcharge. |

### 3.2 Left Panel: Fund Entries

```
┌──────────────────────────────────────────────────────────────────┐
│  YOUR PORTFOLIO  [+ Add Fund]  [Upload CSV ↑]                    │
│                                                                  │
│  ┌─[teal]──────────────────────────────────────[expand][✕]──┐   │
│  │  Fund #1   Fund Name (optional)  [EQUITY FUND ▾]         │   │
│  │                                                           │   │
│  │  Purchase Date  [📅 ____________]  ⓘ                     │   │
│  │  Sale Date      [📅 ____________]                         │   │
│  │  Invested:  ₹ [__________]   Redeemed: ₹ [__________]   │   │
│  │  — OR —                                                   │   │
│  │  Units: [____]  Buy NAV: [______]  Sell NAV: [______]    │   │
│  │                                                           │   │
│  │  IDCW Received this year: ₹ [______]  ⓘ                 │   │
│  │  Exit Load: ₹ [______]  ⓘ                                │   │
│  │                                                           │   │
│  │  ── RESULT ──────────────────────────────────────────── │   │
│  │  Gain: ₹34,200  |  [LTCG @ 12.5%]  |  Tax: ₹4,275      │   │
│  │  Holding: 14 months ✅ (Long-Term)                       │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [+ Add another fund]                                            │
└──────────────────────────────────────────────────────────────────┘
```

**Fund Type Dropdown Options and Their Tax Rules (shown as a sub-label when selected):**

```
EQUITY FUND          → STCG: 20% if ≤12m | LTCG: 12.5% above ₹1.25L if >12m
ELSS FUND            → Always LTCG (3yr lock-in) | 12.5% above ₹1.25L
DEBT FUND (post Apr 2023) → Slab rate regardless of holding period
DEBT FUND (pre Apr 2023)  → STCG: Slab rate | LTCG: 12.5% if >36m
AGGRESSIVE HYBRID    → Same as Equity (≥65% equity allocation)
CONSERVATIVE HYBRID  → STCG: Slab rate | LTCG: 12.5% if >24m (unlisted)
BALANCED ADVANTAGE   → Default: Equity rules (verify factsheet ≥65%)
GOLD ETF (Listed)    → STCG: Slab rate if ≤12m | LTCG: 12.5% if >12m
GOLD FoF (Unlisted)  → STCG: Slab rate if ≤24m | LTCG: 12.5% if >24m
INTERNATIONAL ETF    → STCG: Slab rate if ≤12m | LTCG: 12.5% if >12m
INTERNATIONAL FoF    → STCG: Slab rate if ≤24m | LTCG: 12.5% if >24m
ARBITRAGE FUND       → Same as Equity fund (equity treatment)
LIQUID / ULTRA-SHORT → Same as Debt fund (post Apr 2023 rules apply)
```

When "DEBT FUND (pre Apr 2023)" is selected, an additional question appears:

```
  ⚠️ Units purchased before 1 April 2023 — are these being sold after 23 July 2024?
  [Yes — apply 12.5% LTCG without indexation]  [No — use old rules with indexation]
```

**CSV Upload format** (downloadable template provided):

```csv
fund_name,fund_type,purchase_date,sale_date,invested_amount,redeemed_amount,idcw_received,exit_load
"Mirae Large Cap","EQUITY",2024-06-01,2026-04-15,100000,134200,0,0
"HDFC Liquid Fund","DEBT_POST_2023",2025-08-01,2026-01-15,500000,526000,0,0
```

### 3.3 Right Panel: Live Tax Summary

```
┌──────────────────────────────────────────────────────────────────┐
│  TAX SUMMARY — FY 2025-26              [Copy Result] [Share ↗]  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TOTAL CAPITAL GAINS BREAKDOWN                                   │
│  ┌──────────────┬────────────┬──────────────────────────────┐   │
│  │ Type         │ Gross Gain │ After Exemption / Set-Off    │   │
│  ├──────────────┼────────────┼──────────────────────────────┤   │
│  │ Equity STCG  │ ₹40,000    │ ₹15,000 (after STCL setoff) │   │
│  │ Equity LTCG  │ ₹1,50,000  │ ₹25,000 (after ₹1.25L exem) │   │
│  │ Debt STCG    │ ₹18,000    │ ₹18,000 (at slab rate)      │   │
│  │ Gold LTCG    │ ₹20,000    │ ₹20,000 (no exemption)      │   │
│  └──────────────┴────────────┴──────────────────────────────┘   │
│                                                                  │
│  SET-OFF APPLIED  ⓘ                                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ STCL available: ₹90,000                                  │    │
│  │ Applied against STCG: −₹80,000                          │    │
│  │ Remaining STCL applied vs LTCG: −₹10,000               │    │
│  │ LTCL available: ₹0                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  EXEMPTIONS APPLIED  ⓘ                                          │
│  ₹1.25 lakh equity LTCG exemption: −₹1,25,000                  │
│  (Stock LTCG already used: ₹0  |  Remaining for MFs: ₹1,25,000) │
│                                                                  │
│  TAX COMPUTATION                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Equity STCG:  ₹15,000 × 20%        =     ₹3,000      │     │
│  │  Equity LTCG:  ₹25,000 × 12.5%      =     ₹3,125      │     │
│  │  Debt STCG:    ₹18,000 × 30% (slab) =     ₹5,400      │     │
│  │  Gold LTCG:    ₹20,000 × 12.5%      =     ₹2,500      │     │
│  │  IDCW Income:  ₹5,000  × 30% (slab) =     ₹1,500      │     │
│  │  ─────────────────────────────────────────────────     │     │
│  │  Sub-total tax:                           ₹15,525      │     │
│  │  + Health & Education Cess (4%):            ₹621       │     │
│  │  ─────────────────────────────────────────────────     │     │
│  │  TOTAL TAX PAYABLE:                       ₹16,146      │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌─────────────────┬────────────────┬────────────────────────┐  │
│  │ Total Invested  │ Total Redeemed │ Post-Tax Return        │  │
│  │ ₹8,18,000       │ ₹9,48,200      │ ₹9,32,054 (13.9% net) │  │
│  └─────────────────┴────────────────┴────────────────────────┘  │
│                                                                  │
│         [Donut Chart: Tax vs Post-Tax Gain vs Principal]         │
│                                                                  │
│  ⚠️ CARRY-FORWARD ALERT                                          │
│  You have ₹0 in unused losses this year.                        │
│  File ITR by 31 July 2026 to preserve loss carry-forward rights. │
└──────────────────────────────────────────────────────────────────┘
```

**Tax Savings Panel** — always shown below the summary:

```
┌──────────────────────────────────────────────────────────────────┐
│  💡 TAX SAVING OPPORTUNITIES FOUND  (saves up to ₹7,800 more)   │
├──────────────────────────────────────────────────────────────────┤
│  1. Fund #3 (Equity) — Hold 47 more days to qualify as LTCG.    │
│     Saves: ₹7,800  [See how ▾]                                   │
│                                                                  │
│  2. You haven't used ₹82,500 of your ₹1.25L LTCG exemption.    │
│     Harvest up to ₹82,500 in other equity gains tax-free.       │
│     [Go to Tax Gain Harvesting →]                               │
│                                                                  │
│  3. Fund #2 (Debt) has an exit load of ₹1,200.                  │
│     The tax saving from the loss is only ₹900. Not worth it.    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Tab 2 — Tax Loss Harvesting

This tab has three sub-tabs:

```
[🌾 Harvesting Savings]  [📊 LTCL vs STCL Strategy]  [📅 Year-End Planner]
```

### 4.1 Sub-tab A: Harvesting Savings

**Purpose:** Given your current realized gains and a portfolio of unrealized losses, compute exactly how much tax you save by harvesting each position.

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: YOUR REALIZED GAINS THIS YEAR                         │
│                                                                 │
│  Realized STCG (Equity)   ₹ [__________]   @ 20%              │
│  Realized LTCG (Equity)   ₹ [__________]   @ 12.5% (>₹1.25L) │
│  Realized STCG (Debt)     ₹ [__________]   @ slab rate        │
│  Realized LTCG (Non-Eq.)  ₹ [__________]   @ 12.5%            │
│                                                                 │
│  Current Tax Bill: ₹64,350   [ⓘ Breakdown]                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: ADD LOSS-MAKING HOLDINGS  [+ Add Position]  [📤 CSV]  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Position 1                                    [✕]        │  │
│  │  Name: [Nifty IT ETF_______]                             │  │
│  │  Unrealized Loss (₹): [−80,000]                          │  │
│  │  Holding Period: [6] months                              │  │
│  │  Type: [STCL (held < 12 months) ▾]  ⓘ                   │  │
│  │  Exit Load: ₹ [0]   ⓘ                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [+ Add Position]                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  HARVESTING RESULT                                              │
│                                                                 │
│  Tax without harvesting:   ₹64,350                             │
│  Tax with harvesting:      ₹33,150                             │
│                                                                 │
│  ████████████████████████░░░░░░░░░░░░░░░░░░░  48.5% reduction  │
│                                                                 │
│  YOU SAVE: ₹31,200                                              │
│                                                                 │
│  ──── HOW THIS WORKS ────────────────────────────────────────  │
│  STCL of ₹1,50,000 applied against:                           │
│    → ₹2,00,000 STCG first: reduces STCG to ₹50,000            │
│    → Remaining ₹0 STCL applied vs LTCG                        │
│  Tax on ₹50,000 STCG @ 20%: ₹10,000                           │
│  Tax on ₹3,00,000 LTCG (after ₹1.25L exempt): ₹21,875         │
│  + Cess: ₹1,275                                                │
│  New total: ₹33,150                                            │
│                                                                 │
│  ⚠️ Exit load of ₹0 on these positions.                        │
│  Net benefit after costs: ₹31,200                              │
│                                                                 │
│  ⚠️ Carry-forward available: ₹0  (all losses used up)          │
│                                                                 │
│  [📋 Copy Result]  [📤 Share]  [🖨 Print]                      │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Sub-tab B: LTCL vs STCL Strategy

**Purpose:** When you have multiple loss positions, the calculator prioritizes which to harvest first for maximum tax efficiency.

```
ADD LOSING POSITIONS — PRIORITIZED AUTOMATICALLY

Total STCG realized this FY: ₹ [3,00,000]
Total LTCG realized this FY: ₹ [2,00,000]

[+ Add Position] (name, unrealized loss ₹, holding months, fund type)

──── OPTIMAL HARVEST ORDER ────────────────────────────────────────

Priority 1 [STCL — offset STCG first, highest rate saved]
  Nifty IT ETF     Loss: ₹80,000    Held: 6 months    Type: STCL
  Tax saved: ₹16,000 (₹80,000 × 20%)

Priority 2 [STCL — any remaining against LTCG]
  Pharma Small Cap  Loss: ₹50,000   Held: 4 months    Type: STCL
  Tax saved: ₹6,250 (₹50,000 × 12.5%)

Priority 3 [LTCL — only against LTCG]
  Infra Fund       Loss: ₹1,20,000  Held: 18 months   Type: LTCL
  Tax saved: ₹15,000 (₹1,20,000 × 12.5%)

──── RESULT ────────────────────────────────────────────────────────

Without harvesting:  ₹72,150
After harvesting:    ₹35,360
You save:            ₹36,790

STCL used: ₹1,30,000   LTCL used: ₹1,20,000   Carry-forward: ₹0

ⓘ WHY STCL IS PRIORITIZED:
   STCL saves 20% per rupee when used against STCG, vs only 12.5%
   when used against LTCG. Always exhaust STCG first with STCL.
```

### 4.3 Sub-tab C: Year-End Tax Planner

**Purpose:** Enter all positions (gains AND losses) to calculate the optimal set of sells before March 31.

```
ENTER ALL PORTFOLIO POSITIONS — GAINS AND LOSSES — OPTIMIZED FOR MARCH 31

[+ Add Position]   Each position has: Name | Gain/Loss (₹) | Holding (months)

Example entries shown:
  Large Cap Equity    Gain: ₹2,50,000   15 months  [LT - Gain]
  Mid Cap Fund        Loss: ₹80,000      8 months  [ST - Loss]
  Nifty 50 ETF        Gain: ₹1,00,000    6 months  [ST - Gain]
  Small Cap Fund      Loss: ₹45,000     20 months  [LT - Loss]

──── YEAR-END HARVEST PLAN ─────────────────────────────────────────

RECOMMENDED ACTIONS:
  ✅ Sell Mid Cap Fund now (STCL ₹80,000 offsets ₹80,000 of STCG)
  ✅ Sell Small Cap Fund now (LTCL ₹45,000 offsets ₹45,000 of LTCG)
  ⏳ Wait 6 more months on Nifty 50 ETF — converts STCG to LTCG

Save ₹22,490 by March 31
Tax without action:   ₹37,050
Tax after action:     ₹14,560
Tax saved this FY:    ₹22,490    (60.7% reduction)

[📋 Copy Plan]  [📤 Share Plan]
```

---

## 5. Tab 3 — SIP Mode

**Purpose:** SIP investors have a unique problem — each installment has its own purchase date and holding period. FIFO must be applied when redeeming. This tab handles that precisely.

### 5.1 SIP Entry Interface

```
SIP FUND DETAILS
  Fund Name: [________________________]
  Fund Type: [EQUITY FUND ▾]

SIP INSTALLMENTS  [+ Add Month]  [📤 Import CSV]
  ┌────────────────────────────────────────────────────────┐
  │ Month     | Invest Date | Amount (₹) | NAV   | Units  │
  ├────────────────────────────────────────────────────────┤
  │ Jan 2024  | 2024-01-05  | 10,000     | 42.50 | 235.29 │
  │ Feb 2024  | 2024-02-05  | 10,000     | 44.20 | 226.24 │
  │ Mar 2024  | 2024-03-05  | 10,000     | 45.80 | 218.34 │
  │ ...                                                    │
  └────────────────────────────────────────────────────────┘

REDEMPTION DETAILS
  Redemption Date: [📅 ___________]
  Redemption Amount (₹): [___________]   OR   Units Redeemed: [_____]
  Sell NAV on redemption date: [_______]
```

### 5.2 SIP Redemption Output (FIFO Applied)

```
SIP REDEMPTION ANALYSIS (FIFO Applied)  ⓘ
  Total Redeemed: ₹1,46,200  from 24 SIP installments (₹10,000/mo since Jan 2024)

  ┌────────────────────────────────────────────────────────────────────┐
  │ SIP Date   │ Units Used │ Buy NAV │ Cost    │ Sale   │ Gain  │Type │
  ├────────────┼────────────┼─────────┼─────────┼────────┼───────┼─────┤
  │ Jan 2024   │ 235.29     │ ₹42.50  │ ₹10,000 │ ₹13,100│ ₹3,100│LTCG │
  │ Feb 2024   │ 226.24     │ ₹44.20  │ ₹10,000 │ ₹12,590│ ₹2,590│LTCG │
  │ ...        │            │         │         │        │       │     │
  │ Nov 2024   │ 179.21     │ ₹55.80  │ ₹10,000 │ ₹ 9,970│ −₹30 │STCG │
  │ Dec 2024   │ 174.23     │ ₹57.40  │ ₹10,000 │ ₹ 9,690│ −₹310│STCG │
  └────────────────────────────────────────────────────────────────────┘

  SUMMARY
  LTCG (>12 months):  Gain: ₹48,200    Tax: ₹0 (within ₹1.25L exemption)
  STCG (<12 months):  Loss: ₹340       Harvestable! Can offset other gains.

  ⚠️ Only 10 of 24 installments are long-term.
  Wait until [March 2026] to make all remaining installments long-term.
  Potential STCG at current NAV if sold now: ₹4,200 @ 20% = ₹840
```

---

## 6. Tab 4 — Compare & Plan

Three comparison tools in one tab.

### 6.1 Growth vs IDCW Comparison

```
GROWTH OPTION vs IDCW OPTION — WHICH COSTS YOU LESS TAX?

  Your Tax Slab: [30%]   Fund Type: [Equity ▾]
  Investment: ₹ [5,00,000]   Holding Period: [24] months
  Expected Gain %: [40%]    IDCW distributed: [15%] of NAV

  ┌─────────────────────────────────────────────────────────┐
  │                 GROWTH OPTION   │   IDCW OPTION         │
  ├─────────────────────────────────┼───────────────────────┤
  │ Total gain                      │ ₹2,00,000  ₹2,00,000  │
  │ Tax on LTCG (12.5%)             │ ₹9,375     —          │
  │ Tax on IDCW at slab (30%)       │ —          ₹22,500    │
  │ Post-tax in your hands          │ ₹1,90,625  ₹1,77,500  │
  │ Effective tax rate              │ 4.7%       11.25%     │
  └─────────────────────────────────┴───────────────────────┘

  ✅ GROWTH OPTION saves you ₹13,125 in this scenario.

  ⚠️ IDCW ONLY makes sense if your tax slab is 0-5% and you
     need regular income. For 20%+ brackets, Growth is almost
     always better.
```

### 6.2 Fund Switching Tax Impact Calculator

```
WHAT HAPPENS IF YOU SWITCH FUNDS?

  Source Fund: [HDFC Short Duration___] [DEBT POST-2023 ▾]
  Purchase Date: [2023-09-01]
  Current Value: ₹ [5,75,000]   Purchase Cost: ₹ [5,00,000]
  Planned Switch Date: [📅]

  ──── SWITCH TAX IMPACT ────────────────────────────────────
  Gain on switch: ₹75,000
  Tax type: STCG (debt post-Apr 2023 → always slab rate)
  Tax @ 30% slab: ₹22,500 + cess ₹900 = ₹23,400

  💡 WAIT OPTION:
  If you wait until [2025-09-01] (24 months from purchase),
  your gain becomes LTCG @ 12.5%.
  Tax would be: ₹75,000 × 12.5% = ₹9,375 + ₹375 cess = ₹9,750
  SAVING BY WAITING: ₹13,650
```

### 6.3 Arbitrage Fund vs Liquid Fund Optimizer

```
ARBITRAGE FUND vs LIQUID FUND (SHORT-TERM PARKING)

  Amount to park: ₹ [10,00,000]
  Duration: [9] months
  Expected Return: [7%] per year
  Your Tax Slab: [30%]

  ┌───────────────────────────┬──────────────┬────────────────────┐
  │                           │ Liquid Fund  │ Arbitrage Fund     │
  ├───────────────────────────┼──────────────┼────────────────────┤
  │ Gain (9 months)           │ ₹52,500      │ ₹52,500            │
  │ Tax Type                  │ STCG @ slab  │ STCG @ 20%         │
  │ Tax Rate                  │ 30%          │ 20%                │
  │ Tax Paid                  │ ₹15,750      │ ₹10,500            │
  │ Post-Tax Return           │ ₹36,750      │ ₹42,000            │
  │ Effective Return %        │ 4.9%         │ 5.6%               │
  └───────────────────────────┴──────────────┴────────────────────┘

  ✅ Arbitrage Fund saves ₹5,250 for a 9-month ₹10 lakh parking.
  ⚠️ Note: Arbitrage funds have some tracking error vs liquid funds.
```

---

## 7. Tab 5 — ITR Filing Guide

A contextual, interactive guide that populates itself from the user's portfolio data.

```
ITR FILING GUIDE — BASED ON YOUR PORTFOLIO

  Based on your entries, here's what you need to file:

  ✅ ITR FORM: ITR-2 (You have STCG/LTCG above ₹1.25L)  ⓘ

  DOCUMENTS TO COLLECT:
  ☐ Capital Gains Statement from CAMS  [How to get it →]
  ☐ Capital Gains Statement from KFintech  [How to get it →]
  ☐ Annual Information Statement (AIS) from IT portal
  ☐ Form 26AS (for IDCW TDS credit of ₹500 in your portfolio)
  ☐ Form 16 from employer (if salaried)

  SCHEDULE CG ENTRIES (pre-filled from your portfolio):
  ┌────────────────────────────────────────────────────────────┐
  │ Section 111A (Equity STCG):           ₹15,000             │
  │ Other STCG (Debt/Non-equity):         ₹18,000             │
  │ Section 112A (Equity LTCG):           ₹1,50,000           │
  │   → Less exemption:                  −₹1,25,000           │
  │   → Taxable LTCG (112A):             ₹25,000              │
  │ Other LTCG (Gold, International):     ₹20,000             │
  └────────────────────────────────────────────────────────────┘

  KEY DEADLINES:
  📅 31 July 2026 — File ITR to preserve any loss carry-forward
  📅 31 March 2026 — Last day to book losses in FY 2025-26

  [📋 Copy All Figures for ITR]  [Open IT Portal →]
```

---

## 8. Calculation Engine — Complete Logic

### 8.1 Holding Period Calculator

```javascript
function classifyHoldingPeriod(purchaseDate, saleDate, fundType) {
  const months = monthDiff(purchaseDate, saleDate);

  const thresholds = {
    EQUITY:               { ltMonths: 12,  term: 'LTCG_EQUITY' },
    ELSS:                 { ltMonths: 36,  term: 'LTCG_EQUITY' },  // always LTCG in practice
    ARBITRAGE:            { ltMonths: 12,  term: 'LTCG_EQUITY' },
    AGGRESSIVE_HYBRID:    { ltMonths: 12,  term: 'LTCG_EQUITY' },
    BALANCED_ADVANTAGE:   { ltMonths: 12,  term: 'LTCG_EQUITY' },  // if ≥65% equity
    DEBT_POST_APR_2023:   { ltMonths: null, term: 'STCG_SLAB' },   // always slab
    DEBT_PRE_APR_2023:    { ltMonths: 36,  term: 'LTCG_NON_EQUITY_12_5' },
    GOLD_ETF:             { ltMonths: 12,  term: 'LTCG_NON_EQUITY_12_5' },
    GOLD_FOF:             { ltMonths: 24,  term: 'LTCG_NON_EQUITY_12_5' },
    INTERNATIONAL_ETF:    { ltMonths: 12,  term: 'LTCG_NON_EQUITY_12_5' },
    INTERNATIONAL_FOF:    { ltMonths: 24,  term: 'LTCG_NON_EQUITY_12_5' },
    CONSERVATIVE_HYBRID:  { ltMonths: 24,  term: 'LTCG_NON_EQUITY_12_5' },
  };

  const rule = thresholds[fundType];

  if (rule.ltMonths === null) return { type: 'STCG_SLAB', months };
  if (months > rule.ltMonths) return { type: rule.term, months };
  return { type: 'STCG', months, isEquity: isEquityFund(fundType) };
}
```

### 8.2 Tax Rate Resolver

```javascript
function resolveTaxRate(gainType, taxSlab) {
  const rates = {
    LTCG_EQUITY:             0.125,          // 12.5% (+ 4% cess)
    LTCG_NON_EQUITY_12_5:   0.125,          // 12.5% (+ 4% cess), NO exemption
    STCG_EQUITY:             0.20,           // 20% (+ 4% cess)
    STCG_NON_EQUITY_SLAB:   taxSlab / 100,  // user's slab rate (+ 4% cess)
    STCG_SLAB:               taxSlab / 100,  // debt/gold short-term → slab
    IDCW:                    taxSlab / 100,  // always slab
  };
  return rates[gainType] ?? 0;
}

function addCess(taxAmount) {
  return taxAmount * 1.04;
}
```

### 8.3 Set-Off Hierarchy Engine

```javascript
function applySetOffHierarchy(gains, losses, prevYearSTCL, prevYearLTCL) {
  let { stcg, ltcgEquity, ltcgNonEquity } = gains;
  let { stcl, ltcl } = losses;

  // Add carry-forward losses
  stcl += prevYearSTCL;
  ltcl += prevYearLTCL;

  // Step 1: Apply STCL against STCG first (saves more — 20% vs 12.5%)
  const stclVsStcg = Math.min(stcl, stcg);
  stcg -= stclVsStcg;
  stcl -= stclVsStcg;

  // Step 2: Apply remaining STCL against LTCG (equity first, then non-equity)
  const stclVsLtcgEquity = Math.min(stcl, ltcgEquity);
  ltcgEquity -= stclVsLtcgEquity;
  stcl -= stclVsLtcgEquity;

  const stclVsLtcgNonEq = Math.min(stcl, ltcgNonEquity);
  ltcgNonEquity -= stclVsLtcgNonEq;
  stcl -= stclVsLtcgNonEq;

  // Step 3: Apply LTCL against LTCG only (CANNOT offset STCG)
  const ltclVsLtcgEquity = Math.min(ltcl, ltcgEquity);
  ltcgEquity -= ltclVsLtcgEquity;
  ltcl -= ltclVsLtcgEquity;

  const ltclVsLtcgNonEq = Math.min(ltcl, ltcgNonEquity);
  ltcgNonEquity -= ltclVsLtcgNonEq;
  ltcl -= ltclVsLtcgNonEq;

  // Step 4: Apply ₹1.25L exemption to equity LTCG only
  const LTCG_EQUITY_EXEMPTION = 125000;
  const exemptionUsed = Math.min(ltcgEquity, LTCG_EQUITY_EXEMPTION - stockLtcgAlreadyUsed);
  const taxableLtcgEquity = Math.max(0, ltcgEquity - exemptionUsed);

  return {
    taxableStcgEquity: Math.max(0, stcg),  // includes non-equity slab STCG separately
    taxableLtcgEquity,
    taxableLtcgNonEquity: Math.max(0, ltcgNonEquity),
    unusedStcl: stcl,    // carry forward
    unusedLtcl: ltcl,    // carry forward
    exemptionUsed,
  };
}
```

### 8.4 Tax Harvest Optimizer (for Tab 2)

```javascript
function optimizeHarvestOrder(lossPositions, realizedGains) {
  // Priority 1: STCL positions — sort by loss size descending
  //             Use against STCG first (saves 20%) then LTCG (saves 12.5%)
  // Priority 2: LTCL positions — only usable against LTCG (saves 12.5%)

  const stclPositions = lossPositions.filter(p => p.type === 'STCL')
    .sort((a, b) => b.loss - a.loss);
  const ltclPositions = lossPositions.filter(p => p.type === 'LTCL')
    .sort((a, b) => b.loss - a.loss);

  // Calculate marginal tax saving per rupee for each position
  stclPositions.forEach(p => {
    const remainingStcg = currentStcg - offsetSoFar;
    p.effectiveSaving = remainingStcg > 0
      ? 0.20 * Math.min(p.loss, remainingStcg) + 0.125 * Math.max(0, p.loss - remainingStcg)
      : 0.125 * p.loss;
    p.netSaving = p.effectiveSaving - p.exitLoad;
  });

  ltclPositions.forEach(p => {
    p.effectiveSaving = 0.125 * p.loss;
    p.netSaving = p.effectiveSaving - p.exitLoad;
  });

  // Filter out positions where net saving is negative (exit load > tax saving)
  return {
    recommended: [...stclPositions, ...ltclPositions].filter(p => p.netSaving > 0),
    notRecommended: [...stclPositions, ...ltclPositions].filter(p => p.netSaving <= 0),
  };
}
```

### 8.5 SIP FIFO Engine

```javascript
function calculateSipFIFO(sipInstallments, redemptionDate, redemptionAmount, sellNAV) {
  // Sort installments by purchase date (oldest first = FIFO)
  const sorted = [...sipInstallments].sort((a, b) => a.date - b.date);

  let remainingRedemptionAmount = redemptionAmount;
  const transactions = [];

  for (const installment of sorted) {
    if (remainingRedemptionAmount <= 0) break;

    const units = installment.amount / installment.nav;
    const currentValue = units * sellNAV;
    const amountToRedeem = Math.min(currentValue, remainingRedemptionAmount);
    const unitsRedeemed = amountToRedeem / sellNAV;
    const costBasis = unitsRedeemed * installment.nav;
    const gain = amountToRedeem - costBasis;
    const holdingMonths = monthDiff(installment.date, redemptionDate);

    transactions.push({
      purchaseDate: installment.date,
      units: unitsRedeemed,
      costBasis,
      saleValue: amountToRedeem,
      gain,
      holdingMonths,
      gainType: holdingMonths > 12 ? 'LTCG' : 'STCG',
    });

    remainingRedemptionAmount -= amountToRedeem;
  }

  return transactions;
}
```

---

## 9. Component Inventory

### 9.1 ⓘ InfoTooltip Component

Every technical term throughout the UI has a tooltip. Full dictionary:

| Term | Tooltip Content |
|------|----------------|
| STCG | Short-Term Capital Gain — profit from selling a fund before the long-term threshold. Equity: 20% tax. Others: at your slab rate. |
| LTCG | Long-Term Capital Gain — profit after the long-term threshold. Equity: 12.5% above ₹1.25 lakh. Gold/Intl: 12.5% (no exemption). |
| STCL | Short-Term Capital Loss — a loss booked before the long-term threshold. Can offset both STCG and LTCG. |
| LTCL | Long-Term Capital Loss — a loss booked after the threshold. Can ONLY offset LTCG, not STCG. |
| ₹1.25L Exemption | The first ₹1.25 lakh of equity long-term capital gains every financial year is completely tax-free. Shared across all equity MFs and direct stocks you sell. |
| FIFO | First-In, First-Out — India's tax law assumes you sell your oldest units first in any partial redemption. Critical for SIP investors. |
| Tax Harvesting | Deliberately selling a loss-making investment to book the loss, using it to reduce tax on other gains. You can immediately buy it back. |
| Carry Forward | Unused capital losses can be saved and used against gains in future years, for up to 8 assessment years. Requires on-time ITR filing. |
| Exit Load | A fee charged by the AMC if you redeem before a certain period. Eats into the benefit of tax-loss harvesting. |
| Section 50AA | The section of the Income Tax Act that covers debt funds (post-April 2023) — taxing them at your slab rate regardless of holding period. |
| Health & Edu Cess | A 4% surcharge on your total income tax. Applies to everyone. Not shown in base rates — always added at the end. |
| ITR-2 | The income tax return form used by investors who have capital gains above ₹1.25 lakh or losses to carry forward. |
| IDCW | Income Distribution cum Capital Withdrawal — the new name for "dividend." Always taxed at your slab rate. TDS of 10% applies if IDCW >₹5,000/year from one AMC. |
| Switch Tax | Switching from one mutual fund to another — even within the same AMC — is a taxable event. Treated as full redemption + fresh purchase. |
| Grandfathering | For equity fund units bought before 31 January 2018, the cost basis is the higher of the actual purchase price or the NAV on 31 Jan 2018. |
| Debt Pre-2023 | Units purchased in debt funds before 1 April 2023 may have different tax treatment, including a potential LTCG rate of 12.5% if held long-term. |

### 9.2 Charts & Visuals

**Donut Chart — Portfolio Tax Breakdown:**

```
Center shows: ₹16,146 total tax
Segments: [Principal] [Post-Tax Gain] [Tax Paid] [Exit Loads]
```

**Stacked Bar Chart — Per-Fund Contribution:**

```
Fund 1  ████████████████░░░░░░  LTCG ₹3,125
Fund 2  ██████████░░░░░░░░░░░░  STCG ₹3,000
Fund 3  ████░░░░░░░░░░░░░░░░░░  Slab ₹5,400
         ── Tax Paid ──   ── Post-Tax Gain ──
```

**Holding Period Timeline (per fund):**

```
Jan 2024 ────────────────────────── Jul 2026
  |  [== SHORT TERM ==]|[====== LONG TERM ======]
  0                   12m                    current
         ↑ crossed LT threshold  ↑ you sold here
```

**Harvest Savings Funnel:**

```
Realized Gains:         ₹5,00,000
After Set-Off:          ₹3,50,000   (▼ ₹1,50,000 STCL used)
After Exemption:        ₹2,25,000   (▼ ₹1,25,000 equity exempt)
Taxable Base:           ₹2,25,000
Tax @ blended rate:     ₹32,500
After-cess final tax:   ₹33,800
```

### 9.3 Smart Alerts System

The calculator emits context-aware alerts in the results panel:

| Trigger | Alert |
|---------|-------|
| Fund held 10–12 months | ⏳ "Holding 54 more days converts this to LTCG — saves ₹X" |
| LTCL present + all gains are STCG | ⚠️ "Your LTCL cannot offset STCG. Only useful if you have LTCG." |
| Unused LTCG exemption remaining | 💡 "You have ₹X of your ₹1.25L exemption unused. Harvest gains before March 31." |
| Exit load > tax saving | 🚫 "Harvesting this position costs more in exit load (₹X) than you save in tax (₹Y). Skip it." |
| Debt fund switch planned | ⚠️ "Switching this debt fund now triggers ₹X in slab-rate tax. Waiting Y months saves ₹Z." |
| Carry-forward losses available | 💡 "₹X in carry-forward STCL from prior years applied. Verify in Schedule BFLA of ITR-2." |
| Total LTCG from stocks + funds > ₹1.25L | ⚠️ "Stock LTCG of ₹X already uses ₹X of your ₹1.25L exemption. Only ₹Y left for MFs." |
| IDCW received in 30% bracket | 💡 "IDCW taxed at 30%. Consider switching to Growth plan to defer tax." |
| Filing deadline approaching | 📅 "31 July 2026 is the ITR deadline. File on time to carry forward ₹X in losses." |

---

## 10. Data Model

```typescript
// User tax profile
interface TaxProfile {
  taxSlab: 0 | 5 | 10 | 15 | 20 | 30;           // % income tax slab
  stockLtcgThisYear: number;                       // ₹ from direct stocks/ETFs
  carryForwardSTCL: number;                        // from previous ITR filings
  carryForwardLTCL: number;
  surchargeApplicable: boolean;
  surchargeRate: 0 | 10 | 15;                     // %
}

// A single fund entry (lump sum)
interface FundEntry {
  id: string;
  name: string;
  fundType: FundType;                              // enum of all fund categories
  purchaseDate: Date;
  saleDate: Date;
  investedAmount: number;
  redeemedAmount: number;
  idcwReceived: number;
  exitLoad: number;
  // Computed fields (auto-calculated)
  gain: number;
  holdingMonths: number;
  gainType: GainType;
  taxRate: number;
  taxBeforeExemption: number;
  isLongTerm: boolean;
}

// A SIP entry (multiple installments → single redemption)
interface SIPEntry {
  id: string;
  name: string;
  fundType: FundType;
  installments: { date: Date; amount: number; nav: number }[];
  redemptionDate: Date;
  redemptionAmount: number;
  sellNAV: number;
  // Computed: per-installment FIFO breakdown
  fifoTransactions: FIFOTransaction[];
}

// A loss position for harvesting
interface LossPosition {
  id: string;
  name: string;
  unrealizedLoss: number;
  holdingMonths: number;
  type: 'STCL' | 'LTCL';
  exitLoad: number;
  // Computed
  effectiveTaxSaving: number;
  netBenefit: number;
  recommended: boolean;
}

// Global app state
interface AppState {
  taxProfile: TaxProfile;
  funds: (FundEntry | SIPEntry)[];
  lossPositions: LossPosition[];  // for Tab 2
  // Computed tax summary
  summary: TaxSummary;
}
```

---

## 11. Implementation Phases

### Phase 1 — Core Calculator (MVP) ← Start Here

- Tax profile setup (slab, exemption, carry-forward)
- Fund entry with the 12 fund types, STCG/LTCG logic
- Automatic set-off hierarchy engine
- ₹1.25L exemption applied correctly
- Results panel: tax breakdown, post-tax return, effective rate
- All ⓘ tooltips for every field
- Donut chart for portfolio visualization
- Smart alerts: "hold X more days" and "unused exemption" notifications

### Phase 2 — Tax Harvesting Module

- Harvesting Savings sub-tab (realized gains + loss positions → tax saved)
- LTCL vs STCL prioritization engine
- Year-End Planner (full mixed portfolio → optimal sell actions)
- Exit load vs tax saving comparison
- Carry-forward computation and alert
- Per-position "harvest or skip" recommendation

### Phase 3 — SIP Mode

- SIP installment entry (manual + CSV import)
- FIFO engine for partial redemptions
- Per-installment STCG/LTCG breakdown table
- "Wait until X to go fully long-term" alert
- Aggregate SIP tax summary

### Phase 4 — Compare & Plan

- Growth vs IDCW comparison widget
- Fund switching tax impact calculator
- Arbitrage vs Liquid fund optimizer
- Interactive "what if I wait N more months?" slider for any fund

### Phase 5 — ITR Guide & Polish

- Contextual ITR guide (auto-populated from portfolio)
- Schedule CG / 112A pre-filled summary to copy
- CSV and PDF export of full tax report
- Dark/light mode toggle
- Mobile responsive layout
- Share via link (URL-encoded state)

---

## 12. Key Differentiators vs Existing Calculators

| Feature | ctccalculatorindia | stockcalc.in | sum.money | rupeetools.in | **This Calculator** |
|---------|:-----------------:|:------------:|:---------:|:-------------:|:-------------------:|
| Multi-fund portfolio | ❌ | ❌ | ❌ | ❌ | ✅ |
| SIP FIFO mode | ❌ | ❌ | ❌ | ❌ | ✅ |
| All 12 fund types | Partial | 2 types | 2 types | 3 types | ✅ |
| Set-off hierarchy auto | ❌ | ❌ | Partial | Partial | ✅ |
| Stock LTCG sharing exemption | ❌ | ❌ | ❌ | ❌ | ✅ |
| Carry-forward from prior years | ❌ | Partial | ❌ | ❌ | ✅ |
| Exit load vs tax saving check | ❌ | ❌ | ❌ | ❌ | ✅ |
| Growth vs IDCW comparison | ❌ | ❌ | ❌ | ❌ | ✅ |
| Fund switch tax calculator | ❌ | ❌ | ❌ | ❌ | ✅ |
| Arbitrage vs Liquid optimizer | ❌ | ❌ | ❌ | ❌ | ✅ |
| Debt fund (pre/post 2023 split) | ❌ | ❌ | ❌ | ❌ | ✅ |
| ⓘ tooltips on every term | ❌ | Partial | ❌ | ❌ | ✅ |
| ITR pre-fill guide | ❌ | ❌ | ❌ | ❌ | ✅ |
| Smart "wait X days" alerts | ❌ | ❌ | ❌ | ❌ | ✅ |
| Surcharge calculation | ❌ | Partial | ❌ | ❌ | ✅ |

---

## 13. Sample User Flow (End-to-End)

**User: Param, 30% slab, FY 2025-26**

1. Opens the calculator → enters Tax Slab: 30%, Stock LTCG this year: ₹0
2. Adds Fund 1: Mirae Large Cap, Equity, Invested ₹1,00,000 on 2024-06-01, Redeemed ₹1,34,200 on 2026-04-15
   - Calculator instantly shows: LTCG ₹34,200, within ₹1.25L exemption → Tax: **₹0**
   - Alert: "₹90,800 of exemption still unused"
3. Adds Fund 2: HDFC Short Duration (Debt post-Apr 2023), ₹5,00,000 invested Aug 2025, redeemed Jan 2026 at ₹5,26,000
   - Instantly: STCG ₹26,000 at slab rate → Tax: ₹26,000 × 30% + 4% cess = **₹8,112**
4. Adds Fund 3: Gold ETF, ₹2,00,000 invested April 2025, current value ₹2,40,000 (not sold yet — enters as unrealized)
   - Moves to Tab 2 → adds as "loss or gain position"
   - Calculator projects: if sold now, STCG (11 months) → Slab tax ₹12,000. Wait 1 month → LTCG 12.5% → ₹5,000. **Saving: ₹7,000 by waiting 1 month.**
5. Goes to Tab 4, Growth vs IDCW → confirms Growth option saves ₹8,400 on his equity fund vs IDCW at 30% slab
6. Tab 5 tells him: file **ITR-2**, enter ₹34,200 in Schedule 112A, ₹26,000 in other STCG at slab rate
7. Hits "Copy All Tax Figures" → pastes into ITR filing

Total tax identified: ₹8,112 (debt STCG) + ₹0 (equity LTCG under exemption) = ₹8,432 (after cess)  
Tax saved vs naïve calculation: ~₹7,000+ from timing Gold ETF + ₹13,125 from Growth vs IDCW guidance

---

*Implementation Plan authored for blog project at beyondbooks2116.netlify.app*  
*Tax rules accurate as of FY 2025-26 (AY 2026-27). Budget 2024 changes fully incorporated.*  
*Disclaimer: This is an educational tool. Final tax liability should be confirmed with a CA.*