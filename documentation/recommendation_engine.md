# Mutual Fund Recommendation Engine

This document details the rule-based recommendation engine for MutualFundAnalysis. The system acts as a digital financial planner, transforming a user's qualitative questionnaire inputs into a quantitative, well-diversified mutual fund portfolio.

## Overview of the Framework

The recommendation process is designed as a **9-layer decision pipeline**. The workflow processes inputs through risk assessment, strategy formulation, asset allocation, category selection, and finally fund scoring.

---

### Layer 1: Financial Risk Capacity
Assesses the user's *ability* to take financial risk based on hard facts.
- **Inputs used:** Income stability, emergency fund size, debt load, number of dependents, liquidity needs.
- **Logic:** 
  - If a user has irregular income, high debt, or high liquidity needs, capacity is **Conservative**.
  - If a user has stable income, >6 months of emergency savings, and no debt, capacity is **Aggressive**.
  - Otherwise, it defaults to **Balanced**.

### Layer 2: Emotional Risk Tolerance
Assesses the user's *willingness* to endure market volatility.
- **Inputs used:** Reaction to a 30% portfolio drop, overall investing experience.
- **Logic:**
  - "Panic and sell" or a beginner who is "concerned" maps to **Conservative**.
  - "Buy more at discount" + intermediate/expert maps to **Aggressive**.
  - Otherwise, **Balanced**.

### Layer 3: Final Risk Profile
Reconciles capacity and tolerance.
- **Logic:** We take the *minimum* of capacity and tolerance. If you have high tolerance but low capacity (or vice versa), the system restricts you to the safer profile.

### Layer 4: Investor Archetype & Goal Mapping
Translates the risk profile and goal into a recognizable archetype (e.g., "Tax Optimizer", "Aggressive Accumulator", "Capital Preserver"). 
- **Logic:** Mapped directly from `final_risk_profile`, `goal_type`, and `goal_horizon`. 

### Layer 5: Asset Allocation
Determines the percentage split between equity, debt, and satellite components.
- **Logic:** 
  - Horizon < 3 years: **90% Debt / 10% Equity**
  - Conservative: **75% Debt / 25% Equity**
  - Aggressive (10+ years): **70% Core Equity / 10% Debt / 20% Satellite Equity**
  - Balanced: **50% Core Equity / 45% Debt / 5% Satellite Equity**

### Layer 6: Strategy Formulation
Determines how the investment should be deployed and managed.
- **Inputs used:** Age, goal, horizon, income type.
- **Logic:** Recommends **SIP** (salary), **Lumpsum** (surplus capital + high experience), **STP** (lumpsum + conservative), or **SWP** (retirees seeking income). 

### Layer 7: Fund Universe Selection
Identifies which exact SEBI mutual fund categories should be picked to fulfill the asset allocation.
- **Logic:** 
  - Tax saving goal overrides to **ELSS**.
  - Ultra short-term horizons focus on **Liquid** and **Short Duration Funds**.
  - Aggressive long-term adds **Small Cap**, **Mid Cap**, and **Multi Cap**.
  - Conservative long-term sticks to **Large Cap**, **Index**, and **Balanced Advantage Funds**.

### Layer 8: Fund Scoring & Ranking
Within each selected category, we need to pick the best fund.
- **Logic:** Currently utilizes a composite scoring system weighted on three metrics:
  - **50% Performance:** Trailing 3-Year CAGR (normalized to 0-20%)
  - **25% Risk-Adjusted Returns:** Sharpe Ratio (normalized to 0-2.0)
  - **25% Cost:** Expense Ratio (inverted, lower is better)
- *Note:* The system defaults to Direct & Growth plans unless IDCW was explicitly requested.

### Layer 9: Portfolio Assembly
Picks up to a maximum of **5 distinct funds** (to prevent over-diversification/clutter). It assigns each fund a role (`core` or `satellite`) and generates a human-readable justification for why it was selected for the user.

---

## User Flow & UX

1. **Questionnaire (`recommendations/engine.py`):**
   - The user completes a 3-step wizard covering "About You", "Your Goal", and "Your Style".
   - If a user has already completed the questionnaire previously, returning to the engine automatically routes them to their results.

2. **Result Dashboard (`recommendations/result.html`):**
   - Displays the calculated Investor Archetype, Risk Profile, Strategy, and Review Frequency.
   - Highlights **Red Flags** (e.g., investing in equity without an emergency fund) and **Considerations** (e.g., tax inefficiencies of IDCW payouts).
   - Shows an interactive pie chart of the target allocation.
   - Lists the final 5 recommended funds.

3. **Editing Profiles:**
   - From the result dashboard, users can click "Edit Profile & Regenerate Recommendations" (`?edit=1`).
   - The questionnaire opens completely pre-filled with their past answers, allowing them to adjust parameters seamlessly.
