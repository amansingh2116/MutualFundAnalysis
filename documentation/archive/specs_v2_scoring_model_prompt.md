<USER_REQUEST>
I already have a mutual fund scoring model for scoring mutual funds based on various parameters, note that updating the model should change few things in project which you can find, like the analysis section of funds analysis tab, while doing migration/ingestion/population we find the scores for funds to rank funds in various tabs in research sections of side bar, etc, so accordingly handle all that and I want to update and improve the model with the following one (whatever is feasible):
# MF Analysis Platform — Fund Scoring Model (v2)

> **Last updated:** 2026-06-25
> **Model version:** 2.0
> **Status:** Production (v2)
> **Replaces:** v1.0 (2026-05-28)

---

## Changelog from v1 → v2

| What changed | Why |
|---|---|
| Added **Manager Quality** as a 6th pillar (10%) | v1 had no signal for fund manager skill or AMC governance — a critical blind spot identified in the book |
| Added **Debt-Specific Pillar** for debt/hybrid funds (replaces Composition for those categories) | Debt funds require duration, credit quality, and yield analysis not captured by equity-style composition metrics |
| **Information Ratio** added to Risk pillar | Morningstar's updated Medalist methodology (Nov 2025) uses IR as the primary active-management skill signal |
| **Rolling return win rate** expanded to 3Y and 5Y windows with consistency penalty | Catches "lucky period" funds that spike once and mean-revert |
| **Liquidity score** added to Composition pillar for equity funds | CRISIL's CMFR uses portfolio liquidity as a standalone check; important for small/mid-cap AUM concentration risk |
| **Portfolio Turnover** added as a sub-metric | High turnover funds incur hidden transaction costs that erode returns; the book explicitly warns about this |
| **AMC governance red flag** added | Addresses front-running (Axis MF 2022), SEBI regulatory actions, and the book's section on frauds/controversies |
| **Category-aware weight tables** for equity vs. debt vs. hybrid vs. index | One weight set doesn't fit all — index funds should not be scored on active-manager metrics |
| Improved **normalization bounds** calibrated to Indian market data (Nifty, category averages) | v1 used generic bounds; bounds are now grounded in AMFI data and SEBI category norms |
| **Confidence level system** redesigned with 4 tiers | Clearer communication to end users about how much to trust a score |

---

## 1. Overview

The Fund Scoring Model v2 is a **category-normalized, multi-pillar quantitative framework** that evaluates mutual funds across **six independent pillars** and produces a single composite score (0–100). The model is designed to reflect risk-adjusted value and manager quality, not raw past performance.

### Core Design Principles

1. **Category-first**: All scoring is relative to the fund's SEBI category peer group. Equity funds are never compared to debt funds. Index funds are scored differently from actively managed funds.
2. **No single-factor dominance**: No single metric can dominate the score. Return quality, downside control, cost discipline, portfolio construction, and manager quality all matter.
3. **Transparent fallbacks**: When data is missing, the system reduces confidence level rather than fabricating a score. Each pillar may be `Rated`, `Provisional`, or `Skipped`.
4. **Not a prediction**: The score reflects historical and current data quality. It is **not** a forecast of future returns.
5. **Pillar weights adapt by fund type**: Equity, Debt, Hybrid, and Index/ETF funds have different weight tables because the drivers of quality differ across these categories.

---

## 2. Score Structure

### 2.1 Formula (Actively Managed Equity / Hybrid Funds)

```
Final Score = 0.30 × Performance
            + 0.25 × Risk / Stability
            + 0.15 × Cost
            + 0.15 × Composition & Liquidity
            + 0.15 × Manager Quality
            − Red Flag Penalty   (max 20 pts)

Clamped to [0, 100]
```

### 2.2 Pillar Weight Table by Fund Type

| Pillar | Equity (Active) | Debt | Hybrid | Index / ETF |
|---|---|---|---|---|
| **Performance** | 30% | 30% | 30% | 40% |
| **Risk / Stability** | 25% | 25% | 25% | 30% |
| **Cost** | 15% | 20% | 15% | 25% |
| **Composition & Liquidity** | 15% | — | 15% | — |
| **Debt Quality** | — | 15% | 5%* | — |
| **Manager Quality** | 15% | 10% | 10% | 5% |
| **Red Flag Penalty** | −20 max | −20 max | −20 max | −15 max |

> *For hybrid funds, the Debt Quality pillar is scaled to the fund's average debt allocation (e.g., a 65/35 equity-debt fund applies Debt Quality at 35% × 15% weight). The remaining weight flows to Composition.

