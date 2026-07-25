# Institutional Mutual Fund Research Report System

> **A multi-page, quantitative mutual fund research report generator featuring dynamic analyst commentary, 6-pillar scorecards, riskometer gauges, side-by-side rolling return distribution box plots, peer comparison matrices, and Chrome headless PDF rendering.**

---

## 1. Overview & Architecture

The Institutional Research Report engine (`apps/funds/report.py`) automatically generates an institutional-grade PDF research report for any Indian Direct Growth Mutual Fund or ETF. 

Unlike traditional static PDF reports, this report synthesizes **quantitative metrics and dynamic rule-based research narratives** to deliver actionable investment takeaways, executive recommendation verdicts, key strengths, risk considerations, and strategic rebalancing rules.

```
                  ┌─────────────────────────────────────┐
                  │          Scheme Selection           │
                  │   (AMFI Code / Scheme Model Object) │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │       Runtime Data Aggregator       │
                  │    (apps.funds.runtime.get_...)     │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │   Quantitative 6-Pillar Model Score │
                  │     (apps.analytics.scorer.score)   │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │  Dynamic Research Narrative Engine  │
                  │  (_build_research_narratives(ctx))  │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │     Plotly Chart Generator System   │
                  │ (Plotly.js + Kaleido PNG Export)    │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │  Django Template Context Assembly   │
                  │ (templates/funds/report_pdf.html)   │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │    Chrome Headless PDF Compiler     │
                  │   (--no-pdf-header-footer CLI)      │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │   Final Institutional PDF Artifact  │
                  │        (FundReport_<name>.pdf)      │
                  └─────────────────────────────────────┘
```

---

## 2. Institutional Report Structure Breakdown


