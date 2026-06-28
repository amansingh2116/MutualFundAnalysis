# Advanced Mutual Fund Strategy Backtester — Master Product & Engineering Specification

> Consolidated from your current implementation (Investment Plan Builder UI) + 10 video/transcript sources covering relative-valuation timing, PE-band SIPs, smart/booster SIPs, Monte Carlo allocation optimization, rebalancing engines, lump-sum vs batch deployment, market-regime detection, rolling-return statistics, and research-grade comparison dashboards.

**Purpose of this document:** a single source of truth you can build against. It is organized by *engine/module*, not by source video, because the same idea ("pause SIP when expensive") shows up in five different transcripts in five different costumes — relative valuation, PE bands, macro risk, RSI, drawdown triggers. They are all the same underlying primitive: **a signal feeding a trigger ladder that resizes a cashflow.** The spec below is written so your codebase only needs to build that primitive *once* and reuse it everywhere.

---

## Table of Contents

0. [Design Philosophy](#0-design-philosophy)
1. [Current State — What You've Already Built](#1-current-state)
2. [System Architecture — The Nine Engines](#2-system-architecture)
3. [Module A — Data & Universe Layer](#module-a)
4. [Module B — Strategy & Portfolio Builder](#module-b)
5. [Module C — Cashflow / Investment-Mode Engine](#module-c)
6. [Module D — Signal Engine](#module-d)
7. [Module E — Action & Rule Engine](#module-e)
8. [Module F — Rebalancing Engine](#module-f)
9. [Module G — Cash, Cost, Tax & Realism Engine](#module-g)
10. [Module H — Optimization Engine](#module-h)
11. [Module I — Analytics & Risk Engine](#module-i)
12. [Module J — Statistical Validation Engine](#module-j)
13. [Module K — Comparison & Scenario Engine](#module-k)
14. [Module L — Screener & Fund Discovery](#module-l)
15. [Module M — Visualization & Reporting Layer](#module-m)
16. [Module N — Strategy Management (Save/Load/Version)](#module-n)
17. [Module O — Alerts & Monitoring](#module-o)
18. [Consolidated Input Specification](#18-consolidated-inputs)
19. [Consolidated Output Specification](#19-consolidated-outputs)
20. [End-to-End Working Pipeline](#20-working-pipeline)
21. [Preset Comparison Library (one-click templates)](#21-preset-library)
22. [Engineering Architecture](#22-engineering-architecture)
23. [Roadmap](#23-roadmap)

---

## 0. Design Philosophy

1. **One signal engine, many costumes.** Relative valuation ratio, PE band, RSI, drawdown-from-ATH, market-cap-to-GDP, VIX — these are all just *time series that produce a score*, which a *trigger ladder* maps to an *action*. Build the Signal → Trigger → Action pipeline as a generic, reusable object, not as five separate "strategies."
2. **Cashflow-native, not return-series-native.** Because you support SIP pausing, doubling, redemption, transfers between funds, and step-ups, the simulator must track actual rupee cashflows in and out on actual dates — not just a return series. XIRR, tax lots, and unit-level FIFO accounting all depend on this.
3. **Nothing hardcoded — everything is a band/threshold editor.** PE bands, relative-valuation bands, drawdown bands, vol thresholds — none of these should be hardcoded in your code. Build one generic "Band Editor" UI component and reuse it for every signal type.
4. **Every comparison is A vs B (vs C, D, E…).** The single most-repeated request across every transcript is side-by-side comparison: SIP vs lumpsum, index vs active, rebalance vs no-rebalance, fund vs benchmark. Make multi-strategy comparison the *default* screen, not a special mode bolted onto single-strategy backtesting.
5. **Show the user *why*, not just *what*.** Decision-quality output (which rule helped, which fund hurt, was the timing rule overfit) is what separates a "calculator" from a "research lab." Treat attribution as a first-class output, not an afterthought.
6. **Realism beats elegance.** Tax, exit load, transaction cost, liquidity feasibility, and behavioral execution delay are what make backtests trustworthy. A strategy that wins gross of tax but loses net of tax is the single most common trap in this domain — surface it every time.

---

## 1. Current State — What You've Already Built {#1-current-state}

Based on your screenshots, the live app already has:

| Area | What exists today |
|---|---|
| Fund/index search | Global search bar ("Search funds by name, AMC, ISIN…") + a second "Search mutual funds or indices…" box inside the plan builder |
| Portfolio plan | Add one or more funds as cards (shows scheme name, scheme code, plan type, rule count) |
| SIP rule | Amount (₹), Frequency (Monthly dropdown), Step-up %/yr, Start Date, End Date (blank = ongoing) |
| Other rule types | `+ Lumpsum`, `+ Sell Rule` buttons exist next to `+ SIP` (so the per-fund rule model already supports multiple heterogeneous rules per fund) |
| Simulation control | Global Start Date / End Date for the whole backtest |
| Rebalancing | Mode = Annual (dropdown — presumably also Monthly/Quarterly/etc.), Anchor Month = January (dropdown) |
| Tactical Overlay ("What-If") | Runs the **same base plan 4 more times** with different equity signals; when a signal is "off," SIP cash is redirected to a **debt parking fund** (optional, searchable) instead of the equity leg; if no parking fund is chosen, parked capital earns a **Synthetic Debt Return Rate** (slider, default 7% p.a.); **Strategy 3** uses a **Vol Threshold** slider (default 20%); **Strategy 4** is PE-ratio-based but is currently **disabled — "PE data not yet ingested."** |
| Data sources | AMFI, mfapi.in, captnemo.in, Morningstar — credited in the footer |
| Positioning | "MF Analysis Platform," explicitly **open source on GitHub**, explicit "Not financial advice" disclaimer |
| Onboarding | A 3-step framing on the empty state: **1. Search & Add → 2. Configure Rules → 3. Run & Analyse** (promising CAGR, XIRR, drawdowns, ledger, rebalancing overlays) |

**What this tells us about your architecture already:**
- You have a **per-fund rule model** (a fund can carry multiple rules: SIP + Lumpsum + Sell Rule simultaneously) — this is exactly the right primitive; the rest of this spec mostly *adds more rule types* and *more trigger conditions* to that same model, it doesn't replace it.
- You already have the concept of a **signal-driven multi-run overlay** (the "4 strategies" tactical overlay) — this is precisely the **Signal → Action engine** described in Module D/E below, just currently scoped to 3 working signals + 1 pending (PE). This spec gives you the full generalization of that idea plus the exact spec to finish Strategy 4.
- You already have a **debt-parking / synthetic-return concept** — this maps directly to Module G's cash/idle-capital engine. The spec below generalizes "synthetic debt return when off" into a full **cash-parking framework** (liquid / ultra-short / overnight / synthetic) reusable everywhere money is idle, not just in the tactical overlay.
- You don't yet appear to have (from the screenshots): tax computation, transaction-cost/exit-load modeling, benchmark/index assets as backtestable legs in their own right, Monte Carlo allocation search, rolling-return / statistical-significance views, multi-strategy A/B/C comparison, a transaction ledger export, or a fund screener. These form the bulk of the new modules below.

---

## 2. System Architecture — The Nine Engines {#2-system-architecture}

```
┌─────────────────────────────────────────────────────────────────────┐
│                         A. DATA & UNIVERSE LAYER                     │
│   NAV/TRI history · scheme metadata · indices · PE/macro series      │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────────┐
│                  B. STRATEGY & PORTFOLIO BUILDER                      │
│   funds/indices + weights · strategy mode · constraints              │
└─────┬─────────────┬───────────────┬──────────────┬────────────────────┘
      │              │               │              │
┌─────▼─────┐  ┌─────▼──────┐ ┌──────▼──────┐ ┌─────▼────────┐
│ C. CASHFLOW│  │ D. SIGNAL  │ │ E. ACTION/  │ │ F. REBALANCE │
│   ENGINE   │◄─┤  ENGINE    │►│ RULE ENGINE │►│   ENGINE     │
│ SIP/Lump/  │  │ valuation/ │ │ pause/double│ │ freq/band/   │
│ STP/SWP/   │  │ technical/ │ │ /redeem/    │ │ hybrid/      │
│ batch      │  │ macro/regime│ │ switch/xfer │ │ smart-SIP   │
└─────┬──────┘  └────────────┘ └─────────────┘ └──────┬───────┘
      │                                                 │
┌─────▼─────────────────────────────────────────────────▼──────────────┐
│               G. CASH, COST, TAX & REALISM ENGINE                     │
│   idle-cash parking · STCG/LTCG · exit load · txn cost · slippage     │
└───────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │   SIMULATION CORE         │
                    │ (daily/event-driven loop) │
                    └────────────┬──────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
┌───────▼────────┐   ┌───────────▼──────────┐   ┌──────────▼─────────┐
│ H. OPTIMIZATION │   │ I. ANALYTICS & RISK   │   │ J. STATISTICAL      │
│   ENGINE        │   │   ENGINE              │   │   VALIDATION ENGINE │
│ Monte Carlo /   │   │ CAGR/XIRR/Sharpe/     │   │ rolling-return      │
│ vol targeting   │   │ Sortino/ROMAD/VaR…    │   │ distributions, p-val│
└─────────────────┘   └───────────┬───────────┘   └──────────┬──────────┘
                                   │                          │
                    ┌──────────────▼──────────────────────────▼──────┐
                    │     K. COMPARISON & SCENARIO ENGINE             │
                    │  A vs B vs C · stress tests · what-if · regime  │
                    └──────────────────────┬───────────────────────────┘
                                            │
        ┌────────────────────────────────────┼────────────────────────┐
┌───────▼────────┐               ┌───────────▼──────────┐   ┌──────────▼─────────┐
│ L. SCREENER /   │               │ M. VISUALIZATION &    │   │ N. STRATEGY        │
│ FUND DISCOVERY  │               │    REPORTING LAYER    │   │   MANAGEMENT       │
└─────────────────┘               └───────────────────────┘   │ save/load/version/ │
                                                                │ compare             │
                                                                └─────────┬───────────┘
                                                                          │
                                                                ┌─────────▼───────────┐
                                                                │ O. ALERTS &          │
                                                                │   MONITORING         │
                                                                └───────────────────────┘
```

**Why split it this way:** the Signal Engine (D) and Action/Rule Engine (E) are deliberately separate from the Rebalancing Engine (F) even though "rebalancing" is itself a rule, because rebalancing is *portfolio-level* (drift between N assets back to target weights) while the Signal→Action pipeline is generally *per-asset or per-pair* (one ratio, one fund, one trigger). Keeping them distinct prevents your rule engine from becoming a tangle of special cases.

---

## Module A — Data & Universe Layer {#module-a}

### A1. Asset types the engine must treat as first-class, swappable inputs
- Mutual fund schemes (NSE/BSE, direct & regular, growth & IDCW)
- Benchmark / market indices (Price and **TRI — Total Return Index**, which must be the default wherever available, since price-only indices understate long-term return by excluding reinvested dividends)
- ETFs
- Category proxies (e.g., "Midcap 150" used as a stand-in for the midcap category as a whole)
- Factor indices (momentum, value, low-volatility, quality, and blends of these)
- Debt / liquid / ultra-short / overnight funds (used as the "parking" leg — already partially present in your Tactical Overlay)
- Gold ETFs / commodity proxies
- User-defined "synthetic" series (e.g., a constant-rate proxy for a debt return, which you already support as "Synthetic Debt Return Rate")

### A2. Required data fields per asset
| Field | Notes |
|---|---|
| Scheme name / ISIN / scheme code | Primary key |
| Category & sub-category | Large/Mid/Small/Flexi/Hybrid/Debt/Gold, SEBI cap-tier |
| AMC | |
| Direct vs Regular | Drives expense ratio difference |
| Growth vs IDCW | Drives dividend re-investment handling |
| NAV history (daily) | Core series |
| TRI / benchmark index mapped to this scheme | For benchmark-relative analytics |
| Expense ratio (current + historical if available) | All returns should default to **net-of-expense** |
| Tracking error (for index funds) | Needed to pick "best" index fund per category, and to realistically degrade index returns vs the raw index |
| Exit load schedule | e.g., 1% if redeemed within 365 days |
| Minimum SIP / lumpsum amount | Feasibility checks |
| SIP-allowed flag | Some schemes don't allow SIP |
| Inception date | For survivorship-bias-safe selection (see A5) |
| Fund manager / mandate changes (optional, advanced) | Useful for "has this fund's strategy changed under the hood" flags |
| AUM (current + historical if available) | Used for category fund selection and concentration-risk flags |
| Risk label (SEBI riskometer) | Display only |
| Star rating (Morningstar / Value Research) | Display + screener filter |
| Split / merger / closure events | Must be NAV-adjusted so a scheme that merged into another doesn't show a fake return discontinuity |

### A3. Macro / signal-source data (new — not fund-specific)
| Series | Used by |
|---|---|
| Nifty 50 / Nifty 500 PE ratio (and PB, dividend yield if available) | PE-band engine (Module D) — **this is exactly the data your UI already flags as "not yet ingested" for Strategy 4.** Ingesting monthly/daily Nifty PE (and ideally PE for Midcap150 / Smallcap250) directly unblocks Strategy 4. |
| India Market-cap-to-GDP ratio | Macro risk overlay |
| India VIX | Macro risk overlay, "wait for VIX to cool" rule |
| FII/DII flow data | Event-annotation layer |
| CPI / inflation index | Inflation-adjustment module |
| Risk-free rate proxy (e.g., 91-day T-bill or repo rate) | Sharpe/Sortino numerator |
| Liquid fund / overnight fund average return | Default "cash parking" rate when no specific fund is chosen (generalizes your existing Synthetic Debt Return Rate) |
| Market regime event calendar | 2008 GFC, 2013 taper tantrum, 2018 NBFC crisis, 2020 COVID crash, 2022 rate-hike/Ukraine drawdown, election windows — used for the event-overlay chart |

### A4. Data engineering requirements
- **Common-period auto-alignment.** When two or more assets are selected for a comparison, the engine must automatically detect the overlapping date range across all of them and run the backtest on that common window, clearly displaying the resulting start date (this is explicitly necessary because schemes have different inception dates — index funds in particular often start years after the index itself).
- **Missing-value handling.** Forward-fill NAV on non-trading holidays; flag (don't silently drop) any gap longer than N days.
- **Adjustment for corporate actions.** Splits, merges, and scheme closures must be NAV-adjusted so a backtest doesn't show a fake jump/crash.
- **TRI-first default.** Whenever a price index and its TRI equivalent both exist, TRI should be the default selection, with an explicit toggle to switch to price-return if the user wants it.

### A5. Survivorship-bias controls
A first-class option, not a footnote: **"Construct universe as of [date]"** — i.e., let the user pick funds/AMCs the way they would have looked at the time (e.g., "top funds by AUM as of Jan 2015"), rather than only letting them cherry-pick today's known winners. Practically this means:
- Storing **historical AUM rankings**, not just current AUM, so a "top-10-by-AUM" filter can be applied *as of a past date*.
- Allowing a manually curated "as it stood then" fund list import (since some of this — e.g. "which funds award bodies were hyping in 2015" — isn't a clean numeric filter and is research the user does themselves; just give them an easy way to lock in that list and reuse it).
- A visible warning banner whenever a fund-selection method is return-based and not survivorship-safe (e.g., "you selected funds by trailing 5Y return — this set is subject to survivorship bias").

---

## Module B — Strategy & Portfolio Builder {#module-b}

### B1. Strategy modes (top-level radio choice, drives which of the engines below activate)
| Mode | Behavior |
|---|---|
| **Buy & Hold** | One-time lumpsum / SIP schedule, no rebalancing, no tactical signal |
| **Rebalance** | Periodic and/or band-based rebalancing back to target weights (Module F) |
| **Risk Targeting** | User sets a drawdown/volatility tolerance; engine dynamically resizes equity exposure to stay inside that risk budget |
| **Signal-Driven / Tactical** | One or more Module D signals drive Module E actions (pause/double/redeem/switch) — this is the generalized version of your existing "Tactical Overlay" |
| **Pair / Relative-Value** | Exactly two assets (fund-fund, fund-index, index-index); a relative signal between them drives capital migration from one to the other (long-short style) |
| **Factor Portfolio** | Portfolio built from factor indices (momentum/value/quality/low-vol) instead of, or blended with, market-cap funds |
| **Lump-sum vs Batch Deployment** | A fixed corpus deployed either as one lumpsum or split into N tranches at fixed intervals |

These modes are not mutually exclusive — e.g. a "Rebalance" portfolio can also have a "Signal-Driven" overlay on top (this is effectively what your current Tactical Overlay already does relative to the base plan).

### B2. Portfolio construction inputs
- **Asset list**: any mix of fund/index/ETF/debt/gold entries (multi-asset, not equity-only)
- **Target weights**: must sum to 100%; live validation with a running total shown as the user types (this maps directly onto your existing per-fund-card layout — just add a weight field and a running-sum validator)
- **Per-asset deviation-rule type**: **absolute** deviation (±X percentage points) or **relative** deviation (±X% of the target weight itself) — needed because a 2%-weight asset and a 40%-weight asset shouldn't use the same drift rule
- **Per-asset min/max allocation constraints** (e.g., "never let small-cap exceed 25% of the equity sleeve")
- **Minimum holding period** per asset (to respect exit loads / avoid churning)
- **Direct vs Regular** and **Growth vs IDCW** as selectable per fund, not assumed

### B3. Constraints layer
- Max allocation per single fund / per category / per AMC (concentration limits)
- Exit-load-aware switching (engine should warn or auto-delay a sell/switch if it would trigger an avoidable exit load)
- Tax-regime assumptions (equity vs debt vs hybrid taxation — see Module G)
- SIP-allowed flag respected (block SIP rule creation on a scheme that doesn't support it)

---

## Module C — Cashflow / Investment-Mode Engine {#module-c}

This is the generalization of your existing **+ SIP / + Lumpsum / + Sell Rule** buttons. Each fund-rule should be one of the following types, fully composable (a fund can carry several simultaneously, as your UI already allows):

### C1. Lumpsum
- One-time investment on a specific date, specific amount.

### C2. Standard SIP
- Amount, frequency (**daily / weekly / monthly** — currently your UI only exposes Monthly; add Daily/Weekly), start date, end date (blank = ongoing — already supported), day-of-month/week selector.
- Note for the team: the "DIY smart SIP" transcript explicitly tested whether the *date-of-month* chosen for the SIP changes returns and found it does **not** matter materially — useful as a built-in tooltip/FAQ entry so users don't over-optimize a non-factor.

### C3. Step-Up SIP ("SIP Plus")
- **Absolute step-up**: add a fixed ₹ amount every period (e.g. +₹2,000 every 12 months)
- **Percentage step-up**: increase by X% every period (e.g. +10% every 12 months) — *this is distinct from, and an addition to, your existing flat "Step-up %/yr" field; expose both absolute and percentage modes explicitly*
- Step-up frequency independent of contribution frequency (e.g., contribute monthly, step up annually)

### C4. Smart / Booster / Value SIP
- A dynamic SIP whose **contribution multiplier** (e.g., 10%–1000% of the base amount) is driven by a valuation signal from Module D, rather than a fixed amount.
- **Source–Target Fund model**: cash is first parked in a *source* fund (typically a short-duration debt fund) and only transferred into the *target* equity/hybrid fund when the valuation model says so — model this explicitly as two ledgers (source, target) with a transfer rule between them, since several real-world products (booster SIP, smart SIP variants) work exactly this way.
- Tiered multiplier table (user-editable), e.g.:

| Valuation zone | SIP multiplier |
|---|---|
| Super cheap | 1000% |
| Cheap | 200% |
| Neutral | 100% |
| Expensive | 50% |
| Super expensive | 10% |

### C5. Conditional / Triggered SIP
- "Buy ₹X extra whenever [index] is down Y% on the day" (intraday/daily trigger)
- "Buy ₹X extra whenever **my own portfolio** is down Y% from its peak" (portfolio-relative trigger, distinct from an index-relative trigger)
- One-time vs repeatable trigger flag

### C6. STP (Systematic Transfer Plan)
- Scheduled transfer of a fixed amount from one fund to another at a fixed frequency (distinct from the *conditional* source→target transfer in C4 — this is calendar-based, not signal-based)

### C7. SWP (Systematic Withdrawal Plan) / Sell Rule
- Generalize your existing "+ Sell Rule" into: fixed-amount withdrawal, fixed-unit withdrawal, or %-of-corpus withdrawal, on a recurring schedule or as a one-time redemption
- **Withdrawal sustainability check**: flag if the SWP rate is likely to deplete the corpus before the end date, and show a "years until depletion at this rate" estimate

### C8. Lump-sum vs Batch (Staggered) Deployment
- A dedicated mode (not just a rule) for the classic "I have ₹1,00,000 right now — all at once, or split it?" question:
  - **Batch count**: N tranches (user-set, or auto-optimized — see Module H)
  - **Interval**: gap between tranches (default monthly)
  - **Idle-capital treatment while waiting**: 0% / liquid-fund rate / custom rate (ties into Module G's cash-parking framework)
  - **Batch-size optimizer**: sweep N from e.g. 2 to 12 tranches and report which count historically gave the best hit-rate / risk-adjusted return (Module H)

### C9. Frequency flexibility (applies across C2–C9)
Daily, weekly, monthly, and custom-interval contribution/withdrawal cycles should all be supported by the same underlying scheduler — don't special-case "monthly" in the simulation core.

---

## Module D — Signal Engine {#module-d}

**This is the single most important new module.** Every "tactical" idea across all ten sources reduces to the same shape: *take a time series, normalize it into a score, and check the score against bands.* Build this once, generically, and every "strategy" below becomes a configuration, not new code.

### D1. Generic signal object
```
Signal {
  id, label
  source_type: RATIO | ABSOLUTE_LEVEL | TECHNICAL | MACRO | COMPOSITE
  inputs: [asset_or_series_refs]
  transform: RAW | RATIO_A_OVER_B | PERCENTILE | Z_SCORE | ROLLING_RETURN_SPREAD | DRAWDOWN_FROM_ATH
  lookback_window (if rolling/percentile/z-score based)
  rebase_date / rebase_value (for ratio series, e.g. rebase A/B to 1.0 at a chosen start date)
  evaluation_frequency: DAILY | WEEKLY | MONTHLY
}
```

### D2. Signal types to support

| Signal type | Definition | Source |
|---|---|---|
| **Relative valuation ratio** | `Index_A / Index_B`, rebased to 1.0 at a chosen start date. Bands like 0.9–1.1 = neutral. | Small-cap/large-cap relative valuation videos |
| **Drawdown-from-ATH** | `(current value / rolling all-time-high) − 1`, evaluated daily | Buy-the-dip transcripts |
| **PE ratio band** | Nifty 50 (or category) trailing/forward PE vs user-defined bands | PE-band SIP transcripts — **this is your blocked Strategy 4; spec is in D4 below** |
| **Moving-average trend filter** | Price vs 200-DMA; "uptrend" defined as price > 200-DMA | Buy-the-dip + trend combo |
| **RSI** | Standard 14-period RSI; oversold <30, overbought >70; optional divergence detection | Buy-the-dip + momentum combo |
| **Market-cap-to-GDP ratio** | India-specific; <60% aggressive, >90% cautious (user-editable thresholds) | Macro risk overlay |
| **Market breadth** | Advancing vs declining stock counts/ratio | Macro risk overlay |
| **VIX level** | India VIX; high = wait, falling = re-enter | Macro risk overlay |
| **Parabolic-rally detector** | % gain over a short trailing window (e.g., +30% in 4 months) flags an overheated market | Macro risk overlay |
| **Google Trends / retail-sentiment proxy** | Optional, lower priority; search-interest spike as an overheating proxy | Macro risk overlay |
| **F&O turnover** | Rising derivatives turnover as a speculation proxy | Macro risk overlay |
| **Portfolio-relative drawdown** | The user's own constructed portfolio's drawdown from its own peak (distinct from an index-level signal) | Conditional SIP transcripts |
| **Volatility threshold** | Rolling N-day realized volatility crossing a threshold | *Already implemented as your Strategy 3 "Vol Threshold" slider — generalize it into this framework* |
| **Composite / blended score** | Weighted combination of any of the above (e.g., 50% PE-band score + 50% drawdown score) | Implied by several transcripts that say real "smart SIP" products blend signals |

### D3. Band / trigger-ladder editor (generic, reusable UI)
Every signal above is consumed the same way: a list of (threshold, comparison operator, action, magnitude) rows that the user edits directly — no hardcoded bands anywhere in the codebase.

| Field | Example |
|---|---|
| Threshold | 1.10 |
| Direction | `signal crosses above` / `signal crosses below` / `signal is between` |
| Action | Pause / Reduce / Continue / Increase / Redeem / Switch |
| Magnitude | ₹10,000, or 150% of base SIP, or 100% of holding |
| Repeat | One-time per crossing vs every period while condition holds |

**Default band presets to ship** (purely as starting templates the user can edit — not hardcoded logic):
- *Relative valuation (Small-cap/Large-cap style):* neutral 0.9–1.1; sell ladder at 1.10/1.15/1.20 (₹10k/₹20k/₹30k); buy ladder at 0.90/0.85/0.80 (₹10k/₹20k/₹30k)
- *Drawdown-from-ATH:* tiers at −5% / −10% / −15% / −25%, each with an escalating deployment amount

### D4. PE-band engine — exact spec to unblock your Strategy 4
Since your app already flags this as pending only on data, here is the full spec to build once Nifty PE is ingested:
- **Inputs:** Nifty 50 (or chosen index) trailing PE series, monthly close; a **5-band table**, user-editable, defaulting to:

| Band | PE range | Default action |
|---|---|---|
| Super cheap | < 14 | Invest 3× base SIP |
| Cheap | 14 – 18 | Invest 1.5× base SIP |
| Neutral | 18 – 24 | Invest 1× base SIP (no action) |
| Expensive | 24 – 28 | Invest 0.5× base SIP, or pause |
| Super expensive | > 28 | Redeem a fixed amount, or pause entirely |

- **Evaluation frequency:** monthly, using the previous month's closing PE (matches how the source transcript describes doing this manually).
- **Output:** same as every other signal-driven strategy (Module I metrics) plus a dedicated **"PE band timeline"** chart showing which band was active on which date, overlaid on the equity curve.

### D5. Market-regime classifier
A standalone classifier (used by Module K's regime-aware comparisons and Module C8's batch-deployment analysis):

| Regime | Default definition (user-editable) |
|---|---|
| Bull | Index up >20% over a trailing window of 2+ months |
| Bear | Index down >20% over a trailing window of 2+ months |
| Sideways | Index moves within roughly ±5–10% with no sustained trend |

Output: a regime label attached to every date in the backtest window, used to (a) shade charts, (b) compute regime-conditional win-rates, and (c) drive the recommendation/decision-guidance layer in Module K.

---

## Module E — Action & Rule Engine {#module-e}

Consumes a Signal-Engine event and executes a concrete portfolio action.

### E1. Action types
| Action | Effect |
|---|---|
| **Pause SIP** | Skip the next N scheduled contributions (or contributions while the condition holds) |
| **Resume SIP** | Re-activate a paused SIP |
| **Increase SIP (multiplier)** | Scale the next contribution(s) by a factor (e.g., 200%) |
| **Decrease SIP (multiplier)** | Scale down (e.g., 50%) without fully pausing |
| **One-time extra buy** | Inject a lumpsum top-up on the trigger date |
| **Redeem fixed amount** | Sell ₹X worth of units |
| **Redeem fixed units** | Sell X units |
| **Redeem % of holding** | Sell X% of current value in that asset |
| **Switch / transfer A → B** | Sell in asset A, buy in asset B on (ideally) the same trade date — this is the "long-short style" capital migration from the relative-valuation transcripts |
| **Source→Target transfer** | Move parked cash from the source (debt) ledger into the target (equity) ledger — the Smart-SIP primitive from C4 |

### E2. Execution realism controls (apply to every action above)
- **Feasibility / liquidity check:** user-defined max ₹ available per trigger event; if a trigger calls for more than is available, either skip, partially execute, or borrow against a defined cash buffer (user choice).
- **Behavioral delay simulation:** optional N-day execution lag after a signal fires, to model real-world hesitation; optional "missed trigger" probability (e.g., 10% chance a given trigger is simply not acted on, to stress-test how much of the edge survives imperfect execution).
- **Exit-load-aware sell:** if a sell/switch would trigger exit load and the holding is within a configurable number of days of being load-free, optionally auto-delay the sell to the load-free date (toggleable; off by default since it changes the let backtest fidelity to the literal rule).
- **Transaction cost:** flat ₹ or bps cost per switch/redemption, applied to every E1 action that touches the market (not applicable to pause/resume).

### E3. Action audit log requirement
Every single action the engine takes — including SIP installments, step-ups, rebalances, and tactical triggers — must be recorded with: date, fund, action type, units, NAV, ₹ amount, triggering signal value (if applicable), and resulting portfolio weight. This feeds Module M's transaction ledger.

---

## Module F — Rebalancing Engine {#module-f}

Generalizes your existing "Mode: Annual / Anchor Month: January" control into the full rebalancing framework described across the platform-demo transcripts.

### F1. Rebalancing trigger types
| Type | Definition |
|---|---|
| **Frequency-based** | Rebalance on a fixed calendar cadence: Monthly / Quarterly / Half-yearly / Annual / Custom-N-months, anchored to a chosen month (you already have Annual + Anchor Month — extend the dropdown to the other cadences) |
| **Band-based** | Rebalance only when any asset's weight drifts beyond its allowed deviation (absolute or relative — see B2) |
| **Hybrid** | Check on the chosen frequency, but only actually rebalance if a band has been breached at that check — this is the "best of both" mode and should probably become the recommended default |

### F2. Rebalancing mechanics
- **Full rebalance:** sell every overweight asset and buy every underweight asset back to exact target weights.
- **Smart SIP rebalancing:** instead of selling anything, route the *next incoming SIP cash* preferentially into underweight assets first; only fall back to selling overweight assets if the SIP cash alone cannot close the gap within a configurable number of periods. This reduces transaction costs and capital-gains tax versus a full sell-and-buy rebalance, and should be offered as a toggle on every Rebalance-mode portfolio.
- **Partial rebalance:** rebalance only X% of the way back to target (a softer alternative to full rebalance, useful for tax-sensitive users).

### F3. Rebalancing impact reporting (ties into Module I)
For every backtest run in Rebalance mode, always show, as a standard pair of numbers:
- **Rebalanced portfolio** final value / CAGR / max drawdown / volatility
- **Same portfolio, no rebalancing** (buy-and-hold drift) final value / CAGR / max drawdown / volatility
…so the user can see in one glance whether rebalancing actually helped, by how much, and at what transaction/tax cost. This directly answers the "did rebalancing improve results?" decision-quality question.

### F4. Risk-Targeting mode (advanced rebalancing variant)
- User sets a **maximum acceptable drawdown** (e.g., "never let the portfolio fall more than 15% from its peak").
- Engine dynamically reduces equity weight (shifting into the debt/parking leg) as realized volatility or drawdown approaches the budget, and restores equity weight as conditions normalize.
- Should be reportable against a static-allocation benchmark of the same nominal equity/debt split, to show whether dynamic risk targeting actually reduced drawdown without giving up too much return.

### F5. Future / advanced allocation rules (flagged explicitly as roadmap, not MVP)
- **Inverse-volatility weighting**: weight each asset inversely to its trailing volatility.
- **Volatility targeting**: size the whole equity sleeve to hit a target portfolio volatility (e.g., 12% p.a.), scaling up/down as realized vol changes.
- **Risk-parity / risk-contribution rebalancing**: rebalance so each asset contributes equally to total portfolio risk, not equal capital weight.

---

## Module G — Cash, Cost, Tax & Realism Engine {#module-g}

### G1. Idle-cash / cash-parking framework (generalizes your existing Debt Parking Fund + Synthetic Debt Return Rate)
Any time capital is not deployed in the "main" asset — waiting for a SIP trigger, sitting between batch tranches, parked in a Smart-SIP source fund, or held during a paused SIP — it must earn a return, not sit at 0% by default, because the cash-drag effect is one of the largest, most counter-intuitive results across the sources (a "dip investor" who waits for corrections frequently *under*-performs a boring SIP investor purely because of cash drag, even when their market-timing calls are individually correct).

| Parking option | Behavior |
|---|---|
| **0% (cash)** | No return on idle capital — useful as the "worst case" comparison |
| **Specific debt/liquid/overnight fund** | Use the actual NAV history of a chosen fund (already supported in your UI) |
| **Synthetic rate** | A flat user-set annual rate (already supported — generalize so it's available everywhere idle cash exists, not only in the Tactical Overlay) |

### G2. Transaction costs & slippage
- Flat-fee or bps cost per buy/sell/switch (configurable, default 0)
- Optional slippage assumption for large rupee amounts deployed at PE/valuation triggers (models the real-world friction of moving large sums quickly)

### G3. Exit load
- Per-scheme exit-load schedule (e.g., 1% if redeemed <365 days) applied automatically to every sell/switch/SWP event that touches a unit younger than the load window
- "Exit-load-avoided" counter shown in results if the auto-delay option (E2) was used

### G4. Tax engine
This is one of the biggest gaps versus most retail backtesters and should be a flagship feature, not an afterthought.

- **Lot-level FIFO unit tracking** is required (not just a portfolio-level return series) because STCG/LTCG depends on *which specific units* are sold and how long *those specific units* were held.
- **Equity taxation** (current Indian rules as the default assumption, clearly labeled as editable since tax law changes): STCG for units held < 12 months at the prevailing STCG rate; LTCG for units held ≥ 12 months at the prevailing LTCG rate, with an annual exemption threshold.
- **Debt/hybrid taxation**: different holding-period and rate rules from equity — model as a separate, editable tax-rule object per asset class so the engine doesn't hardcode equity-only tax logic.
- **Outputs:**
  - Total realized gains (period-wise)
  - Total tax paid (STCG component + LTCG component, shown separately)
  - Post-tax final corpus
  - Post-tax XIRR / CAGR, shown **side-by-side** with pre-tax XIRR/CAGR every time, because the gap between the two is itself the headline insight for tactical/high-turnover strategies
  - "Tax drag" — the percentage-point difference between pre-tax and post-tax CAGR, attributable specifically to switching/rebalancing/redemption frequency

### G5. Inflation adjustment
- CPI series ingestion (Module A3)
- Toggle on every results screen: **Nominal** vs **Real (inflation-adjusted)** — recompute final corpus, CAGR, and XIRR in real terms
- Inflation-adjusted XIRR is the metric to headline when comparing strategies meant to fund a long-horizon goal (retirement, child's education, etc.)

### G6. Liquidity / feasibility layer
- A user-set ceiling on how much *extra* capital can realistically be deployed at any single trigger (protects against a backtest implying you'd have needed ₹30,000 of spare cash on a specific date you didn't actually have)
- Partial-execution mode: if the trigger calls for more than the ceiling, deploy only up to the ceiling and log the shortfall

### G7. Behavioral realism (cross-reference Module E2)
- Missed-trigger probability
- Execution-delay distribution (fixed N days, or a random delay within a range)
- "Perfect execution vs realistic execution" toggle so every tactical strategy can be shown both ways — this should be a standard comparison pair, the same way Rebalance vs No-Rebalance is in Module F3.

---

## Module H — Optimization Engine {#module-h}

### H1. Monte Carlo allocation optimizer
- **Inputs:** the asset list from Module B, a number of random weight-vector draws to try (user-configurable, e.g. 1,000), and an objective function (see H2).
- **Mechanics:** for each draw, generate a random weight vector that sums to 100% (respecting any per-asset min/max constraints from B2–B3), run the full backtest for that vector, score it on the objective function, and keep the running best.
- **Outputs:**
  - Best weight vector found, and its score
  - Full distribution of simulated outcomes (scatter or histogram of objective-function values across all draws) — *not just the winner* — so the user can see how sensitive the result is to allocation choice (a tight cluster of outcomes means allocation barely matters; a wide spread means it matters a lot)
  - Efficient-frontier-style scatter plot: risk (volatility or max drawdown) on one axis, return (CAGR/XIRR) on the other, every simulated portfolio plotted as a point, the chosen objective's winner highlighted
  - Explicit caveat banner: "This is the best *historical* allocation for this exact period — re-running with a different number of simulations, or a different time window, will likely produce a different 'ideal' weight. Treat this as a sensitivity exploration, not a forecast."

### H2. Objective function choices
| Objective | Formula basis |
|---|---|
| Maximize ROMAD | CAGR (or XIRR) ÷ \|Max Drawdown\| |
| Maximize raw return | CAGR or XIRR |
| Minimize max drawdown | \|Max Drawdown\| |
| Minimize volatility | Annualized standard deviation of returns |
| Maximize Sharpe ratio | (Return − risk-free rate) ÷ volatility |
| Maximize Sortino ratio | (Return − risk-free rate) ÷ downside deviation |
| Composite / weighted score | User-defined weighted blend of any of the above (e.g., 60% ROMAD + 40% volatility-minimization) |

### H3. Batch-size optimizer (Lump-sum vs Batch deployment, Module C8)
- Sweep tranche count N over a user-set range (e.g., 2–12)
- For each N, compute the historical hit-rate (% of historical entry dates where batching beat lumpsum) and the average outperformance magnitude, both overall and **regime-conditional** (bull/bear/sideways, from Module D5)
- Report the N that maximizes the chosen objective, plus the full sweep table/chart so the user sees how sensitive the "ideal" batch count is

### H4. Future: volatility targeting / inverse-vol allocator
Flagged as a roadmap item (see Module F5) — an optimizer mode that doesn't search random weights but instead computes weights algebraically from trailing volatility (inverse-vol weighting) or solves for a target portfolio volatility.

---

## Module I — Analytics & Risk Engine {#module-i}

This is the metrics catalog. Every metric below should be computable for **any** backtest run (single strategy, or each leg of an A/B/C/D comparison) and should default to **net-of-expense, pre-tax** unless the user has switched on the post-tax or inflation-adjusted toggle (Modules G4/G5).

### I1. Performance metrics
| Metric | Definition |
|---|---|
| **Absolute return** | (Final value − Total invested) ÷ Total invested |
| **CAGR** | `(Final value / Initial value)^(1/years) − 1` — for lumpsum/static-corpus comparisons |
| **XIRR** | Internal rate of return over irregular cashflow dates (SIPs, top-ups, redemptions) — the correct metric whenever cashflows aren't a single lumpsum, computed via Newton-Raphson or bisection on the NPV-zero condition |
| **Rolling returns** | Annualized return for every possible N-year holding period in the data (not just start-to-end); reported across multiple windows: 1Y, 3Y, 5Y, 7Y, 10Y |
| **Calendar-year returns** | Return for each Jan–Dec calendar year |
| **Yearly SIP return curve** | XIRR computed progressively at each anniversary of an ongoing SIP, showing how the "as of today" XIRR evolved over the life of the investment |

### I2. Risk metrics
| Metric | Definition |
|---|---|
| **Max drawdown** | Largest peak-to-trough decline in portfolio value over the period |
| **Current drawdown** | Decline from the most recent peak, as of the last date in the backtest |
| **Drawdown duration / Max-drawdown days** | Number of days from peak to trough for the worst drawdown |
| **Recovery time** | Number of days from trough back to the prior peak (the "how long can you hold your breath" metric) |
| **Volatility** | Annualized standard deviation of periodic (daily/monthly) returns |
| **Downside deviation** | Standard deviation computed only over negative-return periods (used in Sortino) |
| **Worst month / worst quarter** | The single worst rolling 1-month / 1-quarter return in the series |
| **VaR (Value at Risk)** | The Nth percentile (e.g., 5th) of the daily/monthly return distribution — "95% confident daily return is no worse than X%" |
| **CVaR / Expected Shortfall** | Average of all returns *worse than* the VaR threshold — captures tail severity beyond VaR |

### I3. Risk-adjusted ratios
| Ratio | Formula |
|---|---|
| **Sharpe ratio** | (Return − risk-free rate) ÷ volatility |
| **Sortino ratio** | (Return − risk-free rate) ÷ downside deviation |
| **Calmar ratio** | CAGR ÷ \|Max Drawdown\| (typically computed on a trailing 3Y window) |
| **ROMAD** | Return (CAGR or XIRR) ÷ \|Max Drawdown\| — functionally similar to Calmar but computed over the full backtest window rather than a fixed trailing window; expose both since different sources use each |
| **Information ratio** | Active return (portfolio − benchmark) ÷ tracking error |

### I4. Consistency metrics
- % of positive months / negative months
- Average gain in an up-month vs average loss in a down-month
- Rolling 1Y / 3Y / 5Y return distribution (mean, median, quartiles, min, max — feeds Module J's box plots)
- Upside capture ratio (portfolio return ÷ benchmark return, computed only over benchmark-positive periods)
- Downside capture ratio (same, computed only over benchmark-negative periods) — a genuinely defensive strategy should show downside capture meaningfully below 100% without giving up too much upside capture

### I5. Benchmark-relative metrics
- Active return (portfolio return − benchmark return)
- Tracking error (standard deviation of the active-return series)
- Information ratio (I3)
- Excess return over benchmark, both nominal and annualized

### I6. Allocation metrics
- Actual vs target weight per asset, on every date
- Drift series per asset (actual − target)
- Concentration metrics (e.g., Herfindahl-style index across holdings, or simply "largest single position %")
- Rebalancing impact (Module F3)

### I7. Cashflow metrics
- SIP-timing effect (does the *specific date* in the month materially change outcomes — generally no, per I1's date-of-month note, but compute it so the user can verify for their own data)
- Lumpsum-timing effect (entry-date sensitivity — ties into Module J's rolling-return distribution and Module K's "was I entering at a peak?" insight)
- Total contribution growth over time (a simple cumulative-invested-capital line, useful as the denominator context behind every return number)
- Withdrawal sustainability (Module C7)

### I8. Strategy attribution ("decision-quality" output)
The output users most often don't get from a basic calculator, and the most valuable differentiator to ship well:
- **Per-fund contribution to total return** (how much of the final corpus's gain came from each holding)
- **Per-rule contribution** (isolate the return delta attributable to *just* the rebalancing rule, *just* the tactical overlay, *just* the step-up, by running counterfactual variants automatically — e.g. same portfolio with the rule turned off — and differencing the result)
- **Which fund hurt the portfolio most** (largest negative contributor)
- **Was the rebalancing/tactical rule worth its complexity?** — compare the rule-on result against the rule-off result, net of any extra transaction cost/tax incurred by the rule, and surface a plain-language verdict (e.g., "this rule added +0.4% CAGR but cost an extra 0.6% in tax/transaction drag — net negative")
- **Overfitting flag** — if a rule's edge is concentrated in a narrow date range or a single market cycle rather than appearing consistently across the regime-conditional breakdown (Module D5/K), flag it as possibly overfit rather than presenting it as a robust edge.

---

## Module J — Statistical Validation Engine {#module-j}

This is what separates "Strategy A looks better in this one backtest" from "Strategy A is *reliably* better." Build this as a dedicated module that activates automatically whenever two or more strategies are compared.

### J1. Rolling-return distribution analysis
- Compute the *full distribution* of N-year rolling returns (not just the single start-to-end CAGR) for each strategy, across multiple windows (1Y/3Y/5Y/7Y/10Y).
- Visualize as **box plots**: min, lower fence, Q1 (25th percentile), median, mean, Q3 (75th percentile), upper fence, max/outliers — one box per strategy, one panel per window length, so the user can see at a glance whether Strategy A's *typical* outcome is better, not just its lucky/unlucky endpoints.
- Smaller box = more reliable/consistent outcome regardless of entry date; wider box = highly entry-date-dependent, which is itself an important risk disclosure.

### J2. Statistical significance testing
- For any A-vs-B comparison, run a significance test (e.g., a t-test, or a non-parametric alternative if the rolling-return distributions are non-normal) on the rolling-return samples of A vs B.
- Report: **p-value**, **t-statistic** (or equivalent test statistic), and an **effect size** (e.g., Cohen's d) classified in plain language as negligible / small / medium / large.
- Plain-language verdict line, e.g.: *"Over 5-year rolling windows, Strategy A's outperformance is statistically significant (p < 0.05) but the effect size is small — don't expect this edge to feel large in any single 5-year period you personally live through."*
- This must be computed **per window length** — the sources explicitly show that a real strategy can be significant at 3Y, borderline at 5Y, and negligible at 7Y; don't collapse this into one number.

### J3. Correlation / diversification check
- **1-year rolling correlation** between any two compared strategies (or strategy vs benchmark).
- Plain-language read-out: correlation persistently near 1.0 → "these are not meaningfully different bets, just the same bet with extra steps"; correlation that varies a lot or runs low → genuine diversification.

### J4. Cycle-coverage requirement
- Before presenting any of the above, the engine should check how many distinct bull/bear/sideways regimes (Module D5) the backtest window actually contains, and surface a coverage note (e.g., "This window includes 1 bear market and 2 bull markets — interpret tail-risk claims with that in mind") rather than silently letting a 3-year, all-bull-market backtest imply a robust risk profile.

### J5. Entry-timing context ("was I buying at a peak?")
- For the chosen start date(s) of a lumpsum or batch-deployment strategy, show where that date falls on the underlying asset's own drawdown/rolling-return history (e.g., "this start date was 3% below the then all-time-high, in the cheaper third of historical valuation observations") — directly useful for the lumpsum-vs-staggered decision in Module C8/H3.

---

## Module K — Comparison & Scenario Engine {#module-k}

### K1. Multi-strategy comparison workspace (the primary screen)
- Build **Strategy A, Strategy B, (C, D, …)** as parallel, independently configured portfolios (each with its own assets, weights, modes, rules) and run them over the same — auto-aligned — common period.
- This should be the **default landing workflow**, not a special mode: even a single-strategy backtest can be thought of as "Strategy A vs a benchmark," so the comparison UI and the single-run UI should share the same components.
- Strategy save/reload (Module N) should plug directly into this screen, so users can pull two previously-saved strategies in and compare them on demand.

### K2. Standard comparison sets to ship as one-click presets
(See the full preset library in Section 21 — this is the conceptual list; Section 21 is the literal one-click menu.)
- Portfolio vs benchmark index
- Direct vs Regular plan
- Growth vs IDCW
- SIP vs Lumpsum
- SIP vs Staggered batch deployment
- No rebalance vs Frequency rebalance vs Band rebalance vs Hybrid rebalance
- Equal-weight vs score/rank-weighted portfolio
- Static allocation vs Monte-Carlo-optimized allocation
- Active fund(s) vs Index fund(s), same category, survivorship-bias-safe selection
- Single fund vs multi-fund diversified portfolio
- Rule-on vs Rule-off (isolates the tactical overlay's true value, per Module I8)
- Perfect execution vs Realistic (delayed/missed-trigger) execution

### K3. Scenario / stress-test library
Run the *same* strategy through curated historical sub-windows to test robustness:
- 2008 Global Financial Crisis
- 2020 COVID crash & recovery
- 2018 NBFC/IL&FS crisis (mid/small-cap specific)
- 2022 rate-hike / Russia-Ukraine drawdown
- A user-defined "prolonged sideways" window (engine can auto-detect candidate windows using Module D5's regime classifier)
- A user-defined high-inflation window (using the CPI series from A3)
- A user-picked custom date range

### K4. What-if analysis
- "What if I had started investing N years earlier/later?" — shift the whole strategy's start date and re-run
- "What if my SIP stepped up by X% every year?" — toggle Module C3 on/off on an otherwise identical strategy and diff the result
- "What if I had skipped my worst N months?" / "What if I had skipped my best N months?" — a classic, eye-opening pair that quantifies how much of total return is concentrated in a few extreme days/months
- "What if I only rebalanced when drift exceeded X%?" — sweep the band threshold and show sensitivity

### K5. Decision-guidance / recommendation layer
A rules-based (not AI-based, at least initially) layer that turns the regime-conditional results from Module D5/J4 into plain-language guidance, e.g.:
> "In bear-market windows, staggered deployment beat lump-sum 76% of the time in this dataset. In bull-market windows, lump-sum won 80% of the time. The current regime is classified as: **[Bull / Bear / Sideways]**."

Always paired with the standard disclaimer that this is a descriptive read of historical data, not investment advice or a forecast.

---

## Module L — Screener & Fund Discovery {#module-l}

A pre-backtest filtering layer so users can build a sensible universe before they ever open the Strategy Builder.

### L1. Filters
- Category / sub-category
- AUM (current, and **as-of-date** for survivorship-safety, per A5)
- Expense ratio (range)
- Fund age / inception date
- Direct-only toggle
- Growth-only toggle
- Star rating (Morningstar / Value Research)
- Tracking error (index funds)
- Exit load schedule
- Rolling-return consistency (e.g., "show only funds whose 3Y rolling return rarely fell below category average")
- Downside-capture ratio
- Benchmark-relative active return

### L2. Screener UX
- Search-as-you-type by name/AMC/ISIN (already present)
- Multi-select with chips for selected schemes, a running count, and Select All / Clear All (explicitly requested pattern from the platform-demo transcripts)
- A direct **"Add selected to Strategy Builder"** action that hands the chosen set straight into Module B, so screening and building are one continuous flow rather than two disconnected screens.

---

## Module M — Visualization & Reporting Layer {#module-m}

### M1. Core charts (every backtest run, single or comparison)
| Chart | Notes |
|---|---|
| **Equity / NAV curve** | Overlay every compared strategy + benchmark on one chart |
| **Drawdown / underwater chart** | Mirrors the equity curve; overlay all compared strategies |
| **Daily/periodic returns** | Per-strategy time series, for volatility/tail inspection |
| **Annual returns bar chart** | One bar per calendar year, per strategy |
| **Monthly return histogram** | Distribution of monthly returns |
| **Monthly return heatmap** | Year × Month grid, color-coded by return — a very high-value, frequently-requested visualization across sources |
| **Allocation drift chart** | Actual vs target weight per asset over time |
| **SIP cashflow timeline** | Bars for contributions/withdrawals over time |
| **Relative-signal / PE-band / regime overlay chart** | The driving signal plotted alongside the equity curve, with band zones shaded and trigger events marked |
| **Rolling correlation chart** | 1-year rolling correlation between compared strategies |
| **Rolling Sharpe / rolling volatility charts** | 1-year rolling, per strategy |
| **Rolling-return box plots** | Per Module J1, faceted by window length (1Y/3Y/5Y/7Y) |
| **Monte Carlo scatter / efficient-frontier plot** | Per Module H1 |
| **Event-annotation overlay** | Marks 2008/2020/etc. on any time-series chart (toggleable layer) |

### M2. Chart interaction requirements
Zoom, pan, autoscale-reset, and full-screen-per-chart should be standard on every time-series chart — explicitly called out as valuable in the platform-demo transcripts for inspecting specific crisis windows.

### M3. Tabular outputs
- **Summary metrics table** — every Module I metric, one column per compared strategy, for direct side-by-side reading
- **Risk metrics table** — drawdown, drawdown days, recovery days, volatility, Sharpe, Sortino, VaR, ROMAD — one row per strategy
- **Transaction / audit ledger** — every action from Module E3: date, fund, type (SIP/lumpsum/sell/switch/rebalance), units, NAV, ₹ amount, triggering signal value, resulting weight; filterable and exportable (CSV/Excel)
- **Asset-class / per-fund contribution table** — return, Sharpe, drawdown, and XIRR contribution broken out by holding (Module I8)
- **Statistical significance table** — p-value, effect size, per window length, per A-vs-B pair (Module J2)

### M4. The "five questions" results framing
Organize the results experience around the five questions every user actually has, rather than dumping every metric on one screen at once (each can be a tab or a scroll-section, but the *order and grouping* matters for comprehension):
1. **Did it work?** → final value, return, benchmark comparison
2. **How safe was it?** → drawdown, volatility, recovery time
3. **How consistent was it?** → rolling returns, monthly heatmap, calendar-year table
4. **What changed the result?** → rebalancing impact, fund/rule attribution
5. **What should I trust?** → statistical significance, regime coverage, scenario robustness

### M5. Report export
- Downloadable PDF/HTML summary report bundling M1–M4 for a given run or comparison, suitable for sharing or archiving — useful both for your own book-writing/teaching use case and for end users.

---

## Module N — Strategy Management (Save / Load / Version / Compare) {#module-n}

- **Save Strategy**: name, persist the full configuration (assets, weights, mode, all rules, all bands/thresholds) — not just the result.
- **Load / Edit / Re-run**: reopen a saved strategy back into the Strategy Builder, edit anything, re-run.
- **Strategy library view**: list of all saved strategies with key headline metrics shown inline (final value, CAGR, max drawdown) so the user can browse without opening each one.
- **Multi-select compare**: select 2+ saved strategies directly from the library and send them straight into the Module K comparison workspace.
- **Versioning (nice-to-have)**: keep prior versions of an edited strategy so a user can see how their own thinking/parameters evolved, and re-diff an old version against the current one.

---

## Module O — Alerts & Monitoring {#module-o}

Extends the backtester from purely historical analysis into a **forward-looking watchlist**, using the exact same Signal Engine (Module D) so logic is never duplicated between "backtest mode" and "live mode."

- **Watchlist**: attach any saved signal (relative ratio, PE band, drawdown-from-ATH, RSI, vol threshold, etc.) to a live-updating data feed.
- **Threshold alerts**: notify (in-app, and optionally email) when a band is crossed — e.g., "PE band crossed into 'Cheap' zone," "Small-cap/Large-cap ratio crossed 1.10."
- **Recommended-action display**: show the configured action (per the user's own band/trigger ladder) alongside the alert, so the tool tells the user what their *own rule* says to do, without giving independent advice.
- **Historical crossing log**: a running history of every time a given signal crossed a band, so the user can see how often a rule would actually have fired in real time (a useful reality check against "this strategy only had 3 trigger events in 15 years — is the complexity worth it?").

---

## 18. Consolidated Input Specification {#18-consolidated-inputs}

A single reference table of every input surface across the app, organized by where it lives in the UI.

### 18.1 Strategy-level inputs (apply once per strategy, i.e. once per "Strategy A" / "Strategy B" slot)
| Input | Notes |
|---|---|
| Strategy name | For save/load (Module N) |
| Strategy mode | Buy & Hold / Rebalance / Risk Targeting / Signal-Driven / Pair-Relative-Value / Factor Portfolio / Lumpsum-vs-Batch (Module B1) |
| Simulation start date / end date | Global window; auto-reconciled to common-period if assets don't all cover it (A4) |
| Benchmark selection | Any index/fund, including TRI variants |
| Inflation toggle | Nominal vs Real (G5) |
| Tax-on/off toggle + tax-rule set | Equity/debt/hybrid rules (G4) |
| Transaction cost assumption | Flat ₹ or bps (G2) |
| Liquidity ceiling | Max ₹ deployable per trigger (G6) |
| Behavioral-realism toggle | Perfect vs delayed/missed execution (G7) |

### 18.2 Per-asset inputs (repeated for each fund/index/ETF in the plan — extends your existing fund-card model)
| Input | Notes |
|---|---|
| Asset search & select | By name / AMC / ISIN / scheme code (already present) |
| Target weight % | New — running-total validator (B2) |
| Deviation rule type | Absolute vs Relative (B2) |
| Min/max allocation constraint | Optional (B2) |
| Minimum holding period | Optional, exit-load aware (B3) |
| Plan type | Direct/Regular, Growth/IDCW |
| Rules attached to this asset | Any combination of C1–C7 below |

### 18.3 Per-rule inputs
| Rule | Inputs |
|---|---|
| **Lumpsum (C1)** | Amount, date |
| **SIP (C2)** | Amount, frequency (daily/weekly/monthly), day-of-period, start date, end date |
| **Step-Up SIP (C3)** | Base amount, step type (absolute/%), step size, step frequency |
| **Smart/Booster SIP (C4)** | Base amount, driving signal (from D2), multiplier band table, optional source fund, optional target fund |
| **Conditional SIP (C5)** | Trigger reference (index or own portfolio), trigger %, amount, one-time/repeat flag |
| **STP (C6)** | Source fund, target fund, amount, frequency, start/end date |
| **SWP / Sell Rule (C7)** | Amount type (₹ / units / % of corpus), frequency or one-time, start/end date |
| **Batch deployment (C8)** | Total corpus, tranche count (or "optimize" flag → Module H3), interval, idle-capital rate |

### 18.4 Signal inputs (Module D)
| Input | Notes |
|---|---|
| Signal type | Relative ratio / Drawdown-from-ATH / PE band / 200-DMA trend / RSI / Mcap-to-GDP / Market breadth / VIX / Parabolic rally / Vol threshold / Composite |
| Source asset(s) | One or two series depending on type |
| Lookback window | For rolling/percentile/z-score transforms |
| Rebase date/value | For ratio signals |
| Evaluation frequency | Daily / Weekly / Monthly |
| Band/trigger-ladder table | Threshold, direction, action, magnitude, repeat flag (D3) |

### 18.5 Rebalancing inputs (Module F)
| Input | Notes |
|---|---|
| Rebalance trigger type | Frequency / Band / Hybrid |
| Frequency + anchor month | Already present for Annual; extend to Monthly/Quarterly/Half-yearly/Custom |
| Band thresholds | Per-asset, absolute or relative |
| Smart-SIP-rebalance toggle | On/off |
| Partial-rebalance % | Default 100% |
| Risk-targeting drawdown budget | Only for Risk Targeting mode (F4) |

### 18.6 Optimization inputs (Module H)
| Input | Notes |
|---|---|
| Number of Monte Carlo draws | e.g. 1,000 |
| Objective function | ROMAD / Return / Min-drawdown / Min-vol / Sharpe / Sortino / Composite |
| Per-asset weight bounds | Reuses B2/B3 constraints |
| Batch-count sweep range | For C8/H3 |

### 18.7 Comparison/scenario inputs (Module K)
| Input | Notes |
|---|---|
| Strategy slots to compare | A, B, C, D… (each independently configured per 18.1–18.6) |
| Preset comparison template | Optional — auto-fills two strategy slots (Section 21) |
| Scenario / stress window | Preset crisis window or custom date range |
| What-if toggle | Shift start date / toggle step-up / skip best-or-worst N months / sweep rebalance band |

---

## 19. Consolidated Output Specification {#19-consolidated-outputs}

Outputs are organized into the four layers from your own original outline, now fully populated with every metric/chart from Modules I–M.

### Layer A — Summary output (one row per strategy, shown first)
Final corpus · Total invested · Absolute return · CAGR · XIRR · Excess return over benchmark · Max drawdown · Volatility · Sharpe · Sortino · Calmar · ROMAD · Information ratio · Post-tax XIRR · Inflation-adjusted XIRR (when toggled on)

### Layer B — Time-series output
Portfolio value over time (per strategy) · Benchmark value over time · SIP/lumpsum/withdrawal cashflow timeline · Allocation drift over time (actual vs target, per asset) · Rebalancing event timeline · Tactical trigger event timeline · Buy/sell/switch/rebalance transaction log

### Layer C — Risk output
Max drawdown · Current drawdown · Drawdown duration / recovery days · Worst month / worst quarter · Monthly return distribution (histogram + heatmap) · Rolling return distribution (box plots, 1Y/3Y/5Y/7Y) · Downside capture · Upside capture · VaR · CVaR · Rolling volatility (1Y) · Rolling Sharpe (1Y) · Rolling correlation vs benchmark/other strategy (1Y)

### Layer D — Decision-quality output
Which rule helped most (rule-on vs rule-off differencing) · Which fund contributed most return · Which fund hurt the portfolio most · Did rebalancing improve results, net of cost/tax · Were tactical/timing rules statistically significant, or noise (Module J2) · Was the rule's edge overfit to a narrow period (Module D5/J4) · Regime-conditional win-rate breakdown (bull/bear/sideways) · Tax drag attributable to switching/rebalancing frequency · Behavioral-realism gap (perfect vs realistic execution)

### Bonus Layer E — New: Optimization & Statistical output (didn't exist in the original four-layer model; added because Modules H and J are large enough to warrant their own output layer)
Monte Carlo best weight vector + score · Distribution of all simulated outcomes · Efficient-frontier scatter · p-value / t-statistic / effect size per comparison per window length · Cycle-coverage note (how many bull/bear/sideways regimes are represented in the test window) · Entry-timing context (was the start date a peak/cheap/mid-cycle point)

---

## 20. End-to-End Working Pipeline {#20-working-pipeline}

```
STEP 0 — Screen the universe (Module L, optional)
  Filter funds by category/AUM/expense/rating/age → select candidates →
  "Add selected to Strategy Builder"

STEP 1 — Define strategy/strategies (Modules B, C, D, E, F)
  Pick strategy mode → add assets + weights → attach rules per asset
  (SIP/Lumpsum/Step-up/Smart-SIP/Conditional/STP/SWP/Batch) →
  configure any signal(s) + band/trigger ladder → configure rebalancing →
  set constraints. Repeat for Strategy B/C/D if comparing.

STEP 2 — Configure realism & framing (Modules G, A)
  Set tax on/off + tax rules → set transaction cost → set liquidity ceiling →
  set behavioral-realism toggle → set inflation toggle →
  pick benchmark → set/confirm simulation date range
  (engine auto-aligns to common period across all selected assets)

STEP 3 — System loads & prepares data (Module A)
  Fetch NAV/TRI/PE/macro series → adjust for splits/mergers/closures →
  forward-fill gaps, flag long gaps → apply survivorship-safe universe
  construction if requested → confirm common period to the user

STEP 4 — Simulate (Simulation Core, event-driven loop)
  For each date in the window:
    a. Evaluate any active Signal(s) (Module D)
    b. Resolve any Action(s) the signal(s) trigger (Module E) —
       respecting feasibility/liquidity (G6) and behavioral-realism (G7)
    c. Process any scheduled cashflow rules due today (Module C):
       SIP/step-up/smart-SIP/conditional/STP/SWP/batch tranche
    d. Apply transaction cost / exit load to anything that traded today (G2/G3)
    e. Check rebalancing trigger (frequency and/or band) (Module F);
       execute full/partial/smart-SIP rebalance if triggered
    f. Update unit holdings (FIFO lots for tax purposes), market value,
       actual vs target allocation, drift
    g. Log every action to the transaction ledger (E3)

STEP 5 — Compute analytics (Modules I, J)
  Performance, risk, ratios, consistency, benchmark-relative, allocation,
  cashflow, and attribution metrics → rolling-return distributions →
  statistical significance vs benchmark/other strategies →
  correlation → regime-conditional breakdowns

STEP 6 — Optimize (Module H, optional)
  If Monte Carlo or batch-size optimization was requested, re-run Steps 1–5
  across the sampled weight vectors / tranche counts, collect the
  distribution of outcomes, surface the best + the full spread

STEP 7 — Compare & contextualize (Modules K, J4–J5)
  Auto-build the rule-on/rule-off, rebalance/no-rebalance, and
  pre-tax/post-tax counterfactual pairs → run any selected scenario/
  stress windows → run any what-if toggles → attach cycle-coverage and
  entry-timing context

STEP 8 — Present results (Module M)
  Render in the "five questions" order: Did it work? → How safe? →
  How consistent? → What changed the result? → What should I trust? →
  expose full ledger, charts (with zoom/pan/fullscreen), and tables →
  offer PDF/HTML export

STEP 9 — Save / monitor (Modules N, O)
  Save the strategy configuration → optionally promote any signal to a
  live watchlist alert for ongoing (forward-looking) monitoring
```

---

## 21. Preset Comparison Library (one-click templates) {#21-preset-library}

Ship these as literal, selectable presets in the UI (each auto-fills Strategy A / Strategy B and sensible default parameters, which the user can then edit). This single library operationalizes nearly every idea sourced from the transcripts:

| # | Preset name | Strategy A | Strategy B |
|---|---|---|---|
| 1 | Portfolio vs Benchmark | User's portfolio | Selected benchmark (TRI) |
| 2 | Direct vs Regular | Same fund, Direct plan | Same fund, Regular plan |
| 3 | Growth vs IDCW | Same fund, Growth option | Same fund, IDCW option |
| 4 | SIP vs Lumpsum | Monthly SIP | Equivalent lumpsum on day 1 |
| 5 | SIP vs Staggered Batch | Monthly SIP | Same corpus split into N tranches |
| 6 | No Rebalance vs Frequency Rebalance | Buy & hold | Quarterly/Annual rebalance |
| 7 | Frequency vs Band vs Hybrid Rebalance | Frequency rebalance | Band-based rebalance (add Hybrid as C) |
| 8 | Equal-Weight vs Score-Weighted | Equal weight across funds | Weight by chosen ranking/score |
| 9 | Static vs Monte-Carlo-Optimized Allocation | User-set weights | Best weight vector from Module H |
| 10 | Active vs Index (per category) | Top active fund(s) in category, survivorship-safe | Category index fund |
| 11 | Single Fund vs Diversified Portfolio | One fund, 100% | Same total capital across N funds |
| 12 | Aggressive vs Conservative Allocation | High equity tilt | High debt tilt |
| 13 | Rule-On vs Rule-Off | Tactical/signal overlay active | Same plan, overlay disabled |
| 14 | Perfect vs Realistic Execution | No delay/missed triggers | Behavioral-realism enabled |
| 15 | Pre-Tax vs Post-Tax | Tax off | Tax on, equity/debt rules applied |
| 16 | Nominal vs Inflation-Adjusted | Nominal returns | Real (CPI-adjusted) returns |
| 17 | Relative-Valuation Pair Strategy vs Hold | Pair strategy (e.g. Smallcap/Largecap ratio-driven) | Plain SIP into either leg |
| 18 | PE-Band Strategy vs Plain SIP | PE-band-driven SIP | Plain fixed SIP |
| 19 | Buy-the-Dip vs Plain SIP | Drawdown-triggered SIP | Plain fixed SIP |
| 20 | Step-Up SIP vs Flat SIP | Step-up SIP | Flat SIP, same total eventual contribution |
| 21 | Smart/Booster SIP vs Flat SIP | Valuation-driven multiplier SIP | Flat SIP |
| 22 | Factor Portfolio vs Market-Cap Index | Momentum/Value/Quality/Low-Vol blend | Nifty 50 / Nifty 500 |
| 23 | Skip-Worst-N-Months vs Stay Invested | Strategy with N worst months removed | Fully invested |
| 24 | Skip-Best-N-Months vs Stay Invested | Strategy with N best months removed | Fully invested |
| 25 | Multi-Asset (Equity+Debt+Gold) vs Equity-Only | Multi-asset blend | Pure equity |

---

## 22. Engineering Architecture {#22-engineering-architecture}

### 22.1 Backend services
| Service | Responsibility |
|---|---|
| **Data Ingestion Service** | Pulls/refreshes NAV, scheme metadata, index, PE, and macro series from AMFI / mfapi.in / captnemo.in / Morningstar (your existing sources) on a schedule; normalizes into a common internal schema |
| **NAV & Scheme Database** | Stores time series (NAV/TRI/PE/macro) + scheme metadata; should support efficient range queries and as-of-date AUM lookups for survivorship-safe filtering |
| **Signal Service** | Computes any registered Signal type (Module D) over a given date range on demand; stateless, pure function of (asset(s), transform, window) → score series |
| **Simulation Engine** | The event-driven core loop (Step 4 of Section 20); consumes a fully resolved Strategy config + Signal outputs and produces a transaction ledger + daily portfolio-state series |
| **Analytics Service** | Consumes a portfolio-state/ledger series and computes every Module I/J metric; should be reusable across single-run and comparison contexts |
| **Optimization Service** | Wraps the Simulation Engine in a sampling loop for Monte Carlo / batch-size sweeps (Module H); should be parallelizable since each draw is independent |
| **Report Generator** | Assembles Module M outputs (charts + tables) into exportable PDF/HTML |
| **Alert/Monitoring Service** | Runs Signal Service against live-updating data on a schedule; compares against saved watchlist band tables; fires notifications |

### 22.2 Frontend components
- Strategy Builder form (extends current fund-card UI: add weight field, deviation-rule selector, rule-type tabs for SIP/Lumpsum/Step-up/Smart-SIP/Conditional/STP/SWP/Batch)
- Generic **Band/Trigger-Ladder Editor** (reusable across every Signal type — build once, parameterize everywhere)
- Fund/Index Screener (search, filters, chips, select-all/clear-all, "add to builder")
- Multi-strategy Comparison Workspace (A/B/C/D slots, preset picker from Section 21)
- Scenario/Stress-Test picker (preset crisis windows + custom range)
- Results Dashboard, organized per Module M4's "five questions" structure, with the chart library from M1 (zoom/pan/fullscreen on every time-series chart)
- Transaction Ledger table (filterable, exportable)
- Monte Carlo results view (best vector + distribution + efficient-frontier scatter)
- Strategy Library (save/load/version/compare entry point)
- Watchlist/Alerts panel

### 22.3 Storage
- Historical NAV/TRI/PE/macro database (time-series store)
- Scheme metadata store (relational)
- User strategy configs (JSON-serializable — should be literally the same schema the Strategy Builder UI edits, so save/load is a direct round-trip)
- Simulation result cache (keyed on strategy-config hash + date range, so re-opening a saved strategy doesn't always require a full re-simulation)
- Transaction ledgers (one per simulation run, linked to the strategy config + run timestamp)
- Watchlist/alert subscriptions

### 22.4 A note on computation cost
Monte Carlo optimization (Module H1) and statistical significance testing (Module J2) are the two heaviest computational features — each Monte Carlo draw is a full simulation run, and significance testing requires computing the *entire* rolling-return distribution, not just headline CAGR. Budget for these explicitly: consider capping default Monte Carlo draws (e.g. 500–1,000) with an "advanced" option to go higher, and pre-computing/caching rolling-return series per asset (rather than per comparison) since the same underlying asset's rolling-return series is reused across many different strategy comparisons.

---

## 23. Roadmap {#23-roadmap}

Sequenced against what you've already shipped, so each phase is additive to your current app rather than a rewrite.

### Phase 0 — Already shipped (per your screenshots)
Fund/index search · per-fund SIP/Lumpsum/Sell-rule cards · step-up %/yr · global simulation date range · Annual rebalancing with anchor month · a 4-signal Tactical Overlay (3 working + 1 pending on PE data) · debt-parking fund or synthetic-rate fallback · vol-threshold signal for Strategy 3.

### Phase 1 — Close the gaps in what's already there (highest leverage, lowest new-concept risk)
1. Ingest Nifty PE (and ideally PE for Midcap150/Smallcap250) → unblock **Strategy 4** using the exact band spec in Module D4.
2. Generalize the 4-strategy Tactical Overlay into the full Signal Engine + generic Band/Trigger-Ladder editor (Module D) — same UI pattern, but signal-type-agnostic instead of 4 hardcoded strategies.
3. Add **benchmark indices and any index as a backtestable asset in its own right** (not just as a display-only comparison), so Pair/Relative-Value strategies (Module B1, D2) become possible.
4. Add **target-weight fields + running-sum validator** to the existing fund-card UI (Module B2) — this single change unlocks true multi-asset portfolios instead of independent per-fund plans.
5. Add the **Analytics & Risk metrics catalog** (Module I) in full — CAGR/XIRR/Sharpe/Sortino/Calmar/ROMAD/VaR/drawdown-days/recovery-days — as the standard summary block on every run.
6. Add the **equity curve + drawdown/underwater chart + monthly-return heatmap** (the three highest-value, most-requested visualizations across every source).

### Phase 2 — Realism & comparison
7. Tax engine (Module G4) — STCG/LTCG, post-tax XIRR, tax-drag reporting.
8. Transaction cost + exit load modeling (G2/G3) and the transaction ledger (M3).
9. Full Rebalancing Engine (Module F) — frequency/band/hybrid, absolute-vs-relative deviation, Smart-SIP rebalancing.
10. Multi-strategy Comparison Workspace (Module K1) with the Preset Library (Section 21) — turn every "vs" idea into a one-click template.
11. Inflation adjustment toggle (G5).

### Phase 3 — Tactical depth & statistics
12. Step-Up SIP (absolute + percentage, Module C3), Smart/Booster SIP with source-target fund model (C4), Conditional SIP (C5), STP (C6).
13. Drawdown-from-ATH, RSI, 200-DMA, market-cap-to-GDP, market breadth, VIX signals (D2) layered onto the generic Signal Engine.
14. Market-regime classifier (D5) + regime-conditional reporting.
15. Lump-sum vs Batch deployment mode with batch-size optimizer (C8, H3).
16. Statistical Validation Engine (Module J) — rolling-return box plots, significance testing, rolling correlation.
17. Fund/index Screener (Module L) with survivorship-bias-safe, as-of-date universe construction (A5).

### Phase 4 — Optimization, attribution & platform features
18. Monte Carlo allocation optimizer with multiple objective functions (Module H1–H2).
19. Strategy attribution / decision-quality layer (Module I8) — rule-on/rule-off differencing, fund-level contribution, overfitting flags.
20. Strategy save/load/version + multi-select compare (Module N).
21. Behavioral-realism simulation (G7) — execution delay, missed-trigger probability.
22. Factor-portfolio builder (momentum/value/quality/low-vol, Module B1/D2).
23. PDF/HTML report export (M5).

### Phase 5 — Forward-looking & advanced allocation (longer horizon)
24. Alerts & Monitoring / live watchlist (Module O), reusing the Signal Engine.
25. Inverse-volatility weighting / volatility targeting / risk-parity rebalancing (F5/H4).
26. AI-assisted strategy creation, automatic feature suggestions, plain-language result narration, and strategy-robustness scoring (the natural next step once Modules D–K are stable enough for an assistant to reason over).

---

## Closing note

Almost everything in this document is one of two underlying primitives repeated with different parameters: **(1)** a *Signal → Trigger-Ladder → Action* pipeline (Modules D + E), and **(2)** a *cashflow-native simulation core that tracks real rupee movements and unit lots over time* (Module C + the Step-4 simulation loop). If you build those two primitives well and generically, roughly 80% of the feature list above — every "smart SIP," every "PE-band strategy," every "relative valuation pair trade," every macro-risk overlay — becomes a configuration you expose in the UI rather than new code you write. The remaining 20% (tax engine, statistical validation, Monte Carlo optimizer, rebalancing engine, reporting layer) are genuinely separate modules worth building with their own care, exactly as broken out above.

