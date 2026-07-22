Let me fetch all those sources first to extract the actual metrics and frameworks they use.Now the UnlistedZone report:Now I have everything I need. Let me synthesize all four sources into a comprehensive research analyst's framework.

---

# AMC Analysis & Comparison: The Complete Research Framework

> [!NOTE]
> **Implementation Status:** Fully implemented into production! Accessible via the sidebar under **Research → AMC Analysis**.
> - **AMC Directory & Screener:** [`/research/amcs/`](file:///c:/Users/amans/OneDrive/Documents/GitHub/MutualFundAnalysis/templates/research/amcs.html) — Searchable grid with AUM, fund count, returns, TER, scores & multi-select compare bar.
> - **AMC Detail Deep-Dive:** [`/research/amcs/<slug>/`](file:///c:/Users/amans/OneDrive/Documents/GitHub/MutualFundAnalysis/templates/research/amc_detail.html) — 8-pillar analysis across 5 tabs (All Funds, Portfolio Intel, Philosophy, Fund Managers, Categories).
> - **Side-by-Side AMC Comparison:** [`/research/amcs/compare/`](file:///c:/Users/amans/OneDrive/Documents/GitHub/MutualFundAnalysis/templates/research/amc_compare.html) — 26-metric matrix comparing 2–4 AMCs across 7 dimensions with winner badges (★ Best).

There are two distinct questions here: **"Is this AMC worth investing in as a business?"** (AMC-as-stock analysis) and **"Is this AMC worth investing *through*?"** (AMC-as-fund-manager analysis). A proper analyst does both simultaneously, because the quality of the firm and the quality of its investment decisions are deeply linked. Here's the full framework.

---

## Pillar 1: AUM — Scale, Growth & Composition

This is the first thing any analyst looks at because **AUM is the revenue engine** of an AMC. Sources: Morningstar's AMC AUM tool, AMFI disclosures.

**Total AUM & Market Share**
The absolute size of AUM determines revenue through expense ratios — every rupee managed is a fee-generating asset. More important is *market share trend*: is an AMC gaining or losing share of the industry's total AUM? The Morningstar AUM tool shows quarter-end average AUM for every registered AMC alongside absolute and percentage change between any two quarters. As of March 2026, SBI is the largest at ₹12.7 lakh Cr, followed by ICICI Prudential at ₹11.7 lakh Cr, HDFC at ₹9.5 lakh Cr, and Nippon at ₹7.4 lakh Cr. An AMC with a declining AUM share even in a rising market means it's losing the competitive race.

**3-Year AUM CAGR**
More revealing than a single quarter snapshot. HDFC AMC posted 28.22% 3-year AUM growth; UTI AMC led at 35.58%; Nippon was at 22.96%, and PPFAS at 25.57%. For a researcher, the question is: is the growth being driven by market appreciation (rising NAVs lifting AUM passively), net new inflows, or new fund launches? Only net inflow data separates genuine investor confidence from market-driven AUM inflation.

**QoQ AUM Change: Signal vs. Noise**
Morningstar's tool lets you compare any two quarters — for instance, Zerodha AMC grew 44.93% from Dec 2025 to Mar 2026, Helios grew 26.95%, while Quant fell 8.07% and JM Financial fell 7.84%. A single-quarter drop doesn't mean much — it could be market decline or normal redemptions. But sustained quarter-on-quarter outflows, especially when the overall market is up, signal investor dissatisfaction, fund performance issues, or distribution weakness.

**Per-Fund AUM Distribution**
The per-AMC fund-wise view on Morningstar shows AUM change at the individual scheme level. This is critical because an AMC's headline AUM can mask heavily concentrated risk — one blockbuster fund (e.g., PPFAS Flexi Cap holding >80% of the AMC's AUM) creates key-man and concentration risk. Ideally, you want AUM spread across multiple successful schemes and categories.

**Active vs. Passive AUM Split**
For SBI MF, the data shows 36 actively managed equity funds vs 30 index/ETF funds. The active/passive mix tells you the AMC's philosophy and future margin trajectory — passive funds earn significantly lower expense ratios (~0.1–0.3% vs 0.5–1.5% for active), so an AMC rapidly shifting to passive is compressing its own revenue per rupee managed. Conversely, AMCs with high passive share are more defensible against market downturns because passive inflows continue even when active funds underperform.

---

## Pillar 2: Financials & Business Profitability
*(Most relevant when the AMC is listed or pre-IPO)*

**Revenue = AUM × Effective TER (Total Expense Ratio)**
AMC revenue is essentially: average AUM × blended expense ratio across all schemes. When comparing two AMCs of similar AUM, the one with a higher equity-oriented, active-fund mix will earn more per rupee managed. The blended yield on AUM (Revenue ÷ Avg AUM) is the key operating metric.

**PAT Margin**
HDFC AMC had a PAT margin of 60.77% on revenue of ₹4,050 Cr; Nippon was at 56.6%; UTI AMC at 41.3%; PPFAS at 57.3%; and SBI MF (FY24) at 63.04%. The AMC business is capital-light and highly scalable — once the fixed cost base (fund management team, tech, compliance) is covered, incremental AUM flows straight to profit. UTI's lower margins despite high AUM growth point to internal inefficiencies — high fixed costs, legacy infrastructure, or distribution expense.

**Operating Leverage**
As AUM grows, incremental revenue is nearly all margin. Track: does profit grow faster than revenue? If PAT margin is expanding over 3–5 years, the AMC is realizing operating leverage. If it's flat or contracting despite AUM growth, it's either spending aggressively on distribution/tech (could be justified) or has cost control issues.

**Valuation Multiples**
The key multiples for AMC comparison are P/E ratio and Mcap/AUM. HDFC AMC traded at 43.8× P/E with Mcap/AUM of 14.32; Nippon at 39.6× and 9.08; UTI at 22.6× and 4.86; SBI MF (unlisted) at 67.17× and 20.63. The **Mcap/AUM ratio** is the most sector-specific valuation metric — it tells you how much the market is willing to pay for each rupee of assets managed. A lower ratio could indicate undervaluation or structural weakness (poor fund performance, high debt AUM, or regulatory risk). Compare this multiple to the AMC's own history (has it re-rated?) and to peers.

---

## Pillar 3: Portfolio Intelligence — The Heart of AMC Analysis

This is where RightAdvise-style analysis becomes uniquely powerful. It tells you **what the fund managers actually *believe*** as expressed through their equity holdings.

**High Conviction Stocks (Held in 5+ Funds)**
Stocks held across multiple funds simultaneously signal a shared high-conviction view among multiple fund managers within the AMC. For SBI MF, ICICI Bank is the most widely held stock, present in 24 active funds with a combined value of ₹25,961 Cr; HDFC Bank is in 20 funds, and Infosys in 20 funds. This is **cross-fund consensus**, not just one manager's bet. When comparing two AMCs, compare their high-conviction lists — do they overlap heavily (both are closet index trackers) or do they express genuinely different views?

**Dominant Sector Exposure**
For SBI MF, Banks dominate at 17.9% average allocation across 27 funds, followed by Pharma at 8.2% across 28 funds, Automobiles at 6.8%, Finance at 6.5%, and Power at 6.2%. This is the AMC's *revealed preference* — the sectors its fund managers collectively believe in, independent of what any single fund's mandate says. When comparing AMCs, different sector tilts reflect different macro views and investment philosophies.

**Fresh Entries 🟢 — Leading Indicator of New Conviction**
Between May and June 2026, SBI MF's active equity funds made 10 fresh stock entries, including JSW Infrastructure (entering 8 funds simultaneously with ₹1,722 Cr combined value) and Acme Solar Holdings (entering 7 funds with ₹698 Cr). Fresh entries *across many funds simultaneously* are the strongest conviction signal — it means multiple independent fund managers independently decided to buy the same new stock. Track this monthly: is the AMC discovering new ideas or recycling old ones?

**Complete Exits 🔴 — Conviction Reversals**
In the same period, SBI MF completely exited 5 stocks, including Escorts Kubota (from 2 funds) and Nazara Technologies (from 1 fund). Complete exits tell you what the AMC is *done with* — useful for stock-level analysis (if 5 different AMCs all exit a stock in the same month, that's a red flag for the stock). For AMC comparison, an AMC with many exits and few entries is in defensive mode; vice versa signals aggression.

**Adding 📈 vs. Reducing 📉 — Portfolio Momentum**
SBI MF had 186 adding positions and 179 reducing positions in June 2026. The ratio of adds to reductions is a directional signal — a bullish AMC adds more than it reduces. More granularly, track *which specific stocks* are being added across many funds: that's where the AMC's forward conviction is concentrated. Weight changes by fund count and absolute value matter — a stock added by 15 funds simultaneously and with high average weight increase is a very different signal from one added by a single fund.

---

## Pillar 4: Fund-Level Performance Metrics

Source: Value Research per-AMC fund selector with tabs for Returns, Risk, Portfolio, Fees.

**Category Breadth and Depth**
How many SEBI categories does the AMC operate in, and does it have credible offerings in each? A serious AMC should have fund solutions across equity (large/mid/small/flexi/ELSS), debt (liquid/ultra-short/short/medium/gilt), and hybrid categories. An AMC that only operates in 3–4 categories is either boutique (PPFAS), still maturing (new entrants like Helios, Jio BlackRock), or has pulled back from underperforming categories.

**Star Rating Distribution**
Value Research and Morningstar both assign 1–5 star ratings based on risk-adjusted returns within category. At the AMC level, count: what % of the AMC's funds are 4- or 5-star rated? An AMC with 60% of funds in the top two star categories has demonstrated consistent cross-category quality. An AMC with a few star performers and many 1–2 star funds is a "barbell" — select a few, ignore the rest.

**Category-Level Alpha Generation**
For each SEBI category the AMC participates in, compare the fund's return to both its benchmark and its category median. An AMC that consistently beats category median across multiple categories has *organizational alpha* — it's not just one lucky manager but a systemic process advantage.

**Expense Ratios — Direct vs. Regular**
Value Research's Fees & Details tab shows expense ratios for direct and regular plans per fund. Compare the AMC's expense ratios against category peers. An AMC charging above-category-average TER while delivering below-average returns is a structural value destroyer. For the same performance, lower TER = better for investors and signals AMC confidence that their returns justify the fee without inflating it.

---

## Pillar 5: Investment Philosophy & Process Quality

**Philosophy Consistency**
Does the AMC's stated philosophy (growth/value/quality/momentum/quantitative) actually show up in the portfolio? If an AMC claims to be a "quality at reasonable price" investor but its portfolios show high-beta, high-turnover stocks, there's a philosophy-execution gap. This is analyzed by looking at the portfolio's average P/B, ROE, debt-to-equity of holdings, and turnover ratio.

**Stock Universe Breadth**
SBI MF holds 402 unique stocks across its active funds. A large stock universe is expected for a large AMC. But for smaller or boutique AMCs, a wide stock universe with small positions everywhere signals indecision or closet diversification — not genuine stock picking.

**Intra-AMC Fund Overlap**
How much do the portfolios of different funds within the same AMC overlap with each other? If the Large Cap fund and the Flexi Cap fund hold 85% of the same stocks, there's no genuine differentiation — an investor holding both funds gets near-zero incremental diversification. Compute pairwise overlap matrices across same-AMC funds to assess genuine distinctness.

**Turnover Ratio**
High portfolio turnover (>100% annually) across multiple funds of an AMC indicates either active tactical trading or frequent conviction changes — both increase cost and tax drag. An AMC known for high turnover is not suitable for a passive, long-horizon investor even via its equity funds.

---

## Pillar 6: People — The Fund Manager Framework

**Manager Tenure Distribution**
What is the average and median tenure of fund managers at the AMC? High manager turnover is a structural red flag because performance track records may not be attributable to current managers. Some AMCs (like HDFC, PPFAS) have very stable manager teams; others have seen serial exits.

**Single-Manager Concentration (Key-Man Risk)**
Does one or two managers run the majority of the AMC's AUM? PPFAS is described as having a "cult brand" with deep loyalty to its fund management philosophy. While this builds brand, it also concentrates key-man risk — if the star manager leaves, AUM outflows can be severe (as happened with several AMCs post high-profile departures). Compare how AUM behaved at AMCs after notable manager exits.

**Research Team Quality**
A large, experienced research team is the foundation of alpha generation in equity funds. The number of analysts, their qualifications, average experience, and whether the AMC grows analysts internally vs. poaches externally are all qualitative signals of process robustness.

---

## Pillar 7: Distribution, Brand & Flows

**Regular vs. Direct AUM Split**
An AMC with high direct plan AUM (investors bypassing distributors) indicates strong brand pull and digitally sophisticated investor base. An AMC overwhelmingly dependent on regular plan distribution is vulnerable to distributor conflicts and may face margin pressure as the industry shifts toward direct.

**Monthly SIP Book**
The SIP book is the most *resilient* form of AUM because SIPs continue even during market downturns — investors don't actively pull them out the way they would lumpsum investments. An AMC with a large SIP book has predictable, recurring inflows. Monthly SIP flows across the industry have exceeded ₹20,000 Cr, and AMCs with large retail SIP bases are structurally more stable. Track each AMC's reported SIP book as a % of total AUM.

**Geographic Reach (B30 AUM)**
SEBI tracks AUM from B30 cities (Beyond Top 30 cities) separately and provides incentives for AMCs to grow there. An AMC with a high and growing B30 share is reaching the next wave of investors and building a more diverse, less volatile AUM base. Tier 2 and 3 investor surge powered by UPI and digital onboarding is a key growth trigger for AMCs.

**Distributor Relationships vs. Digital First**
Nippon AMC is characterized as "digital-first and retail-heavy" and Jio BlackRock is pursuing an "ultra-low-cost, digital-first" model targeting millennials and Tier 2+ cities. AMCs with strong distributor lock-in (bancassurance, IFA networks) have stickier AUM but face margin pressure from distributor commissions. Digital-first AMCs have lower distribution costs but need stronger brand pull to compensate.

---

## Pillar 8: Regulatory, Risk & Governance

**SEBI Compliance History**
Any show-cause notices, enforcement actions, front-running allegations, or NAV manipulation cases are immediate red flags. The Franklin Templeton debt crisis (2020) and Axis AMC front-running investigations are case studies in how regulatory and governance failures devastate AUM overnight.

**Credit Risk Exposure (Debt Funds)**
For AMCs with significant debt fund AUM, the credit quality of the fixed income portfolio is a systemic risk. An AMC that chased yield by loading up on low-rated paper (sub-AA bonds) is vulnerable to a credit event destroying NAV and triggering mass redemptions.

**Industry-Level Risks**
The key risks for AMCs as a business include market cyclicality (equity-heavy AMCs face pressure in downturns), fee compression from ETFs and SEBI expense caps, distribution disruption from fintechs, fund manager key-man dependency, and regulatory headwinds from SEBI's tightening of classifications.

---

## AMC Comparison Template: Putting It Together

When you are comparing two or more AMCs side by side, organize the comparison across these seven columns and let the data speak:

| Dimension | Metric | AMC A | AMC B | AMC C | Winner Signal |
|---|---|---|---|---|---|
| **Scale** | Total AUM | — | — | — | Larger = more stable revenue |
| **Growth** | 3Y AUM CAGR | — | — | — | Higher + quality inflows |
| **Profitability** | PAT Margin | — | — | — | Higher = more efficient |
| **Valuation** | Mcap/AUM, P/E | — | — | — | Context-dependent |
| **Fund Quality** | % 4-5★ funds | — | — | — | Higher = consistent delivery |
| **Conviction** | High-conviction stocks, Fresh entries | — | — | — | Unique, not consensus |
| **Costs** | Avg TER (direct) | — | — | — | Lower = investor-friendly |
| **People** | Avg manager tenure | — | — | — | Higher = stability |
| **Philosophy** | Turnover ratio, Active share | — | — | — | Consistent with stated style |
| **Flows** | Net SIP book, Direct % | — | — | — | Growing SIP + high direct |
| **Governance** | SEBI actions, credit events | — | — | — | Clean record = prerequisite |

The **analyst's synthesis** is not just who wins the most columns but *which dimensions matter most for the purpose of the analysis*. If you're evaluating an AMC as a stock investment, Pillars 1–3 and 8 dominate. If you're evaluating it as a place to park your money through its funds, Pillars 3–7 dominate. If you're building an AMC research platform (which you are), all eight pillars are data points worth tracking and displaying.