# UI Info Button Tooltip System

To make the platform more accessible for users with limited financial knowledge, every key metric, ratio, and calculator input has a contextual `ⓘ` info button. Clicking or hovering reveals a structured popup explaining what the metric is, how to interpret it, relevant benchmark ranges, and any important caveats.

## How It Works

The tooltip engine is a self-contained IIFE in `static/js/main.js` (`initInfoTooltips()`). It attaches to any `<button class="info-btn">` and reads `data-t-*` attributes to build a rich, styled popup dynamically — no external libraries required.

### Key design decisions
- **Plain text in attributes** — no HTML is embedded in `data-t-*` values. The engine renders sections in its own structured layout.
- **`_tooltipBound` guard** — prevents double-binding when `initInfoTooltips()` is called multiple times.
- **Dynamic content** — after any JS re-render (e.g., SIP results), call `initInfoTooltips(container)` with the updated DOM subtree to bind new buttons.
- **`&#9432;` character** — every `<button class="info-btn">` must have this as its text content so the ⓘ glyph renders correctly.

---

## Usage Guide

Add an info button next to any metric or label:

```html
<button class="info-btn"
        aria-label="Metric Name"
        data-t-title="Full Metric Name"
        data-t-what="What this metric is in plain English."
        data-t-interp="How to interpret it (e.g., Higher is better).">&#9432;</button>
```

### Available Attributes

| Attribute | Required | Description |
|---|---|---|
| `data-t-title` | Optional | Bold title at the top of the tooltip. Falls back to `aria-label`. |
| `data-t-what` | Recommended | Plain-English description of what the metric/item is. |
| `data-t-interp` | Optional | Interpretation guide (e.g., "Higher values indicate more risk"). |
| `data-t-formula` | Optional | Mathematical formula or calculation. |
| `data-t-range` | Optional | JSON array of `{dot, label, text}` objects for a color-coded good/ok/bad scale. |
| `data-t-note` | Optional | Disclaimer or important caveat shown at the bottom (styled amber). |

### `data-t-range` Example

```html
data-t-range='[{"dot":"good","label":"< 1%","text":"Low cost"},{"dot":"bad","label":"> 2%","text":"Expensive"}]'
```

---

## Example Implementations

### Basic Explanation
```html
<div class="metric-key">AUM
  <button class="info-btn"
          data-t-title="Assets Under Management (AUM)"
          data-t-what="The total amount of money managed by this mutual fund.">&#9432;</button>
</div>
```

### With Interpretation and Note
```html
<button class="info-btn"
        data-t-title="Expected Annual Return"
        data-t-what="Assumed annualised growth rate of your investment. This is a projection, not a guarantee."
        data-t-interp="Debt funds: 6-8% | Hybrid: 9-11% | Nifty 50 avg: ~12% | Smallcap/Midcap: 12-16%"
        data-t-note="Past performance does not guarantee future returns.">&#9432;</button>
```

### Binding After Dynamic Render

When results are rendered via JavaScript (e.g., SIP historical calculator), call `initInfoTooltips` on the updated container **after** setting `innerHTML`:

```javascript
resultsArea.innerHTML = buildResultsHTML(data);
if (window.initInfoTooltips) {
  initInfoTooltips(resultsArea);
}
```

---

## Coverage

| Page / Calculator | Metric Buttons |
|---|---|
| **Net Worth** | Market Investments, Retirement Accounts, Total Assets, Total Liabilities, Net Worth, Solvency Ratio |
| **SIP Calculator** | Monthly Amount, Investment Period, Return Rate, Start Date, Instalment, Absolute Gain, XIRR (results) |
| **Step-Up SIP Calculator** | Same as SIP + Annual Step-Up % |
| **XIRR Calculator** | XIRR metric, Cashflow entry guide |
| **Fund detail pages** | Sharpe, Sortino, Alpha, Beta, Max Drawdown, Capture Ratios, Expense Ratio, AUM, and more |
| **Screener — filter sidebar** | All ~30 filterable metrics (AUM, Returns, Volatility, Sharpe, Sortino, Drawdown, Alpha, Beta, Tracking Error, etc.) |
| **Screener — Add Filters panel** | Every metric in all 4 filter categories (Scheme Info, Returns, Risk, Relative Stats) |
| **Screener — column headers** | Every sortable column header in the results table |
| **Backtester results** | Key risk and return metrics |

---

## Screener-Specific Tooltips

The Screener uses a dedicated `const TOOLTIPS` object (in `templates/funds/screener.html`) that maps each filter key to its tooltip HTML attribute string. This is used for **dynamically added filters** (the Add Filter panel and left sidebar) so that tooltips are generated at render time via JavaScript.

Example entry:

```javascript
const TOOLTIPS = {
  aum: 'data-t-title="AUM (Cr)" data-t-what="Total assets managed by the fund." data-t-interp="..."',
  volatility_3y: 'data-t-title="3Y Volatility %" data-t-what="..." data-t-interp="..."',
  // ...
};
```

When `buildRangeWidget(key, meta)` renders a dynamic filter, it uses `TOOLTIPS[key]` to inject the full tooltip definition into the `ⓘ` button.

---

## Styling

- **CSS:** Info button and tooltip styles are in `static/css/main.css` under `/* --- Tooltips --- */` and also in `templates/base.html` (`.info-btn` base styles).
- **Positioning:** The engine detects screen edges and flips the tooltip above or left if it would overflow.
- **Mobile:** Tooltip width is clamped to viewport; never causes horizontal scrollbars.
- **Keyboard:** Buttons are focusable (`tabindex="0"`); `Enter` or `Space` toggles the tooltip; `Escape` closes it.
