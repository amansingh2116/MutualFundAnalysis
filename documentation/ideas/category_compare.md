# Mutual Fund Category Comparison: Analyst's Metric Framework

Here's how a research analyst structures a cross-category comparison — not just fund vs. fund, but understanding *why* one category behaves differently from another.

---

## 1. Return Metrics

**Trailing Returns (1Y / 3Y / 5Y / 10Y CAGR)**
The most common starting point. Always compare to the category average *and* the benchmark index, not just in isolation. A 15% 3Y CAGR in a Mid Cap fund is mediocre; in a Liquid fund it's impossible — so returns are only meaningful *within context*.

**Rolling Returns**
Superior to trailing returns. You compute the annualized return for every possible period of a fixed length (say, every 3Y window over the last 10 years). This removes start/end date bias. Key stats: mean rolling return, % of rolling periods with positive returns, consistency. A fund with 14% mean 3Y rolling but 30% of windows being negative is very different from one with 12% mean but 95% positive windows.

**Category Average Alpha (vs. Benchmark)**
How much excess return the *category as a whole* has delivered over its benchmark. Helps you decide if active management in that category is worth paying for. E.g., Large Cap active funds have consistently delivered near-zero alpha post-expense — the category-level argument for index funds. Flexi-Cap and Mid Cap active funds have historically shown positive category alpha.

---

## 2. Risk Metrics

**Standard Deviation (Volatility)**
Measures dispersion of monthly/annual returns. Use annualized SD. A Sectoral fund may show 22–28% SD; a Liquid fund sits at <0.5%. Use this to set realistic investor expectation ranges.

**Maximum Drawdown (MDD)**
The largest peak-to-trough decline in NAV history. This is what investors *actually experience* in a crisis. Mid Cap categories saw ~50–55% MDD in 2008; Liquid categories saw near-zero. Critical for assessing downside pain and time-to-recovery.

**Beta (vs. Benchmark)**
Measures sensitivity to benchmark movements. A beta of 1.2 means the fund moves 1.2× the index. For cross-*category* comparison, beta is more useful as a relative number — e.g., Small Cap funds tend to have beta >1 vs. Nifty 500, while Debt or Liquid categories have near-zero market beta. Don't compare betas across different benchmarks directly.

**Value at Risk (VaR) / CVaR**
VaR at 95% tells you: "In the worst 5% of months historically, losses exceeded X%." CVaR (Conditional VaR, also called Expected Shortfall) is what the *average* loss looks like in those worst 5% of months — a more complete tail-risk picture. Relevant for Sectoral and Small Cap comparisons.

---

## 3. Risk-Adjusted Return Metrics

These are the *core* metrics for apples-to-apples cross-category comparison because they normalize for risk.

**Sharpe Ratio**
`(Portfolio Return − Risk-Free Rate) / Standard Deviation`
Tells you return per unit of *total* risk. Higher is better. Problem: penalizes upside and downside volatility equally. A Liquid fund with near-zero SD will almost always show a higher Sharpe than an Equity fund — so Sharpe is better used *within* a category, not across radically different ones.

**Sortino Ratio**
`(Portfolio Return − Risk-Free Rate) / Downside Deviation`
Same as Sharpe, but only penalizes *downside* volatility (returns below a minimum acceptable return, usually 0% or the risk-free rate). More appropriate when comparing categories where asymmetric upside is expected. A Mid Cap fund with high upside vol but low downside vol will look better on Sortino than Sharpe.

**Treynor Ratio**
`(Portfolio Return − Risk-Free Rate) / Beta`
Return per unit of *systematic* (market) risk. More appropriate for diversified investors comparing categories that will sit alongside other assets in a portfolio, since unsystematic risk gets diversified away.

**Information Ratio (IR)**
`Active Return / Tracking Error`
Active Return = Fund Return − Benchmark Return. Tracking Error = SD of active returns. IR measures how consistently the fund manager adds alpha. Used for within-category comparison of active vs passive efficiency. An IR > 0.5 sustained over 5 years is considered strong.

**Calmar Ratio**
`Annualized Return / Maximum Drawdown`
Particularly useful for Sectoral and thematic categories that go through deep drawdown cycles. A fund that returned 18% CAGR but had a 55% MDD has a Calmar of ~0.33 — much worse than a 14% CAGR fund with 25% MDD (Calmar ~0.56).

---

## 4. Portfolio Characteristics

**Expense Ratio**
The annual fee as a % of AUM. In Equity categories (active), typical range is 0.5–2.0%; in Liquid/Overnight, it should be <0.2%. This is a guaranteed drag on returns — a 1.5% expense ratio requires the fund manager to generate 1.5% alpha *just to break even* versus a free index. For Liquid funds especially, expense ratios are the primary differentiator.

**Portfolio Concentration (Top 10 / Top 5 Holdings %)**
High concentration = high active bets but higher idiosyncratic risk. A Sectoral fund with 60% in top 5 stocks is very different from a Large Cap fund with 35% in top 5. Compare this to the benchmark's concentration to understand how differentiated the portfolio really is.

**Active Share**
Percentage of the portfolio that differs from the benchmark. Range: 0% (pure index clone) to 100% (completely different). Low-active-share "closet index" funds with high expense ratios are red flags. Useful when comparing supposedly "active" Large Cap funds vs. Flexi Cap funds.

**Turnover Ratio**
Percentage of the portfolio replaced in a year. High turnover (>100%) implies a lot of trading activity — increases transaction costs and tax drag (short-term capital gains). Relevant for after-tax return calculations. Sectoral funds during theme rotation can show very high turnover.

**Portfolio P/E and P/B**
Tells you the valuation profile of the category's holdings. A Mid Cap category trading at 35× P/E vs. historical average of 22× is a different risk proposition than when it traded at 18×. Used for mean-reversion and cycle analysis.

**Average Market Cap / Cap Allocation**
For equity categories — what % is in Large / Mid / Small Cap. This determines *where* the category sits in the risk-return spectrum and also determines regulatory classification compliance (SEBI mandates, e.g., Mid Cap funds must hold ≥65% in mid cap stocks).

---

## 5. Category-Specific Considerations

| Category | Watch Especially |
|---|---|
| **ELSS** | 3-year lock-in, tax saving u/s 80C; compare post-lock-in CAGR and fund manager stability |
| **Liquid / Overnight** | Credit quality of holdings (% AAA), modified duration, YTM spread over repo rate |
| **Mid Cap / Small Cap** | Drawdown depth, time-to-recovery, rolling 5Y returns, liquidity of underlying stocks |
| **Sectoral / Thematic** | Cycle timing risk, sector concentration, exit timing dependency — not for passive SIP investors |
| **Flexi Cap / Multi Cap** | Active allocation shifts across market caps — check how allocation changed during market stress |
| **Debt (Short/Medium Duration)** | Modified Duration, YTM, Credit Risk (% below AA), Interest Rate Sensitivity |

---

## Analyst's Comparison Checklist (Summary Order)

Start with **category mandate** (what is it *allowed* to hold), then look at **rolling returns + consistency**, then **risk metrics (MDD, SD)**, then **risk-adjusted metrics (Sortino, IR)**, then **cost (expense ratio + turnover)**, and finally **portfolio quality (concentration, P/E, credit quality)**. Never compare a Sectoral fund to a Liquid fund on Sharpe alone — always anchor metrics to the category's own benchmark and peer group.

The goal isn't to find the "best" metric — it's to triangulate. A fund that looks good on returns but bad on Calmar and high on turnover is a very different proposition from one with moderate returns but tight drawdown control and low costs.