| Page # | Section Title | Key Visuals & Analytical Components |
|---|---|---|
| **Page 1** | **Institutional Cover Page** | Dark slate / indigo gradient hero banner, rating score badge, 6-card performance & risk KPI grid, fund specifications table, investment objective box, executive start disclaimer. |
| **Page 2** | **Fund Scorecard & Executive Summary** | Executive Verdict Card (`STRONG BUY`, `BUY`, `HOLD`, `REBALANCE`), recommended holding horizon, investor profile, deployment strategy, key strengths bullet card, key risks bullet card, quantitative score gauge, category rank, 6-pillar score breakdown table. |
| **Page 3** | **Returns Analysis** | Historical CAGR & trailing performance commentary box, NAV growth chart, trailing CAGR table (1M, 3M, 6M, 1Y, 3Y, 5Y, Max vs benchmark & category), calendar-year returns bar chart & table. |
| **Page 4** | **Rolling Returns Analysis** | Rolling return consistency & win-rate commentary box, side-by-side rolling return distribution box plot (1Y, 2Y, 3Y, 5Y, 7Y), 1Y / 3Y / 5Y rolling return timeseries charts, statistical tables (min, max, median, mean, win-rate >0%, win-rate >8%). |
| **Page 5** | **Risk & Risk-Adjusted Returns** | Volatility & risk-adjusted return commentary box, 4-card metric explainer grid (Jensen's Alpha, Sharpe & Sortino, Beta, Max Drawdown), 3Y risk metrics table, 5Y risk metrics table, worst drawdown chart & recovery table. |
| **Page 6** | **Yearly Risk & Market Regimes** | Yearly risk table (annualized volatility, max drawdown, Sharpe by calendar year), 6-period crisis stress-test table (2024–25 Tariff Shock, COVID-19 Crash, 2022 Rate Hikes, 2018 IL&FS, 2015 China Slowdown, 2008 GFC), market regime analysis table (Bull, Bear, Sideways, High Inflation, Rate Cut). |
| **Page 7** | **Portfolio & Asset Allocation** | Portfolio concentration commentary box, top 20 stock holdings table, sector allocation donut chart & table, market-cap / asset-class allocation breakdown. |
| **Page 8** | **Quarterly Performance & Peer Comparison** | Peer group positioning commentary box, best & worst quarterly return tables, 10-column peer fund comparison matrix (Fund, AMC, 1Y, 3Y, 5Y, Sharpe, Volatility, Alpha, Expense Ratio, AUM), link to interactive web calculator. |
| **Page 9** | **Technical Indicators Summary** | Multi-timeframe technical trend commentary box, Daily / Weekly / Monthly technical indicator cards, quantitative signal counts (Buy, Neutral, Sell), moving average tables, oscillator tables, technical riskometer gauge charts. |
| **Page 10** | **SIP & Tax Analysis** | SIP returns table (1Y, 3Y, 5Y total invested, current value, XIRR), capital gains tax rules table (STCG, LTCG FY 2025-26 rules for Equity, Debt, and Hybrid funds). |
| **Page 11** | **Fund Manager & Data Sources** | Fund manager profiles, lead tenure, investment objective statement, data provenance table (AMFI, mfapi.in, Yahoo Finance, Morningstar), model scoring methodology notes. |
| **Page 12** | **Analyst Summary & Final Verdict** | Final analyst investment verdict card, core vs satellite allocation guidance, strategic rebalancing & exit trigger rules, institutional risk disclosure. |

---

## 3. Dynamic Narrative Generator (`_build_research_narratives`)

The narrative generator in `apps/funds/report.py` dynamically builds section-by-section institutional text:

```python
def _build_research_narratives(ctx: dict) -> dict:
    """
    Evaluates calculated score, percentile rank, 3Y CAGR, Alpha, Beta,
    Sharpe Ratio, Volatility, Rolling Win-Rates, and Technical Signals.
    Returns dynamic verdict action, tagline, horizon, profile, strategy,
    bulleted strengths, monitorable concerns, and commentary text blocks.
    """
```

### Rating Verdict Triggers:
- **Score ≥ 75**: `STRONG BUY / OUTPERFORM` (Top-tier performer, robust alpha, disciplined risk control)
- **Score ≥ 60**: `BUY / ACCUMULATE` (Solid core holding, consistent benchmark beating capability)
- **Score ≥ 45**: `HOLD / NEUTRAL` (Balanced performance aligned with category averages)
- **Score < 45**: `UNDERPERFORM / REBALANCE` (Lagging relative returns or elevated risk metrics)

---

## 4. PDF Compilation Engine (`_chrome_html_to_pdf`)

To render pixel-perfect CSS Paged Media and execute high-resolution Plotly chart rendering without native Windows library dependencies, the system uses Google Chrome headless:

```python
cmd = [
    chrome_exe,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--run-all-compositor-stages-before-draw",
    "--print-to-pdf-no-header",
    "--no-pdf-header-footer",
    f"--print-to-pdf={pdf_path}",
    f"file:///{html_path}",
]
```

### Key Technical Enhancements:
- **Suppression of Default URLs**: Passes `--no-pdf-header-footer` to remove Chrome's default `file:///...` header and date footer.
- **Custom Running Headers**: Employs a styled `.page-header` running band displaying `"Mutual Fund Analysis — Research Report"` at the top left of every page.
- **Side-by-Side Box Plots**: Uses Plotly `boxmode="group"` with explicit `x=[window]` groupings to render clean, un-overlapped 1Y–7Y rolling return distributions.
- **Riskometer Gauge Meters**: Custom SVG-based gauge rendering with Plotly `update_layout()` keyword isolation.

---

## 5. Usage & Integration

### Via View Endpoint:
```python
# GET /funds/<amfi_code>/report/
from apps.funds.report import generate_fund_report_response

def fund_report_view(request, amfi_code):
    scheme = get_object_or_404(Scheme, amfi_code=amfi_code)
    return generate_fund_report_response(request, scheme)
```

### Via Python Script / Shell:
```python
from apps.funds.models import Scheme
from apps.funds.report import build_report_context, _chrome_html_to_pdf
from django.template.loader import render_to_string

scheme = Scheme.objects.get(amfi_code="122639")
ctx = build_report_context(None, scheme)
html = render_to_string("funds/report_pdf.html", ctx)
pdf_bytes = _chrome_html_to_pdf(html)

with open("Parag_Parikh_Research_Report.pdf", "wb") as f:
    f.write(pdf_bytes)
```

---

## 6. Calculator Hub Integration & In-App Canvas Viewer

### Route & Access Control
- **URL Route**: `/calculators/research-report/`
- **Access Control**: `@login_required` decorator ensures only authenticated users can access the report generator tool.
- **Query State**: Accepts `?scheme=<amfi_code>&auto=1` for auto-triggering report generation directly from the Fund Detail Page (`/funds/<amfi_code>/`).

### Pre-Fetch & In-Memory Blob Rendering
1. **Async Fetch**: The client performs a background `fetch('/funds/<amfi_code>/report/')` while animating a 5-step progress loader.
2. **PDF.js Canvas Engine**: Once the server returns the PDF binary stream, it is converted into an in-memory `ArrayBuffer` and passed directly to `pdfjsLib.getDocument({ data: arrayBuffer })`.
3. **Zero Disk Footprint**: The document is rendered dynamically in browser memory without writing temporary PDF files to server disk.
4. **Dynamic Scroll Page Tracking**: A bounding-box scroll listener calculates the active page in view as the user scrolls up and down, updating the toolbar's `Page X of Y` indicator in real time.