**Why different weights?**
- **Index/ETF funds**: Manager Quality matters very little (passive); Cost and tracking-quality matter more. No Composition pillar since the index defines the portfolio.
- **Debt funds**: Composition (stock concentration) is replaced by the more relevant Debt Quality (duration, credit, YTM). Cost matters more because 0.1% of expense ratio has a larger proportional impact on a debt fund's 7% expected return than on an equity fund's 12%.
- **Hybrid funds**: Both equity and debt dimensions are partially relevant; weights are blended.

---

## 3. Pillar Definitions

### 3.1 Performance Score (0–100)

Measures **quality, consistency, and breadth of returns** across multiple timeframes. Consistency matters as much as magnitude.

#### 3.1.1 Sub-metrics (Equity / Hybrid Active Funds)

| Sub-metric | Weight | Formula | Why it matters |
|---|---|---|---|
| 3Y trailing CAGR | 30% | `normalize(cagr_3y, low=0, high=22)` | Most reliable single horizon; balances recency and duration |
| 5Y trailing CAGR | 20% | `normalize(cagr_5y, low=0, high=18)` | Full market cycle coverage; filters lucky short-run funds |
| 1Y trailing CAGR | 10% | `normalize(cagr_1y, low=-10, high=35)` | Recency signal; lower weight to prevent one-year gaming |
| 3Y Rolling Win Rate (vs 0%) | 15% | `win_rate_3y_vs_0 / 100` | Probability of positive 3Y return over all rolling windows |
| 5Y Rolling Win Rate (vs 0%) | 10% | `win_rate_5y_vs_0 / 100` | Longer-horizon consistency; penalizes cyclically bad decades |
| Excess return vs benchmark (3Y) | 10% | `normalize(excess_3y, low=-5, high=10)` | Alpha generation above benchmark; the whole point of active management |
| Return Consistency Score | 5% | See §3.1.3 | Penalizes high variance in calendar year returns |

**Total: 100%**

#### 3.1.2 Sub-metrics (Debt Funds)

| Sub-metric | Weight | Formula |
|---|---|---|
| 3Y trailing CAGR | 40% | `normalize(cagr_3y, low=4, high=10)` |
| 1Y trailing CAGR | 25% | `normalize(cagr_1y, low=3, high=9)` |
| 3Y Rolling Win Rate (vs category average) | 20% | `win_rate_vs_cat_avg / 100` |
| Excess return vs benchmark (3Y) | 15% | `normalize(excess_3y, low=-2, high=3)` |

#### 3.1.3 Normalization Formula

```
score = clamp((value − low) / (high − low), 0, 1) × 100
```

Values below `low` score 0; values above `high` score 100.

#### 3.1.4 Return Consistency Score

Measures how stable the fund's calendar year returns are. A fund that returns 12% every year is better than one that returns 30%, −10%, 30%, −10%, even if CAGR is similar.

```
calendar_year_returns = [r1, r2, r3, ...]   (last 5 calendar years)
consistency_score = clamp(1 − std(calendar_year_returns) / 30, 0, 1) × 100
```

A standard deviation of 0% in annual returns → score 100. A std of 30% (very erratic) → score 0.

#### 3.1.5 Index / ETF Performance

For index funds, the only performance metric that matters is **tracking quality** — how faithfully the fund replicates its index. Active alpha generation is not expected.

| Sub-metric | Weight | Formula |
|---|---|---|
| 1Y Tracking Difference (fund return − index return) | 50% | `normalize(-tracking_diff_1y, low=-1.5, high=0)` |
| Tracking Error (annualized std of daily diff) | 30% | `normalize(-tracking_error, low=-0.5, high=0)` |
| 3Y Tracking Difference | 20% | `normalize(-tracking_diff_3y, low=-1.5, high=0)` |

> **Why tracking difference, not tracking error?** Tracking difference measures the actual performance gap; tracking error measures volatility of that gap. A fund can have low tracking error but consistently lag the index. Both are needed. The book correctly identifies tracking error as a core index fund metric.

#### 3.1.6 Fallback Cascade

- If 3Y CAGR missing → substitute 5Y or 1Y, reduce weight proportionally, mark pillar `Provisional`
- If all trailing CAGRs missing → pillar is `Unrated`
- If benchmark missing → excess return sub-score = 0 (not penalized, but noted)

---

### 3.2 Risk / Stability Score (0–100)

Measures **downside control, risk-adjusted return quality, and benchmark discipline**. Upside volatility is not penalized.

