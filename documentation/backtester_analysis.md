# Mutual Fund Portfolio Backtester: Architectural & Implementation Guide

This document provides a comprehensive technical guide to the **Mutual Fund Portfolio Backtester** implementation. It outlines the core architecture, data flow, mathematical calculations (including Time-Weighted Returns), and the logic behind tactical overlays and rebalancing strategies.

---

## 1. System Architecture & Data Flow

The portfolio backtester simulates historical investment plans (including monthly/quarterly SIPs, lumpsums, trailing-stop sells, and trigger-based purchases) across a basket of mutual funds and indices. It also runs four **Tactical Overlay (What-If)** strategies side-by-side with the "Base Plan" to show how active risk management affects returns.

### Core Architecture Diagram

```mermaid
graph TD
    A[Client Request: JSON Payload] --> B[portfolio_backtester_api in views.py]
    B --> C[PortfolioPlan Dataclass]
    C --> D[run_plan_simulation in backtester.py]
    
    D --> E[Load Historical Price Series]
    E -->|Mutual Funds| E1[NAVHistory Database/mstarpy]
    E -->|Benchmark Indices| E2[BenchmarkNAV Database/yfinance]
    
    D --> F[Align Intersecting Date Range]
    D --> G[Generate/Load Debt Parking Series]
    G -->|Custom Selected Fund| G1[Real Debt NAV Series]
    G -->|No Selected Fund| G2[Synthetic Daily Growth Series]
    
    D --> H[Pre-Build Scheduled Events Map]
    H --> I[Simulate 5 Strategy Variants]
    I -->|Base Plan| J1[Continuous Allocation]
    I -->|Trend Filter| J2[12M trailing Momentum Filter]
    I -->|MA Filter| J3[10M Simple Moving Average Filter]
    I -->|Vol Control| J4[6M Realized Volatility Filter]
    I -->|Composite Signal| J5[Combined MA + Trend Filter]
    
    I --> K[Rebalancing Engine]
    I --> L[Mathematical Metrics Suite (Unitized TWR)]
    
    L --> M[Assemble SimulationResult]
    M --> N[JSON API Response]
```

### Flow Sequence
1. **Request Deserialization**: The JSON payload from the front-end is parsed in `apps/portfolio/views.py`.
2. **Historical Data Loading**: Daily prices (NAV) are queried from `NAVHistory` (funds) and `BenchmarkNAV` (indices). Missing ranges are fetched on-demand.
3. **Overlapping Alignment**: Dates are restricted to the common intersection across all selected equity funds to prevent backtest distortion from mismatched inception dates.
4. **Scheduled Event Map**: Before entering the simulation loop, SIP dates and non-triggered lumpsums are pre-computed and stored in a hash-map keyed by date to prevent date-shifting arithmetic during execution loop.
5. **Simulation Loop**: The engine steps daily through the aligned timeline. At each date:
   - SIP and lumpsum purchases are executed.
   - Sells or trigger-based lumpsums are evaluated.
   - Tactical signals are computed to redirect equity cash flows to the debt parking fund if the signal is **OFF**.
   - Rebalancing (annual or threshold-based) is checked.
6. **Metrics Calculations**: Absolute gains, CAGR, XIRR, rolling 5-year metrics, volatility, Sharpe, Sortino, drawdowns, and calendar returns are calculated.

---

## 2. Unitized Portfolio Accounting (TWR vs IRR)

A significant feature of this backtester is its **Unitized Portfolio NAV** accounting.

When an investor adds cash to a portfolio (via SIPs or lumpsums), the absolute size of the portfolio grows. If risk metrics or calendar returns were calculated simply on the absolute size of the portfolio, the continuous cash injections would artificially inflate the "returns" (e.g. adding ₹10,000 to a ₹100,000 portfolio looks like a 10% daily return).

To solve this, the backtester simulates a **Mutual Fund NAV structure** for the portfolio itself:
1. The portfolio starts at an arbitrary `port_nav = 100.0`.
2. As markets move, the `port_nav` moves exactly in tandem with the underlying funds' weighted returns.
3. When the user deposits a SIP, they "buy" new `port_units` at the current `port_nav`. The cash injection increases the total portfolio value and the total units, but **leaves the `port_nav` completely unchanged**.

### Why Calendar Returns May Seem High
Users often notice that calendar returns for their portfolio (especially for years like 2020 or 2021) seem exceptionally high, sometimes 50% or 60%+, even if their absolute gain on the money they invested that year is much lower. 

This happens because **Calendar Returns** in this backtester represent the **Time-Weighted Return (TWR)** of the underlying strategy. It measures how the underlying basket of assets performed during that calendar year, completely independent of the user's cash-flow timing. If the underlying Mid Cap funds rallied 60% in 2021, the calendar return will show 60%, even if the user only started their SIP halfway through the year. To see the personal cash-flow weighted return, users should look at the **XIRR** metric.

---

## 3. Tactical Signals

When a tactical overlay strategy is active, the engine checks whether to buy equity or redirect to debt using daily indicators:
* **Trend Filter (12M Trail)**: If the fund's NAV is greater than its NAV exactly 12 months ago, the signal is **ON**. Otherwise, new SIPs are redirected to the debt parking fund.
* **MA Filter (10M SMA)**: If the current NAV is greater than the average NAV over the trailing 10 months, the signal is **ON**.
* **Volatility Control (6M realized)**: Standard deviation of daily log returns over the trailing 6 months is annualized. If it is less than the user-specified threshold (default 20%), the signal is **ON**.
* **Composite Filter**: Standard arithmetic ensemble. If both MA and Trend agree or average signal strength is $> 0.5$, the signal is **ON**.

---

## 4. Rebalancing Engine

* **Annual Rebalance**: Triggers on the user's chosen `anchor_month` (e.g. January) on the first simulated date of that month. It buys and sells equity fund units and uses the `debt_park_id` (or synthetic debt) to balance capital injections and withdrawals.
* **Drift Threshold**: Compares the current allocation percentage of each equity fund against its target weight. If the absolute difference exceeds the user-specified threshold (e.g. 5%), rebalancing occurs immediately.

---

## 5. API Reference & Payload Specifications

### API Endpoint: POST `/portfolio/backtester/api/`

The API receives the full portfolio plan, processes the simulation via the backtesting engine, and returns a detailed dashboard metrics payload.

#### Key Query/Payload Parameters
| Field | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| `funds` | Array | List of selected funds and their custom investment/sell rules. | *Required* |
| `rebalance_mode` | String | Rebalancing rule: `"none"`, `"annual"`, or `"threshold"`. | `"none"` |
| `rebalance_threshold`| Float | Drift percentage trigger for threshold rebalancing. | `5.0` |
| `rebalance_anchor_month`| Integer | Month index (1-12) used to anchor annual rebalances. | `1` |
| `debt_park_source_type` | String | Source type for parking debt fund: `"scheme"`, `"index"`, or `""`.| `""` |
| `debt_park_id` | String | Scheme AMFI code or index identifier for parked capital. | `""` |
| `debt_park_name` | String | The display name of the debt parking fund. | `""` |
| `vol_threshold` | Float | Annualized volatility percentage limit for Strategy 3 control. | `20.0` |
| `debt_return_pct` | Float | Configurable p.a. compound rate for synthetic debt proxy. | `7.0` |

