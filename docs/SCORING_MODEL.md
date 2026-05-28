# MF Analysis Platform — Fund Scoring Model (v1)

> **Last updated:** 2026-05-28  
> **Model version:** 1.0  
> **Status:** Production (v1)

---

## 1. Overview

The Fund Scoring Model is a **category-normalized, multi-factor quantitative framework** that evaluates mutual funds across five independent pillars and produces a single composite score (0–100). The model is designed to reflect risk-adjusted value, not raw past performance.

### Core Design Principles

1. **Category-first**: All scoring is relative to the fund's SEBI category peer group (e.g., Large Cap Equity, Short Duration Debt). Equity funds are never compared directly to debt funds.
2. **No single-factor dominance**: No single metric (not even trailing returns) can dominate the score. Return quality, downside control, cost discipline, and portfolio construction all matter.
3. **Transparent fallbacks**: When data is missing, the system reduces confidence level rather than fabricating a score. Each pillar may be rated, provisional, or skipped.
4. **Not a prediction**: The score reflects historical and current data quality. It is **not** a forecast of future returns.

---

## 2. Score Structure

```
Final Score = 0.30 × Performance
            + 0.28 × Risk
            + 0.12 × Cost
            + 0.15 × Composition
            − Red Flag Penalty   (max 15 pts)

Clamped to [0, 100]
```

| Pillar | Weight | Description |
|---|---|---|
| **Performance** | 30% | Return quality over multiple timeframes |
| **Risk / Stability** | 28% | Downside control and volatility-adjusted returns |
| **Cost** | 12% | Total cost efficiency vs category norms |
| **Composition** | 15% | Portfolio construction quality |
| **Red Flags** | −15% max penalty | Structural or data-quality concerns |

---

## 3. Pillar Definitions

### 3.1 Performance Score (0–100)

Measures the **quality and consistency of returns** across time horizons.

| Sub-metric | Weight | Formula |
|---|---|---|
| 3Y trailing CAGR | 40% | `normalize(cagr_3y, low=0, high=20)` |
| 1Y trailing CAGR | 20% | `normalize(cagr_1y, low=-5, high=30)` |
| 5Y trailing CAGR | 20% | `normalize(cagr_5y, low=0, high=18)` |
| 3Y Rolling Win Rate (>0%) | 10% | Direct `win_rate_0 / 100` |
| Excess return vs benchmark | 10% | `normalize(excess_3y, low=-5, high=8)` |

**Normalization formula:**
```
score = clamp((value - low) / (high - low), 0, 1) × 100
```

**Fallback cascade:**
- If 3Y CAGR missing → substitute 5Y or 1Y, reduce weight
- If all trailing missing → pillar is `UNRATED`
- If benchmark missing → excess return sub-score = 0 (not penalized)

**What this means for investors:** A fund that consistently delivers positive returns across all rolling windows, beats its benchmark over 3 years, and has strong 5-year CAGR will score well here. A fund with one exceptional year but poor long-term history will score lower.

---

### 3.2 Risk / Stability Score (0–100)

Measures **downside control, not just volatility**.

| Sub-metric | Weight | Formula / Thresholds |
|---|---|---|
| Sortino Ratio (3Y) | 30% | `normalize(sortino, low=0, high=2.5)` |
| Max Drawdown (3Y) | 30% | `normalize(-drawdown, low=-50, high=-5)` |
| Downside Capture Ratio (3Y) | 25% | `normalize(100 - downside_capture, low=-30, high=30)` |
| Sharpe Ratio (3Y) | 15% | `normalize(sharpe, low=0, high=2.0)` |

**Notes:**
- Max Drawdown: Lower drawdown (closer to 0%) = higher score. A fund with −10% max drawdown scores better than one with −40%.
- Downside Capture: 80% downside capture = fund fell only 80% as much as the market on bad days. Lower is better.
- Sortino specifically penalizes downside volatility, not upside. A fund that swings wildly upward but falls sharply downward will score poorly here.

**Fallback cascade:**
- If 3Y risk missing → try 5Y risk metrics
- If neither → pillar is `PROVISIONAL` (no penalty, just lower confidence)

---

### 3.3 Cost Score (0–100)

Measures **total cost efficiency** relative to category norms.

| Sub-metric | Weight | Thresholds |
|---|---|---|
| Expense Ratio vs category benchmark | 70% | See table below |
| AUM size factor | 30% | AUM > ₹5,000 Cr = 100, < ₹100 Cr = 20 |

**Expense ratio thresholds by category type:**

| Category Type | Excellent (<) | Good (<) | Average (<) | Poor (≥) |
|---|---|---|---|---|
| Equity – Direct | 0.30% | 0.60% | 1.00% | 1.50% |
| Equity – Regular | 0.80% | 1.20% | 1.75% | 2.25% |
| Index / ETF – Direct | 0.05% | 0.15% | 0.30% | 0.50% |
| Debt – Direct | 0.20% | 0.40% | 0.70% | 1.00% |
| Debt – Regular | 0.50% | 0.80% | 1.20% | 1.50% |
| Hybrid – Direct | 0.40% | 0.70% | 1.10% | 1.60% |
| Default | 0.50% | 1.00% | 1.50% | 2.00% |

**AUM context:** A fund with very low AUM (<₹100 Cr) has limited economies of scale and may have illiquidity risk. Very large AUM (>₹5,000 Cr) indicates scale, though it may constrain flexibility in small-cap funds.