#### 3.2.1 Sub-metrics (Equity Active / Hybrid)

| Sub-metric | Weight | Formula / Notes | Why it matters |
|---|---|---|---|
| Sortino Ratio (3Y) | 25% | `normalize(sortino, low=0, high=3.0)` | Penalizes only bad volatility — the book emphasizes this distinction from Sharpe |
| Max Drawdown (3Y) | 20% | `normalize(-drawdown, low=-60, high=-5)` | How badly you could have bled in the worst stretch; Indian equity can drop 50-60% |
| Downside Capture Ratio (3Y) | 20% | `normalize(100 − dc, low=-30, high=30)` | Did the fund fall less than the market when it fell? |
| Sharpe Ratio (3Y) | 15% | `normalize(sharpe, low=0, high=2.5)` | Overall risk-adjusted return relative to risk-free rate (10Y Gsec) |
| Information Ratio (3Y) | 10% | `normalize(ir, low=-0.5, high=1.0)` | Consistency of alpha generation relative to tracking error |
| Beta (3Y) | 5% | `normalize(1.2 − beta, low=0, high=0.7)` | Lower beta preferred, but only as tiebreaker — a low-beta fund with low returns is not good |
| Upside/Downside Capture Asymmetry | 5% | `normalize(uc − dc, low=-20, high=40)` | Ideally: capture more upside than downside; asymmetry > 0 is good |

**Total: 100%**

> **Note on Information Ratio**: IR = (Fund return − Benchmark return) / Tracking Error. An IR of 0.5 is considered good; 1.0 is excellent. For index funds, IR is not computed (tracking error is near zero by design). This metric was adopted from Morningstar's updated November 2025 Medalist methodology which uses information ratio as the primary Process Pillar signal for active funds.

#### 3.2.2 Sub-metrics (Debt Funds)

| Sub-metric | Weight | Formula |
|---|---|---|
| Sharpe Ratio (3Y) | 30% | `normalize(sharpe, low=0, high=2.0)` |
| Sortino Ratio (3Y) | 25% | `normalize(sortino, low=0, high=2.5)` |
| Max Drawdown (3Y) | 25% | `normalize(-drawdown, low=-20, high=-0.5)` |
| Downside Capture (3Y) | 20% | `normalize(100 − dc, low=-20, high=30)` |

#### 3.2.3 Risk Score Interpretation

| Score | What it means |
|---|---|
| 80–100 | Exceptional downside protection; fund consistently absorbs shocks well |
| 60–79 | Above-average risk control with minor vulnerabilities |
| 40–59 | Category-average volatility and drawdown |
| 20–39 | Notable downside risk; max drawdowns or high capture ratios |
| 0–19 | Severe risk profile; large drawdowns and/or negative Sharpe |

#### 3.2.4 Fallback

- If 3Y risk metrics unavailable → use 5Y equivalents; mark `Provisional`
- If neither 3Y nor 5Y available → pillar `Unrated`

---

### 3.3 Cost Score (0–100)

Measures **total cost efficiency** relative to category norms. Cost is a guaranteed drag on returns — unlike performance, it is entirely within the fund house's control.

#### 3.3.1 Expense Ratio Thresholds (Updated)

| Category Type | Excellent (<) | Good (<) | Average (<) | Poor (≥) |
|---|---|---|---|---|
| Equity – Direct | 0.30% | 0.60% | 1.00% | 1.50% |
| Equity – Regular | 0.80% | 1.20% | 1.75% | 2.25% |
| Index / ETF – Direct | 0.05% | 0.15% | 0.30% | 0.50% |
| Index / ETF – Regular | 0.15% | 0.30% | 0.50% | 0.80% |
| Debt – Direct | 0.20% | 0.40% | 0.70% | 1.00% |
| Debt – Regular | 0.50% | 0.80% | 1.20% | 1.50% |
| Hybrid – Direct | 0.40% | 0.70% | 1.10% | 1.60% |
| Hybrid – Regular | 0.90% | 1.30% | 1.80% | 2.30% |
| Default | 0.50% | 1.00% | 1.50% | 2.00% |

Expense ratio score (70% of Cost pillar):
```
er_band_score = map(er_vs_thresholds) → 100 / 75 / 50 / 25 / 0
```

#### 3.3.2 AUM Size Factor (30% of Cost pillar)

| AUM | Score |
|---|---|
| > ₹10,000 Cr | 100 |
| ₹5,000–10,000 Cr | 85 |
| ₹1,000–5,000 Cr | 70 |
| ₹500–1,000 Cr | 50 |
| ₹100–500 Cr | 30 |
| < ₹100 Cr | 10 |

