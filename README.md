# Mutual Fund Analysis and Advisory Platform

An India-focused, research-stage project for designing a mutual fund analysis
application that can help an investor understand funds, compare alternatives,
evaluate an existing portfolio, and eventually receive transparent,
data-supported guidance aligned with their risk profile and goals.

> **Project status:** This repository contains a fully functional Django web application implementing Phase 1 and Phase 2 of the Mutual Fund Analysis platform. It includes real-time fund screening, performance analytics, PDF reporting, and portfolio calculators.
>
> **Important disclaimer:** Mutual fund investments are subject to market
> risk. Material in this repository is for research and educational use only;
> it is not financial, legal, or tax advice and does not guarantee returns.
> Any future recommendation feature must clearly expose its assumptions,
> limitations, source data, and the need for qualified professional advice
> where appropriate.

## Contents

- [Vision](#vision)
- [Current Project State](#current-project-state)
- [Proposed Product Experience](#proposed-product-experience)
- [Analysis Framework](#analysis-framework)
- [Ideas Incorporated From the Tejas Performance Study](#ideas-incorporated-from-the-tejas-performance-study)
- [Portfolio Analysis and Backtesting](#portfolio-analysis-and-backtesting)
- [Data Sources and Feasibility](#data-sources-and-feasibility)
- [Technology Direction](#technology-direction)
- [Implementation Roadmap](#implementation-roadmap)
- [Project Structure](#project-structure)
- [Research References](#research-references)

## Vision

The long-term goal is a full-stack, open-source mutual fund research and
portfolio intelligence application. It should turn fragmented fund, benchmark,
portfolio, and investor-input data into clear analysis while remaining honest
about uncertainty and investment risk.

The planned platform has five primary capabilities:

1. **Mutual fund research:** Present a complete, understandable profile of a
   scheme, including performance, risk, costs, holdings, management, and
   benchmark context.
2. **Comparison and discovery tools:** Let users screen, rank, and compare
   funds using consistent metrics rather than choosing only from past returns.
3. **Calculators:** Support practical decisions using SIP, lump-sum, XIRR,
   rolling-return, STP, SWP, tax, goal, and portfolio-overlap calculations.
4. **Portfolio analysis:** Ingest transactions or holdings, assess actual
   investor outcomes and diversification, compare against benchmarks, and
   identify issues that deserve review.
5. **Personalized guidance:** Eventually use a questionnaire and explainable
   analytics, potentially assisted by AI, to present suitable fund categories
   or portfolio changes with clear rationale and safeguards.

## Current Project State

This project has successfully transitioned from a design workspace into a functional, data-driven web application built with Django, HTMX, and Pandas.

**Core Features Implemented:**
- **On-Demand Runtime Data Architecture:** Keeps only lightweight scheme data locally, then fetches NAV, metadata, holdings, sectors, and allocations on demand from AMFI, `mfapi.in`, `captnemo`, `mstarpy`, `yahooquery`, and `yfinance`.
- **Advanced Analytics Engine:** Uses vectorized Pandas operations to calculate Rolling Returns (with win rates, medians, and outperformance), Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, and Trailing Returns dynamically.
- **Year-wise Fund vs Benchmark Breakdown:** Risk and performance are now sliced by calendar year, comparing fund outcomes directly with their respective benchmarks.
- **Screener & Fund Compare:** Real-time HTMX-powered screening and side-by-side comparison.
- **PDF Reports:** 1-click export of beautifully formatted fund fact sheets.

### Known Limitations & Future Roadmap
Due to the constraints of relying on public unauthenticated APIs and on-demand data fetching, the following features are **intentionally deferred** to a future phase:

- **Category Average Comparisons** — No unified database of historical category averages yet; fund-vs-peer comparisons require a scheduled ingestion pipeline.
- **Fund Screener** — The screener module has been removed in the current version; a rebuilt screener with proper pre-computed metrics is planned.
- **Peer Finding and Comparison** — Cross-fund peer ranking relies on having pre-computed metrics for all funds in a category.
- **Data-based Relative Fund Ranking** — A rules-based model combining returns, risk, cost, and consistency requires a full category dataset.
- **Individual Stock Holding Analysis** — Deep-dive analysis of each underlying stock (P/E, growth, etc.) is not yet integrated.
- **Holdings Change Over Time** — Tracking how a fund's portfolio composition changes quarter-over-quarter is deferred.
- **Portfolio Overlap Analysis** — Identifying common holdings between two funds requires bulk holdings data for all funds simultaneously.
- **AI/ML-Assisted Fund Selection** — Explainable AI guidance is planned only after the deterministic metrics are fully validated.
- **Total Return Index (TRI) Benchmarks** — Index history currently fetches price data only, not TRI (which includes dividends and is ~1–2% higher annually). SEBI mandates TRI for official benchmark comparison.

For a deep-dive into the technical architecture, data flow, and code structure, please read the newly added **[`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md)**.

The legacy research artifacts that guided this implementation remain in the `docs/` and `scripts/` folders for reference.

## Proposed Product Experience

### Fund Research

A fund page should make it possible to evaluate a scheme without switching
between many sources. It is expected to include:

| Area | Information and analysis to present |
| --- | --- |
| Identity and classification | Scheme name, AMC, objective, inception date, open/closed/interval structure, direct or regular plan, growth or IDCW option, active or passive style, domestic or international exposure, and equity/debt/hybrid/subcategory classification. |
| Fund information | NAV history, AUM and AUM growth, expense ratio, exit load, stamp duty, lock-in, minimum SIP and lump-sum amounts, tax treatment, benchmark, fund-house information, and applicable scheme documents. |
| Fund managers | Manager name, joining date, background, experience, other managed funds, assets managed, and performance during tenure where data is available. |
| Returns | Trailing returns, calendar-year returns, SIP and lump-sum outcomes, XIRR where cash flows exist, rolling-return distributions, and comparisons with benchmark, category average, and peers. |
| Risk | Standard deviation, beta, alpha, Sharpe, Sortino, R-squared, information ratio, maximum drawdown, downside/upside capture, downside-period behavior, and volatility context. |
| Portfolio composition | Equity/debt/cash allocation, market-cap and geographic allocation, sectors and industries, number of securities, top holdings, concentration, turnover, and portfolio changes over time. |
| Decision support | Transparent status commentary such as on track or off track, identified red flags, data freshness, and the reasoning for any ranking or suggestion. |

A future ranking approach is envisioned around return consistency, recent
performance, stability during downturns, cost, risk, composition, and red
flags. A personal risk profile may affect how a ranking is displayed, but it
must never hide the underlying measurements or imply guaranteed results.

### Discovery, Screening, and Comparison

The discovery area should support category browsing and flexible screening by
fund type, AUM, age, expense ratio, exit load, horizon, plan type, returns,
alpha, SIP performance, volatility, beta, risk-adjusted measures, capture
ratios, manager record, holdings, sector diversification, and rating inputs.

Comparison should address more than a simple returns table:

- Return comparisons should cover trailing, rolling, annual, quarterly,
  lump-sum, and SIP outcomes against the correct benchmark and category.
- Risk comparisons should include volatility, drawdown, capture ratios,
  benchmark-relative underperformance in difficult periods, and
  risk-adjusted return measures.
- Portfolio comparisons should show allocations, sector exposures, top-holding
  concentration, turnover, overlap, domestic/overseas allocation, and changes
  over time.
- Scheme comparisons should include expense ratio, loads, minimum investments,
  lock-in, taxation, AUM, objective, manager, launch date, and fund-house
  context.

### Calculators and Tools

The design notes identify a wide calculator surface: trailing and annual
returns, rolling returns, quartile and downside-volatility rankings, category
and benchmark monitoring, PPF versus ELSS, SIP and step-up SIP, STP, SWP,
liquid fund versus savings account, dividend/history comparisons, fund
selection, overlap, risk ratios, ELSS, goals, investment amount, taxation,
market indices, and ratings. Implementation should begin with a small verified
set rather than exposing unvalidated calculations.

## Analysis Framework

The planned fund report combines three questions:

1. **What is the fund?** Identify its mandate, structure, people, costs,
   holdings, benchmark, and practical investment constraints.
2. **How has it behaved?** Measure outcome, volatility, drawdown,
   benchmark-relative performance, category-relative performance, and
   consistency over multiple market conditions.
3. **Does it fit the investor or portfolio?** Consider horizon, risk
   tolerance, goals, portfolio overlap, allocation, tax considerations,
   transaction history, and alternatives.

### Minimum Report Sections

| Section | Expected output |
| --- | --- |
| Summary | Objective, classification, status commentary, data date, important limitations, and high-level observations. |
| Performance | NAV growth, trailing and rolling returns, calendar-period returns, benchmark/category/peer comparisons, and SIP/lump-sum evaluation. |
| Risk and consistency | Volatility, beta, alpha, Sharpe, Sortino, drawdown, capture ratios, negative-period behavior, and consistency scoring. |
| Portfolio | Holdings, allocations, sectors, concentration, turnover, cash, geographic exposure, and change history. |
| Costs and rules | Expense ratio, exit load, taxation, minimum investments, lock-in, and plan/option details. |
| People and governance | AMC, fund manager tenure and history, scheme documents, and relevant red flags or disclosures. |
| Interpretation | Evidence-supported observations, fit questions, comparison prompts, and explicit non-advisory caveats. |

## Ideas Incorporated From the Tejas Performance Study

[docs/tejasblog2.md](docs/tejasblog2.md) documents a worked example that evaluates HDFC
Flexi Cap Fund and Parag Parikh Flexi Cap Fund against the NIFTY 500 from 2019
through 2023. The example is especially useful because it separates two kinds
of performance question that are often mistakenly treated as the same.

### Data Retrieval and Normalization

The article's implementation approach suggests a practical first analytics
pipeline:

1. Fetch mutual fund historical NAV values using an Indian mutual fund data
   source such as `mftool`.
2. Fetch benchmark index history, illustrated using NIFTY 500 data from
   `jugaad_data`.
3. Normalize dates and numeric NAV/close fields, sort data, remove duplicate
   dates, and align fund and benchmark observation periods.
4. Calculate daily percentage change and compounded cumulative returns for
   graphs and absolute-return output.
5. Calculate CAGR for a chosen number of years and retain comparable tabular
   results for each fund and benchmark.

This pipeline should later add source metadata, retrieval timestamps, missing
date treatment, dividend/plan handling, benchmark mapping, and reproducibility
tests before powering user-visible conclusions.

### Two Performance Perspectives

The methodology distinguishes two valid but different analyses:

| Perspective | Question answered | Example window construction | Use in this project |
| --- | --- | --- | --- |
| Investment journey | What happened to an investment made at a particular start date? | Start from January 2019 and extend the endpoint for one, two, three, four, or five years. | Portfolio tracking and review of an investor's actual experience. |
| Screener style | Which fund looks strongest over recent trailing horizons today? | Hold the December 2023 endpoint constant and move the start date backward for one through five years. | Discovery, screening, and new-investment comparison. |

The study notes that results can materially differ between these two views.
Accordingly, the application should label return periods clearly rather than
presenting one performance ranking as universally relevant.

### Annual Performance and Benchmark Consistency

The worked example also computes individual calendar-year returns and evaluates
whether each fund beat its benchmark year by year. This matters because a fund
can show an attractive overall CAGR while performing inconsistently or
underperforming during market conditions that matter to an investor.

The project should extend this idea through:

- Annual and quarterly benchmark comparisons, particularly for negative
  benchmark periods.
- Rolling-return win rates, ranges, means, and volatility rather than only
  endpoint-based return values.
- Downside/upside capture, drawdown, and recovery analysis.
- Category-average and peer comparisons in addition to a market benchmark.
- SIP and transaction-level XIRR analysis, since actual investors commonly
  invest through repeated cash flows rather than one lump sum.

### Product Interpretation

For a prospective investor, screener-style returns paired with annual and
rolling consistency provide useful comparative evidence. For an existing
investor, the investment-journey perspective paired with actual transaction
XIRR and benchmark simulation more directly answers whether the portfolio has
served its purpose. In both cases, allocation, expense ratio, AUM, turnover,
risk, manager changes, and investment objective remain necessary context.

The complete copied study notes, code fragments, outputs, and its associated
figures remain available in [docs/tejasblog2.md](docs/tejasblog2.md).

## Portfolio Analysis and Backtesting

### Portfolio Input

A portfolio module should accept manually entered transactions or an uploaded
CSV/workbook, and may later integrate with an authorized account-data source.
The minimum transaction data includes scheme, transaction type, date, units,
NAV, and cash amount. Current-holdings input may additionally include folio,
AMC, category, source identifier, invested value, current value, and reported
XIRR.

### Portfolio Output

Analysis envisioned by the current documentation and sample workbook includes:

- Invested amount, current value, total and daily return, XIRR, and fund-level
  attribution.
- Portfolio-versus-benchmark and portfolio-versus-category simulation using
  the investor's historic cash flows to estimate alpha or missed gains.
- Asset, market-cap, sector, geographic, and fund allocation, plus
  stock-level overlap and overall security exposure.
- Concentration, turnover, correlation-based diversification, volatility,
  drawdown, and cost analysis.
- Investment journey charts, best and lagging contributors, alerts, relevant
  market/news context, tax-efficiency considerations, and review prompts.
- Evidence-based rebalancing candidates or fund review candidates, with
  explanations rather than automatic buy/sell instructions.

[docs/Portfolio Analysis.xlsx](docs/Portfolio%20Analysis.xlsx) is the present draft
example of this output direction. [docs/analysis.py](docs/analysis.py) is a sample
prototype for quantitative analysis, qualitative/behavioral observations,
benchmark comparison, visualization, and optional AI insights. It must be
reviewed, tested, and supplied with validated data before it is relied on.

### Risk Profiles and Recommendations

The draft workflow proposes a questionnaire covering investing experience,
income stability, financial dependants, temporary-loss tolerance, horizon, and
return expectations. It considers defensive, moderate, and aggressive
portfolios:

| Profile | Intended emphasis |
| --- | --- |
| Defensive | Lower volatility and downside risk, greater stability and liquidity, and suitable large-cap/debt balance. |
| Moderate | A measured balance between return opportunity, volatility, beta, diversification, and hybrid allocation. |
| Aggressive | Greater growth potential and accepted volatility, while still assessing risk-adjusted outcomes and diversification. |

Any recommendation logic should be explainable, regularly backtested, privacy
conscious, and presented as decision support rather than a promise of future
return. AI may help summarize calculations or explain findings only after the
underlying deterministic metrics and source data are visible and validated.

### Backtesting

[docs/backtest.py](docs/backtest.py) is a sample implementation of tactical-versus-passive
SIP analysis. The wider workflow explores:

- Fixed portfolio weights with SIP or lump-sum input and benchmark mappings.
- Annual rebalancing and comparisons between static and tactical allocations.
- Equity signals based on positive 12-month momentum, a 10-month moving
  average trend filter, and six-month realized volatility.
- Further candidate rules such as valuation-aware SIP redirection and combined
  signals that require research and validation before implementation.
- Output metrics including final corpus, XIRR, CAGR/trailing performance,
  rolling returns, volatility, downside-quarter behavior, and comparative
  charts.

Backtests must document the available data period, benchmark choice, costs,
tax assumptions, rebalancing dates, missing data, survivorship risk, and the
fact that historical simulation does not predict future performance.

## Data Sources and Feasibility

The original research explored multiple ways to source data for Indian mutual
funds. Full exploratory code and captured example output are preserved in
[docs/data-source-exploration.md](docs/data-source-exploration.md).

| Source or library | Potential use | Current observation or constraint |
| --- | --- | --- |
| `mftool` | Public Indian scheme details and historical NAV using AMFI scheme codes. | Good candidate for initial NAV ingestion; portfolio-holding availability is limited. |
| `mfapi.in` | JSON API for basic scheme metadata and NAV history. | Candidate NAV source or validation source; data coverage and reliability should be tested. |
| `mf.captnemo.in` | Scheme/NAV lookup using ISIN, with captured example fund output. | Useful for some metadata; explored notes indicate holdings support is insufficient for the planned portfolio analysis. |
| `mstarpy` / Morningstar public data | Returns, category information, risks, allocations, and holdings where available. | Promising enrichment source, but Indian fund fields can be unavailable or access-restricted; terms and reliability need review. |
| `yfinance` and `yahooquery` | Fund/market data and possible holding or sector fields for mapped Yahoo tickers. | Useful for experimentation; ticker coverage and missing fields for Indian funds must be handled carefully. |
| `jugaad_data` / NSE index sources | Benchmark index series such as NIFTY 500. | Used in the Tejas study pattern; validate licensing, mapping, and update reliability. |
| Zerodha Kite API | Account-linked instruments and holdings. | Requires account setup and is not a general public-data foundation for the intended application. |
| Google Finance in Sheets | Spreadsheet experimentation for market instruments. | Not a reliable public Python API or comprehensive Indian mutual fund data source. |
| `indianapi.in` | Indian stocks and basic mutual fund details. | Candidate to evaluate, not yet adopted. |
| Direct web scraping | Filling information gaps from public pages. | Brittle and subject to terms, legal, ethical, and maintenance concerns; prefer authorized APIs/data sources. |

Holdings history, expense/load history, manager tenure data, benchmark mapping,
tax rules, corporate actions, and data licensing are important gaps to solve
before a complete report generator or public application can be dependable.

### Current Runtime Provider Flow

The implemented Django app currently favors temporary, request-scoped data over
bulk persistence:

- Search uses the AMFI scheme universe cache.
- Fund detail pages fetch NAV history and latest NAV on demand, then calculate
  returns and risk metrics in memory.
- Captnemo metadata is requested by exact ISIN first; when a provider only has
  a sibling growth plan, those values are labelled as reference values in the
  UI instead of being treated as exact-plan facts.
- Portfolio data tries `mstarpy` first because it has the best observed
  holdings and allocation coverage, then falls back to `yahooquery` after
  resolving a Yahoo ticker through normalized fund-name and NAV/date checks.
- Detail data is cached briefly in process memory but is not written as a
  permanent local fund dataset.

## Technology Direction

The implementation is now a Python-first Django application. The original
design notes still explain the intended product direction, while the current
codebase provides routing, forms, authentication, database support,
administration, and a path to a full web product.

| Layer | Proposed direction |
| --- | --- |
| Web application | Django templates with HTML/CSS initially; HTMX can add lightweight interactivity when necessary. |
| Data and analytics | Python, Pandas and NumPy for transformations and calculations; Plotly or Matplotlib for visual output. |
| Storage | SQLite during early development; migrate to a managed relational database such as PostgreSQL or MySQL as operational needs grow. |
| Data ingestion | Adapter layer for NAV, benchmark, holdings, and metadata providers with caching, provenance, and validation. |
| Recommendation support | Deterministic metrics first; optional scikit-learn/LLM assistance only with clear explanation and reliability controls. |
| Deployment | A Django-capable host such as Render or Railway rather than GitHub Pages, which hosts only static content. |

Privacy and transparency are core requirements: protect uploaded transaction
data, disclose how it is used, avoid exposing personal portfolio data, record
source dates, explain analytical rules, and visibly communicate the limits of
AI-generated observations.

## Implementation Roadmap

| Phase | Objective | Representative deliverables |
| --- | --- | --- |
| 0. Research and design (current) | Consolidate requirements, reports, reference studies, candidate sources, and prototypes. | This README, workflow, sample files, data-source notes, and reference artifacts. |
| 1. Data foundation | Establish repeatable scheme, NAV, benchmark, and metadata ingestion. | Provider adapters, scheme identifiers, validation checks, local storage, and data freshness/provenance. |
| 2. Fund report MVP | Generate a verified single-fund report from source data. | Summary, return/risk measures, benchmark comparison, charting, and report export based on the sample templates. |
| 3. Screening and comparison | Expose filters and side-by-side analysis. | Fund universe, categories, comparison metrics, rolling/annual return analysis, and core calculators. |
| 4. Portfolio analysis | Evaluate user cash flows and holdings securely. | Import format, XIRR, benchmark simulation, allocation/overlap, cost analysis, dashboard, and review observations. |
| 5. Backtesting and recommendations | Validate strategy concepts and investor-fit outputs. | Reproducible backtests, questionnaire, explained scoring, guardrails, auditability, and responsible AI summaries. |

## Project Structure

```text
MutualFundAnalysis/
|-- README.md
|-- docs/
|   |-- workflow.md
|   |-- tejasblog2.md
|   |-- data-source-exploration.md
|   |-- analysis.py
|   |-- backtest.py
|   |-- mutual fund analysis template.pdf
|   |-- Portfolio Analysis.xlsx
|   `-- Quant_small_cap_analysis.xlsx
|-- images/
|   |-- image.png ... image-9.png
|   `-- workflow-image.png ... workflow-image-58.png
|-- LICENSE
`-- .gitattributes
```

### File Responsibilities

| Path | Responsibility |
| --- | --- |
| `README.md` | Primary orientation: purpose, current state, integrated analysis approach, architecture direction, and roadmap. |
| `docs/workflow.md` | Detailed feature backlog and proposed user-interface/report workflow with screenshots for later implementation. |
| `docs/tejasblog2.md` | Referenced performance-comparison methodology and worked Python example retained for study. |
| `docs/data-source-exploration.md` | Deep exploratory notes, code samples, source limitations, and example outputs formerly maintained in the README. |
| `images/` | Single documentation-asset location; existing article figures retain `image-*` names and formerly root-level design screenshots use the `workflow-image-*` prefix. |
| `docs/analysis.py` | Sample future portfolio-analysis implementation; it is not presented as tested production behavior. |
| `docs/backtest.py` | Sample future portfolio-backtesting implementation; its strategy assumptions require review and testing. |
| `*.xlsx` and `*.pdf` | Example spreadsheet/report templates to guide output design and future report generation. |

## Research References

The repository documentation currently draws ideas from these sources and
projects:

- Mutual fund research sites: [AdvisorKhoj](https://www.advisorkhoj.com/),
  [Moneycontrol](https://www.moneycontrol.com/mutualfundindia/),
  [ET Money](https://www.etmoney.com/mutual-funds/),
  [RupeeVest](https://www.rupeevest.com/), and
  [Morningstar India](https://www.morningstar.in/tools/mutual-fund-detailed-portfolio.aspx).
- Tejas Ekawade's Python study:
  [getting and analyzing mutual funds](https://medium.com/@TejasEkawade/getting-and-analyzing-mutual-funds-in-python-c2d0feb09881)
  and
  [benchmarking and comparing funds](https://medium.com/@TejasEkawade/analyzing-mutual-funds-using-python-benchmarking-and-comparing-funds-215350bf58b7).
- Data and portfolio project references:
  [mftool](https://github.com/NayakwadiS/mftool),
  [mstarpy](https://github.com/Mael-J/mstarpy),
  [mfutility](https://github.com/devanshdalal/mfutility),
  [mf-analysis](https://github.com/asrajavel/mf-analysis),
  [portfolioanalyser](https://github.com/anoninvestor/portfolioanalyser),
  [folioman](https://github.com/codereverser/folioman), and
  [MF-Investment-Analyser](https://github.com/rishabhrkaushik/MF-Investment-Analyser).
- Forecasting and analytical exploration:
  [Forecasting_Mutual_Funds](https://github.com/NayakwadiS/Forecasting_Mutual_Funds)
  and
  [Mutual-funds-Analysis-and-prediction](https://github.com/srinivasRM/Mutual-funds-Analysis-and-prediction).

Additional reference links, API experiments, code, captured data examples, and
backtesting video links remain in the supporting documentation, so exploratory
material is retained without making this entry point difficult to navigate.

## License

See [LICENSE](LICENSE) for repository licensing information.