**Fallback:** If expense ratio is missing → pillar is `PROVISIONAL`. AUM sub-score is computed independently.

---

### 3.4 Composition Score (0–100)

Measures **portfolio construction quality**: diversification, concentration risk, and holdings discipline.

| Sub-metric | Weight | Thresholds |
|---|---|---|
| Top-10 concentration | 40% | <40% = 100, >90% = 0 |
| Total holdings count | 30% | >50 holdings = 100, 1–5 = 10 |
| Sector concentration (HHI) | 30% | Low HHI = high score |

**Top-10 Concentration:**
```
score = clamp((90 - top10_weight) / (90 - 40), 0, 1) × 100
```
A fund with Top-10 weight of 40% scores 100; one with 90%+ scores 0.

**Sector HHI (Herfindahl-Hirschman Index):**
```
HHI = Σ(sector_weight_i²)
HHI score = clamp(1 - HHI / 0.5, 0, 1) × 100
```
Low HHI = well diversified across sectors = higher score.

**Holdings Count:**
```
score = clamp((count - 5) / (50 - 5), 0, 1) × 100
```

**Fallback:** If no holdings data → pillar is `UNRATED`. This is noted explicitly with reason.

---

### 3.5 Red Flag Penalties (0–15 pts maximum deduction)

Red flags are **subtractive** — they reduce the final composite score regardless of other pillar scores. A fund can score well on all pillars but still be downgraded due to structural concerns.

| Red Flag | Penalty | Trigger Condition |
|---|---|---|
| Missing benchmark | −3 pts | No benchmark mapped for the category |
| Very high expense ratio | −5 pts | ER > 2.5% for equity, > 1.5% for debt |
| Very low AUM | −3 pts | AUM < ₹100 Cr |
| Extreme concentration | −5 pts | Single holding > 50% of portfolio |
| Insufficient NAV history | −8 pts | < 1 year (252 trading days) of NAV data |
| No holdings data | −2 pts | Holdings data not available from any source |
| Benchmark mismatch (low R²) | −3 pts | R² < 50% when benchmark is available |

Maximum total penalty is capped at **−15 points**.

---

## 4. Confidence Levels

| Level | Badge | Conditions |
|---|---|---|
| **Rated** | 🟢 Rated | 3Y risk metrics available + trailing returns + at least partial holdings data |
| **Provisional** | 🟡 Provisional | Some data missing (e.g., no 3Y risk, no holdings, or < 3Y NAV history) |
| **Unrated** | ⚪ Unrated | < 1 year NAV history, or multiple critical pillars cannot be computed |

When a fund is `Provisional`, the missing pillar scores are excluded from the weighted average. Weights are redistributed proportionally across available pillars.

---

## 5. Score Interpretation Guide

| Score Range | Badge | Interpretation |
|---|---|---|
| 75–100 | 🟢 Strong | Excellent risk-adjusted profile across most dimensions |
| 55–74 | 🔵 Good | Solid fund with minor weaknesses |
| 40–54 | 🟡 Fair | Average profile — some concerns worth investigating |
| 25–39 | 🟠 Weak | Notable weaknesses in multiple areas |
| 0–24 | 🔴 Poor | Significant structural or performance concerns |

---

## 6. Category Rank

The fund's **Category Rank** is its position among all peers in the same SEBI category that have been scored by this model. For example, "#4 / 28 Large Cap Equity" means the fund is the 4th highest scorer among 28 scored large-cap equity funds in the database.

**Limitations:**
- Only funds with sufficient data in the local database are ranked
- Category peer count may differ from the total universe on platforms like Morningstar or Value Research
- Rank is recomputed on-demand and cached for 6 hours

---

## 7. Data Sources

| Data | Source |
|---|---|
| NAV history | AMFI / mfapi.in |
| Trailing returns | Computed from NAV history |
| Risk metrics | Computed from NAV history (with benchmark) |
| Expense ratio, AUM | captnemo.in / yahooquery / database |
| Holdings, sectors | mstarpy / finapi.upvaly / yahooquery |
| Benchmark series | Yahoo Finance / database |

---

## 8. Important Limitations and Disclaimers

> **⚠️ THIS IS NOT INVESTMENT ADVICE.**

1. **Past performance does not guarantee future results.** All scoring is based on historical data. Markets are inherently unpredictable.

2. **The model uses price index benchmarks**, not TRI (Total Return Index). TRI benchmarks are typically 1–2% higher annually. This means our benchmark comparisons may slightly favour the fund vs official SEBI-mandated comparisons.

3. **Scoring reflects a point-in-time snapshot.** Scores change as new NAV data, holdings updates, and expense ratio changes are published.

4. **The model does not personalize for investor goals, risk tolerance, or time horizon.** A high-scoring fund may still be unsuitable for a specific investor's needs.

5. **Data gaps are common.** Holdings data, expense ratios, and benchmark mappings may be unavailable for some funds. Missing data reduces confidence level but does not fabricate a score.

6. **This platform is for educational and informational purposes only.** Consult a SEBI-registered financial advisor before making investment decisions.

7. **The scoring weights and thresholds in this model are subjective design choices**, informed by financial literature and standard practice, but not empirically backtested for alpha prediction.

---

## 9. Model Version History

| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-05-28 | Initial release: 5-pillar model, category rank, confidence levels |

---

*For questions or model improvements, see the project's GitHub repository.*