> **Why AUM matters for cost**: Small AUM funds spread fixed costs (compliance, operations, fund manager salary) over fewer investors, structurally raising expense ratios. Very large AUM (>₹10,000 Cr) gets economies of scale. However, for small-cap funds, very large AUM constrains the fund manager's ability to deploy capital efficiently — this is handled via a red flag in §3.6, not the cost pillar.

#### 3.3.3 Exit Load Sub-metric (informational, not scored)

Exit load is reported alongside the Cost score but not included in the score formula because it depends on investor holding period. A 1% exit load within 1 year doesn't hurt a 10-year investor but is very punishing for a 6-month holder. It is flagged when exit load is >1% or when the lock-in period exceeds 3 years (beyond ELSS lock-in norms).

---

### 3.4 Composition & Liquidity Score (0–100)

*Applies to equity and hybrid funds only. Debt funds use Pillar 3.5 (Debt Quality) instead.*

Measures **portfolio construction quality**: diversification, concentration risk, liquidity, and trading discipline.

#### 3.4.1 Sub-metrics

| Sub-metric | Weight | Formula | Why it matters |
|---|---|---|---|
| Top-10 Concentration | 30% | `clamp((90 − top10_pct) / 50, 0, 1) × 100` | High concentration amplifies single-stock risk; book explicitly warns about this |
| Sector HHI (Herfindahl-Hirschman Index) | 25% | `clamp(1 − HHI / 0.5, 0, 1) × 100` | Sector concentration risk; important for thematic drift in multi-cap / flexi-cap |
| Holdings Count | 15% | `clamp((count − 5) / 45, 0, 1) × 100` (cap at 60 stocks) | Too few = concentration; too many (>60) = closet indexing |
| Portfolio Liquidity Score | 20% | See §3.4.2 | CRISIL's CMFR includes this; critical for small/mid-cap funds |
| Portfolio Turnover | 10% | `normalize(1 − turnover/5, 0, 1) × 100` | Very high turnover (>400%) indicates churn and higher hidden transaction costs |

**Total: 100%**

#### 3.4.2 Portfolio Liquidity Score

Based on the tradability of the fund's holdings. Specifically, what percentage of the fund's portfolio can be liquidated within a reasonable timeframe (3–5 trading days) without significant market impact?

```
liquid_pct = weight of holdings in large-cap (top 100 stocks by market cap)
semi_liquid_pct = weight in mid-cap (rank 101–250)
illiquid_pct = weight in small-cap (rank 251+) + unlisted + debt instruments with low trading volume

liquidity_score = (1.0 × liquid_pct + 0.6 × semi_liquid_pct + 0.1 × illiquid_pct) × 100
```

This score is then normalized: `normalize(liquidity_score, low=20, high=95)`.

> **Why this matters**: The Franklin Templeton 2020 fiasco (referenced in the book) was fundamentally a liquidity crisis. A small-cap fund with ₹50,000 Cr AUM that holds 65% in illiquid small-cap stocks will struggle to meet mass redemptions. Liquidity scoring prevents the model from rewarding high-conviction illiquid funds without flagging the structural risk.

#### 3.4.3 Portfolio Turnover Interpretation

```
turnover < 30%   → buy-and-hold (PPFAS style) → high score
turnover 30–80%  → actively managed          → medium score
turnover 80–200% → frequent rebalancing       → lower score
turnover > 400%  → very high churn (Quant style) → low score unless justified by IR
```

The book's Quant vs PPFAS case study shows that high turnover can coexist with high performance — but this must be justified by an above-average Information Ratio. If IR is strong (>0.7), the turnover penalty in Composition is offset by the IR gain in Risk. If IR is weak, high turnover is pure value destruction.

#### 3.4.4 Fallback

- If no holdings data → pillar `Unrated`, note reason explicitly. Apply −2 pt red flag.
- Partial holdings (top 10 known, sector unknown) → compute available sub-metrics; weight redistribute proportionally; mark `Provisional`.

---

### 3.5 Debt Quality Score (0–100)

*Applies to debt funds only. Also partially applied to hybrid funds (see weight table in §2.2).*

Measures the **interest rate risk, credit quality, and yield sustainability** of the fixed-income portfolio.

#### 3.5.1 Sub-metrics

| Sub-metric | Weight | Formula | Why it matters |
|---|---|---|---|
| Credit Quality Score | 35% | See §3.5.2 | Single largest determinant of default risk in a debt fund |
| Modified Duration Score | 25% | See §3.5.3 | Duration mismatch with investor holding period = interest rate risk |
| Yield-to-Maturity vs Category Average | 20% | `normalize(ytm − cat_ytm_avg, low=-2, high=2)` | Is the yield pickup justified by credit risk, or is it free lunch? |
| Portfolio Liquidity (Debt) | 20% | `normalize(% in sovereign + AAA, low=30, high=100)` | Concentration in low-liquidity credit = Franklin Templeton risk |

**Total: 100%**

#### 3.5.2 Credit Quality Score

Based on the weighted average credit rating of portfolio holdings:

| Credit Rating Band | Score per unit weight |
|---|---|
| Sovereign / G-Sec | 100 |
| AAA / A1+ | 95 |
| AA+ | 80 |
| AA | 65 |
| AA− | 50 |
| A+ and below | 20 |
| NR / Unrated | 10 |

```
credit_score = Σ(weight_i × score_i) / Σ(weight_i)
```

**Why**: SEBI's Potential Risk Matrix (PRC) classifies credit risk into Low/Medium/High. Our score mirrors this but with finer granularity. AA− and below constitute meaningful credit risk — the book warns that Credit Risk Funds investing in sub-AAA paper carry issuer default risk.

#### 3.5.3 Modified Duration Score

Modified duration determines how much the fund's NAV will change for each 1% change in interest rates. A longer duration amplifies both gains and losses from rate moves.

The score penalizes a **mismatch** between the fund's stated category (which implies a duration band) and its actual duration:

| Debt Category | Expected Duration Band | Penalty if Outside Band |
|---|---|---|
| Overnight | < 0.1Y | −20 pts if > 0.5Y |
| Liquid | < 0.25Y | −15 pts if > 0.5Y |
| Ultra Short Duration | 0.25–0.5Y | −10 pts if outside ±50% |
| Low Duration | 0.5–1Y | −10 pts if outside ±50% |
| Short Duration | 1–3Y | −10 pts if outside ±50% |
| Medium Duration | 3–4Y | −10 pts if outside ±50% |
| Long Duration / Gilt | > 7Y | −5 pts if < 5Y (too conservative for category) |

Duration score (before mismatch penalty):
```
# Lower duration = lower interest rate risk = higher score (for shorter-duration categories)
# For short/medium/long duration: higher Macaulay duration within band is acceptable
duration_score = clamp((max_band − actual_duration) / (max_band − min_band), 0, 1) × 100
```

---

### 3.6 Manager Quality Score (0–100)

*New in v2. This is the most qualitative pillar but is grounded in quantifiable proxies.*

Measures **fund manager skill, consistency, and AMC governance quality**. The book dedicates significant attention to fund manager selection, warning about incentive conflicts, window dressing, closet indexing, and front-running (Axis MF case study).

#### 3.6.1 Sub-metrics

| Sub-metric | Weight | Formula / Source | Why it matters |
|---|---|---|---|
| Manager Tenure at Fund | 20% | `normalize(years_at_fund, low=0, high=8)` | Consistency; avoids post-manager-change performance attribution errors |
| Manager's Overall Alpha Track Record | 25% | `normalize(avg_alpha_across_all_funds, low=-2, high=5)` | Separates fund-level luck from manager skill |
| AMC Governance Score | 25% | See §3.6.2 | No amount of performance excuses front-running or regulatory violations |
| # of Funds Managed by Same Manager | 15% | `normalize(10 − num_funds_managed, low=0, high=9)` | A manager overseeing 15 funds cannot give adequate attention to each one |
| Closet Indexing Check (R²) | 15% | See §3.6.3 | Investors paying active management fees deserve active management |

**Total: 100%**

#### 3.6.2 AMC Governance Score

Based on a composite of:

- **SEBI regulatory actions**: Any SEBI order, penalty, or show-cause notice against the AMC in the last 5 years → −15 pts
- **Front-running / insider trading incidents**: Confirmed cases → −25 pts (effectively tanks this sub-metric)
- **AUM growth trend** (proxy for investor confidence): Consistent AUM growth over 3 years → positive signal
- **Disclosure quality**: Timely monthly factsheet publication, detailed portfolio disclosures → positive signal
- **No negative news / controversies**: Clean record → full marks

AMC Governance Score is scored 0–100 as a judgement-plus-data composite and is updated quarterly.

> **Design note**: This sub-metric intentionally has a qualitative component. The book is explicit that AMC reputation and fund manager ethics matter beyond numbers. A fund with excellent performance but a front-running scandal is a governance failure that should suppress its overall score.

#### 3.6.3 Closet Indexing Check

Funds that charge active fees but mirror the index waste investor capital. R² (R-squared) measures how much of a fund's return variance is explained by its benchmark:

```
if R² > 0.95 and fund is actively managed:
    closet_index_score = 0
elif R² > 0.85:
    closet_index_score = 30
elif R² > 0.75:
    closet_index_score = 60
elif R² > 0.60:
    closet_index_score = 85
else:
    closet_index_score = 100  # genuinely active, low benchmark dependence
```

The book warns: "R-Squared > 90%: Suggests a very close alignment with the benchmark. Consider an index fund that passively tracks the benchmark for potentially lower expense ratios."

#### 3.6.4 Manager Quality for Index Funds

For index/ETF funds, manager quality is mostly irrelevant (the algorithm decides). The sub-metrics reduce to:

| Sub-metric | Weight | Notes |
|---|---|---|
| AMC Governance | 60% | Still relevant — ETF providers can still have compliance failures |
| Tracking error trend | 40% | Has the fund been getting better or worse at tracking over time? |

---

### 3.7 Red Flag Penalties (0–20 pts maximum deduction)

Red flags are **subtractive** — they reduce the final composite score regardless of other pillar scores. The maximum penalty cap is raised from 15 to **20 pts** in v2.

| Red Flag | Penalty | Trigger Condition | Rationale |
|---|---|---|---|
| Missing benchmark | −3 pts | No benchmark mapped for the category | Can't measure excess return or downside capture |
| Very high expense ratio | −5 pts | ER > 2.5% equity; > 1.5% debt | Silent wealth destroyer; the book's chapter on expense ratio |
| Very low AUM | −3 pts | AUM < ₹100 Cr | Limited economies of scale; liquidity risk |
| Very high AUM (small cap only) | −4 pts | AUM > ₹20,000 Cr AND category is Small Cap | Fund becomes too large to exploit small-cap inefficiencies |
| Extreme concentration | −5 pts | Single holding > 50% of portfolio | Massive unsystematic risk; not diversification |
| Insufficient NAV history | −8 pts | < 1 year (252 trading days) of NAV data | Cannot compute meaningful risk metrics |
| No holdings data | −2 pts | Holdings data unavailable | Cannot score Composition pillar |
| Benchmark mismatch (low R²) | −3 pts | R² < 50% when benchmark is available AND not intentionally unconstrained | Benchmark comparison is meaningless |
| SEBI regulatory action | −8 pts | Any active SEBI penalty/order against the AMC | Governance failure; protects investors from compromised AMCs |
| Front-running / insider trading confirmed | −12 pts | Confirmed by SEBI/court order | Severe trust violation; nearly nullifies Manager Quality pillar |
| Very high turnover without IR justification | −3 pts | Turnover > 500% AND Information Ratio < 0 | Pure churn; destroys value for investors per book's analysis |
| Credit Risk Fund with < AA avg credit | −4 pts | Debt funds with weighted avg credit < AA | High default risk; appropriate for informed investors, not general recommendation |

Maximum total penalty is capped at **−20 points** (capped at the top of the deduction stack).

---

## 4. Confidence Levels

| Level | Badge | Conditions |
|---|---|---|
| **Fully Rated** | 🟢 Rated | 3Y+ NAV history; 3Y risk metrics; trailing returns (1Y, 3Y, 5Y); at least partial holdings; benchmark mapped; manager tenure available |
| **Rated (Partial)** | 🔵 Rated-P | All above except missing one minor data point (e.g., no 5Y return, or no sector data) |
| **Provisional** | 🟡 Provisional | Missing 3Y risk metrics OR no holdings data OR NAV < 3 years but > 1 year |
| **Unrated** | ⚪ Unrated | < 1 year NAV history, or multiple critical pillars cannot be computed (e.g., no returns AND no risk data) |

When a fund is `Provisional`, the missing pillar(s) are excluded and weights are redistributed proportionally across available pillars.

---

## 5. Score Interpretation Guide

| Score Range | Badge | Interpretation |
|---|---|---|
| 80–100 | 🟢 Outstanding | Best-in-class risk-adjusted profile; strong manager quality and governance |
| 65–79 | 🔵 Strong | Excellent fund with minor weaknesses; suitable for most investors |
| 50–64 | 🟣 Good | Solid fund with some tradeoffs; worthwhile with further due diligence |
| 35–49 | 🟡 Fair | Average profile — notable concerns in one or more areas |
| 20–34 | 🟠 Weak | Multiple weaknesses; close monitoring required before investing |
| 0–19 | 🔴 Poor | Significant structural, governance, or performance concerns |

> The thresholds are **not percentiles** — they represent absolute quality bands calibrated to Indian market data. A score of 75 means the fund is genuinely strong in most dimensions, not merely that 25% of funds score higher.

---

## 6. Special Handling: Category-Specific Rules

### 6.1 Index Funds and ETFs

Index funds are **not penalized** for:
- Low Information Ratio (they should have near-zero IR by design)
- High R² (they should be 0.99+ vs their benchmark)
- No Manager Quality signals (passive by construction)
- No excess return vs benchmark (that is the point of index investing)

Index funds **are** evaluated on:
- Tracking difference (how much they lag the index)
- Tracking error (how volatile that lag is)
- Expense ratio (primary differentiator between competing index funds)
- AUM / liquidity (important for ETF bid-ask spreads)

For ETF-specific scoring, **ETF liquidity premium** sub-metric is added:
```
etf_liquidity_score = normalize(avg_daily_volume_last_30d_in_cr, low=0, high=50)
```
A ₹50 Cr average daily traded volume scores 100; negligible volume scores 0.

### 6.2 ELSS Funds

ELSS funds are scored identically to equity active funds, but a **lock-in benefit note** is appended: the mandatory 3-year lock-in automatically encourages longer holding periods and means STCG taxation does not apply to the locked-in units.

### 6.3 Sectoral / Thematic Funds

- Sector HHI is **not penalized** (by design, these funds are concentrated in one sector)
- The Composition pillar weights are redistributed: Top-10 Concentration and Liquidity get higher weights
- A **mandatory note** is appended to the score: "High sector concentration by design; only suitable for investors with a clear thesis on [sector name]"

### 6.4 Small Cap Funds

- The AUM red flag threshold for small-cap funds is much stricter: AUM > ₹20,000 Cr triggers a −4 pt red flag (since a very large small-cap fund cannot invest in small caps without moving prices)
- Liquidity score is weighted more heavily in Composition (30% instead of 20%) for small-cap funds
- Downside Capture and Max Drawdown normalization ranges are wider (`low=-70, high=-10` for Max Drawdown) reflecting the historically higher volatility of the small-cap category

### 6.5 Flexi-Cap / Multi-Cap Funds

- The model checks if the fund's **actual allocation drift** is consistent with its stated mandate (e.g., a flexi-cap that always stays 90% large-cap is a de facto large-cap fund paying flexi-cap active fees)
- Allocation drift check: if rolling 12-month average large-cap allocation > 85% for a flexi-cap fund → closet indexing signal is flagged in Manager Quality

---

## 7. Category Rank

The fund's **Category Rank** is its percentile position among all peers in the same SEBI category that have been scored by this model. The rank is expressed as:

```
"#4 / 28 Large Cap Equity  |  Top 14%"
```

**Changes from v1:**
- Rank now shows **percentile** alongside absolute rank (e.g., "Top 14%") to be more meaningful when peer count varies
- Category peer count is displayed with a note if it differs significantly from the AMFI-registered universe
- Rank is recomputed on-demand and cached for **12 hours** (changed from 6 hours in v1 to reduce compute load)

**Limitation**: Only funds with sufficient data in the local database are ranked. The category peer count may differ from the full universe on Morningstar or Value Research.

---

## 8. Data Sources

| Data | Source | Update Frequency |
|---|---|---|
| NAV history | AMFI / mfapi.in | Daily |
| Trailing returns | Computed from NAV history | Daily |
| Risk metrics (Sharpe, Sortino, Drawdown, Beta, IR) | Computed from NAV history + benchmark | Daily |
| Expense ratio, AUM | captnemo.in / yahooquery / AMFI database | Monthly |
| Holdings, sectors, credit ratings | mstarpy / finapi.upvaly / yahooquery / CRISIL | Monthly |
| Benchmark series | Yahoo Finance / NSE / BSE / database | Daily |
| Fund manager data | AMC factsheets / SEBI filings | Monthly |
| AMC governance/regulatory actions | SEBI website / news monitoring | Quarterly |
| ETF trading volume | NSE/BSE APIs | Daily |

---

## 9. Important Limitations and Disclaimers

> **⚠️ THIS IS NOT INVESTMENT ADVICE.**

1. **Past performance does not guarantee future results.** All scoring is based on historical data.

2. **The model uses price index benchmarks**, not TRI (Total Return Index). TRI benchmarks are typically 1–2% higher annually. Excess return comparisons may slightly favour the fund vs SEBI-mandated TRI comparisons. This is a known limitation of public benchmark data availability.

3. **Scoring reflects a point-in-time snapshot.** Scores change as new NAV data, holdings updates, expense ratio changes, and manager changes are published.

4. **The model does not personalize for investor goals, risk tolerance, or time horizon.** A high-scoring fund may still be unsuitable for a specific investor. The book's asset allocation framework (§5.2) should guide which fund types are appropriate.

5. **Data gaps are common.** Holdings data, expense ratios, and benchmark mappings may be unavailable for some funds. Missing data reduces confidence level but does not fabricate a score.

6. **Manager Quality is partially qualitative** (AMC governance). The model's assessment of governance is based on publicly available information and may not capture private compliance failures.

7. **Category comparisons have limits.** A score of 70 in Small Cap Equity and 70 in Overnight Debt are not equivalent risk-adjusted comparisons — the categories have fundamentally different risk profiles.

8. **The Debt Quality pillar does not assess individual issuer credit analysis.** It relies on disclosed portfolio credit ratings, which may lag actual credit deterioration (as seen in the IL&FS and DHFL crises).

9. **This platform is for educational and informational purposes only.** Consult a SEBI-registered investment advisor before making investment decisions.

10. **The scoring weights and thresholds in this model are subjective design choices**, informed by financial literature, CRISIL/Morningstar methodology disclosures, SEBI regulations, and the source book, but **not empirically backtested for alpha prediction**.

---

## 10. Conceptual Framework: How Pillars Interact

Understanding why the six pillars exist together — and not in isolation — is essential for interpreting scores correctly.

### Why Performance alone is insufficient

A fund's 3Y CAGR is the most commonly cited metric, but it suffers from **period-selection bias**. A fund that performs brilliantly in 2020–2023 (a bull market) may look outstanding on trailing returns while having poor downside protection, high costs, and a portfolio that's been lucky rather than skilled. The book's Quant vs PPFAS case study illustrates this: Quant outperforms in rallies, PPFAS in corrections — neither is simply "better."

### Why Risk and Performance must be co-evaluated

The Sortino Ratio, Information Ratio, and Downside Capture together form the **risk-return contract**: they tell you whether the returns you're getting are being earned efficiently. A fund earning 15% with a Sortino of 3 is fundamentally different from one earning 15% with a Sortino of 0.5 — the first is a skilled manager; the second is a volatility machine.

### Why Cost is structural, not tactical

A 1% expense ratio difference compounds to a 26% gap in corpus over 30 years at 12% gross returns. Cost is the one certainty in investing. It penalizes your returns in bull markets, bear markets, and sideways markets equally.

### Why Manager Quality prevents "gaming" the other pillars

Without a Manager Quality pillar, a fund with an exceptional 3-year period (due to macro luck or concentrated bets) could score well despite poor governance or a manager who has just joined. The manager consistency and AMC governance checks anchor the score in long-term institutional quality — the factor that separates durable outperformers (HDFC Flexi Cap, Parag Parikh Flexi Cap) from flash funds.

### Why Debt Quality replaces Composition for debt funds

A debt fund's portfolio structure is fundamentally different from equities. The concentration of risk in debt is in **issuer credit quality and duration mismatch**, not sector or stock diversification. The Franklin Templeton 2020 event was not a composition failure — it was a credit quality and liquidity failure. The Debt Quality pillar captures this.

---

## 11. Model Version History

| Version | Date | Summary |
|---|---|---|
| v1.0 | 2026-05-28 | Initial release: 5-pillar model, category rank, confidence levels |
| v2.0 | 2026-06-25 | Added Manager Quality pillar; added Debt Quality pillar; added Information Ratio, Portfolio Liquidity, Portfolio Turnover sub-metrics; category-aware weight tables; AMC governance scoring; updated red flag penalties; improved normalization bounds |

---

*For questions or model improvements, see the project's GitHub repository.*

after which we will test for some funds and re run migrations/population/ingestion whatever required for consistency and accuracy and thus updating data completely, also update markdown and readme accordingly  and thus having complete updated project
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-06-26T00:19:30+05:30.
</ADDITIONAL_METADATA>
<USER_SETTINGS_CHANGE>
The user changed setting `Model Selection` from None to Gemini 3.1 Pro (High). No need to comment on this change if the user doesn't ask about it. If reporting what model you are, please use a human readable name instead of the exact string.
</USER_SETTINGS_CHANGE>