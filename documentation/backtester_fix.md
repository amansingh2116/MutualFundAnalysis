# Backtester V2 — Comprehensive Fix & Enhancement Plan

## Project Context

**Framework:** Django 4.x + vanilla JS (no React/Vue). No TypeScript.  
**Key files:**
- `templates/portfolio/backtester.html` — Single-file frontend (HTML + CSS in `{% block extra_head %}` + JS in `{% block extra_js %}`). ~3150 lines.
- `apps/portfolio/views.py` — Django views including `portfolio_fund_search_api`, `backtester_v2_run_api`, `backtester_pe_api`
- `apps/portfolio/services/backtester_v2.py` — Core simulation engine (~2420 lines)
- `apps/portfolio/services/pe_adapter.py` — PE/PB/DivYield data fetcher using nsepython
- `apps/portfolio/models.py` — Django models (Portfolio, Transaction)
- `apps/portfolio/urls.py` — URL patterns

**URL patterns (from `apps/portfolio/urls.py`):**
```
path('backtester/', views.portfolio_backtester_view, name='backtester'),
path('backtester/v2/run/', views.backtester_v2_run_api, name='backtester_v2_run'),
path('backtester/fund-search/', views.portfolio_fund_search_api, name='backtester_fund_search'),
path('backtester/pe-data/', views.backtester_pe_api, name='backtester_pe_data'),
```

**Authentication:** Django session auth. User is `request.user`. All new DB models must use `user = models.ForeignKey(settings.AUTH_USER_MODEL, ...)`.

---

## User Decisions (Confirmed)

| Decision | Choice |
|----------|--------|
| Save Strategy storage | **Database per user account** (requires login) — new Django model + migration |
| Custom Benchmark UI | **Simple accordion** inside Step 3 panel — "add index + weight %" form, last added index auto-adjusts weight to hit exactly 100% |
| CAGR | **Remove entirely** — keep only XIRR as the primary return metric |
| PE data caching | **Retry mechanism + local SQLite cache** for PE/PB/divYield data |

---

## ISSUE LIST (All Items to Fix)

---

### ISSUE 1 — Monte Carlo Toggle Button Doesn't Show "On" State

**Severity:** Medium — UX broken  
**File:** `templates/portfolio/backtester.html`

**Root Cause:**  
The `toggleSetting` function in JS (line ~1992) correctly calls `row.classList.toggle('on', toggleStates[key])`. The ID mapping is:
- `toggleSetting('mc')` → looks for element with id `toggleMC` — ✅ exists at line 1231
- `toggleSetting('exitload')` → looks for `toggleExitload` — ✅ exists at line 1175
- `toggleSetting('tax')` → looks for `toggleTax` — ✅ exists at line 1181
- `toggleSetting('inflation')` → looks for `toggleInflation` — ✅ exists at line 1207

The `toggleSetting` builds the ID as:
```js
const row = document.getElementById(`toggle${key.charAt(0).toUpperCase()+key.slice(1)}`);
```
For key `'mc'` this produces `toggleMC` ✅. The CSS `.toggle-row.on .toggle-switch { background: var(--accent); }` exists (line 437). The issue is likely that the CSS variable `--accent` is not defined or not visible enough. The toggle switch track should change color but may be invisible.

**Fix:**
1. Check that `--accent` is defined in `:root` CSS variables in the file. If not, add `--accent: #6366f1;` to the root variables.
2. Also add a more explicit visual label change: when `.toggle-row.on`, display "ON" text in the `.toggle-switch::before` pseudo-element or change the label text from "Off" to "On".
3. Alternatively, hard-code the "on" state to use a specific green: `.toggle-row.on .toggle-switch { background: #22c55e; }`.

---

### ISSUE 2 — Live PE Widget in Header is Broken/Confusing

**Severity:** Low — UI clutter  
**File:** `templates/portfolio/backtester.html` lines 1047–1051 and lines 3102–3150

**Root Cause:**  
The live PE widget appears in the left panel header next to "⚗️ Strategy Backtester". It shows `PE — —` (two em-dashes). It calls `fetchLivePE()` on DOMContentLoaded which calls `/portfolio/backtester/pe-data/?index=NIFTY+50&from=...&to=...`. This fails because nsepython's `index_pe_pb_div` is broken (see Issue 7). The widget shows nothing useful and looks like a broken badge.

**Fix:**
1. **Remove the widget from the header** — delete lines 1047–1051 from HTML
2. Replace `fetchLivePE()` call in DOMContentLoaded with a no-op or remove entirely
3. Instead, PE data will be available in the trigger panel (Issue 7 fix) and shown as a chart overlay when PE trigger is used

---

### ISSUE 3 — Benchmark: Wrong Search, No Default, Not Shown in Analysis Tabs

**Severity:** High — core feature broken  
**File:** `templates/portfolio/backtester.html` — benchmark section (lines 1149–1157), `initBenchSearch()` function, `buildPlan()` function, all chart/metrics render functions

**Sub-issues:**

#### 3a — Benchmark search shows mutual funds (should show ONLY indices)

**Root Cause:** `initBenchSearch()` calls `doSearch(q, 'benchmarkDropdown', onBenchSelect, 'all')` — the `'all'` type searches both schemes AND indices. Should be `'index'` only.

**Fix:** Change `doSearch(q, 'benchmarkDropdown', onBenchSelect, 'all')` → `doSearch(q, 'benchmarkDropdown', onBenchSelect, 'index')`

#### 3b — Benchmark doesn't default to NIFTY 50

**Fix:** In `DOMContentLoaded` handler, after `initBenchSearch()`, add:
```js
// Default benchmark = NIFTY 50
document.getElementById('benchmarkSearch').value = 'NIFTY 50';
document.getElementById('benchmarkId').value = 'NIFTY 50';
document.getElementById('benchmarkType').value = 'index';
const benchSel = document.getElementById('benchmarkSelected');
benchSel.textContent = '✓ NIFTY 50';
benchSel.style.display = '';
```

#### 3c — Custom weighted benchmark (NEW FEATURE)

**UX:** Add a new UI mode below the benchmark search. When user selects "Custom Weighted Benchmark", the single benchmark search is replaced with an accordion that allows adding multiple index components with weights.

**HTML to add** (inside Step 3, replacing/below the benchmark field-group):
```html
<div class="field-group" style="margin-top:8px">
  <label>Benchmark Mode</label>
  <select id="benchmarkMode" onchange="onBenchmarkModeChange()">
    <option value="single">Single Index / Fund</option>
    <option value="custom">Custom Weighted Benchmark</option>
  </select>
</div>
<!-- Single mode (default) -->
<div id="benchSingleWrap">
  ... existing benchmark search UI ...
</div>
<!-- Custom mode -->
<div id="benchCustomWrap" style="display:none">
  <div id="benchCustomComponents"><!-- rendered by JS --></div>
  <button onclick="addBenchComponent()">+ Add Index</button>
  <div id="benchWeightSumDisplay" style="font-size:11px;margin-top:4px"></div>
</div>
```

**JS state:** `let benchCustomComponents = []` — array of `{source_id, label, weight}`.  
**JS function `addBenchComponent()`:** adds `{source_id:'', label:'', weight: 0}`, re-renders.  
**Weight auto-adjustment:** When rendering, the last component's weight is auto-set to `100 - sum(all_others)`. Display "Total: 100%" in green or red if not summing to 100.

**Backend:** `buildPlan()` must pass custom benchmark in settings:
```json
"benchmark_type": "custom",
"benchmark_components": [
  {"source_type": "index", "source_id": "NIFTY 50", "weight": 60},
  {"source_type": "index", "source_id": "NIFTY NEXT 50", "weight": 40}
]
```

**Backend service (`backtester_v2.py`):** When `benchmark_type == 'custom'`, build a weighted composite price series by normalizing each component to the same start value and blending by weight, then compute benchmark CAGR from this composite.

#### 3d — Benchmark metrics shown in analysis tabs

**Current state:** `benchmark_cagr` is computed in the backend and sent in the response, but only displayed in the Summary tab. `benchmark_values` (array of prices, normalized to same initial investment as portfolio) is computed and sent but only shown on the equity chart.

**Fix — Summary Tab:** Add a benchmark column/row to all the key metrics cards:
- Show "Portfolio XIRR" vs "Benchmark XIRR" (compute benchmark XIRR from benchmark_values series — requires adding this computation in `backtester_v2.py`)
- Show "Alpha = Portfolio XIRR − Benchmark XIRR"

**Fix — Charts Tab (equity chart):** Already shows benchmark as a line — ensure it has a legend label "NIFTY 50 (Benchmark)" or whatever the selected benchmark is.

**Fix — Risk Tab:** Add a "Benchmark Risk" column showing benchmark max drawdown, benchmark volatility (computed from `benchmark_values` series in backend).

**New backend fields to add to `BacktestResult`:**
```python
benchmark_xirr: Optional[float] = None     # XIRR of benchmark
benchmark_max_drawdown: Optional[float] = None
benchmark_volatility: Optional[float] = None
alpha: Optional[float] = None              # xirr - benchmark_xirr
```

---

### ISSUE 4 — Date Validation: Investment Dates vs Simulation Dates

**Severity:** High — can cause incorrect results silently  
**File:** `templates/portfolio/backtester.html` — `validatePlan()` function (find via `Select-String -Pattern "validatePlan"`)

**Requirements:**
1. If user sets rule `start_date` / `end_date` outside `[simStart, simEnd]`, show an error naming the fund and rule type.
2. If rule dates are empty (not set), auto-fill: `start_date = fund_inception_date` (from `a.inception_date`), `end_date = simEnd`.
3. If user enters a date before the fund's inception or after its latest NAV date, show a specific error: `"Parag Parikh Flexi Cap: SIP start date 2010-01-01 is before fund inception (2013-05-28)"`.

**Fix — Frontend `validatePlan()` function:**
```js
function validatePlan() {
  const errors = [];
  const simStart = document.getElementById('simStart').value;
  const simEnd = document.getElementById('simEnd').value;
  
  for (const a of assets) {
    for (const r of a.rules) {
      if (r.start_date && simStart && r.start_date < simStart) {
        errors.push(`${a.label}: ${r.rule_type.toUpperCase()} start date ${r.start_date} is before simulation start (${simStart})`);
      }
      if (r.end_date && simEnd && r.end_date > simEnd) {
        errors.push(`${a.label}: ${r.rule_type.toUpperCase()} end date ${r.end_date} is after simulation end (${simEnd})`);
      }
      // Check inception date
      if (a.inception_date && r.start_date && r.start_date < a.inception_date) {
        errors.push(`${a.label}: ${r.rule_type.toUpperCase()} start date ${r.start_date} is before fund inception (${a.inception_date})`);
      }
    }
  }
  return errors;
}
```

**Fix — `addSelectedAsset()` auto-fill inception date:**  
The `inception_date` field on the asset comes from the search result (`r.inception_date`). The backend search API already returns `nav_date` as `inception_date` (this is not inception but last NAV date — needs to be fixed). Need the actual inception/start date. For now, use `nav_date` as a proxy for the fund data availability end date, and leave start blank (so simulation start is used).

**Fix — Backend validation in `backtester_v2_run_api`:** Add date range checks server-side as well; return descriptive error messages in the `data_warnings` list.

---

### ISSUE 5 — Trigger Panel: RSI, MA, Relative Valuation — Only Shows Selected Assets

**Severity:** Medium — limits strategy design  
**File:** `templates/portfolio/backtester.html` — `renderConditionParams` function (lines 2887–3009)

**Current Behavior:**  
For `relative_val` (lines 2930–2947), `ma_200` (lines 2950–2965), and `rsi` (lines 2968–2983), the "Reference Asset" dropdown is built from `assets.map(a => ...)` — meaning only the user's currently selected portfolio assets appear.

**Fix:**  
Replace the `<select>` with a live search input (reusing the `doSearch()` function):
```js
// Replace <select> with:
`<div class="search-wrap" style="position:relative">
  <input type="text" id="condRefSearch-${i}" placeholder="Search any fund or index…" autocomplete="off"
    value="${p.reference_label || ''}"
    oninput="onCondRefSearch(${i}, this.value, 'reference_id', 'reference_label')" />
  <div class="search-dropdown" id="condRefDropdown-${i}"></div>
</div>`
```

Add a global `onCondRefSearch(condIdx, q, idKey, labelKey)` function that calls `doSearch(q, 'condRefDropdown-'+condIdx, (result) => { updateCondParamNested(condIdx,'params',idKey, result.id); updateCondParamNested(condIdx,'params',labelKey, result.name); document.getElementById('condRefSearch-'+condIdx).value = result.name; document.getElementById('condRefDropdown-'+condIdx).classList.remove('open'); }, 'all')` with debounce.

For `relative_val`, two such search inputs are needed (Asset A and Asset B).

---

### ISSUE 6 — Trigger Panel: PE Signal Shows All Indices; Add PB + Div Yield

**Severity:** Medium  
**File:** `templates/portfolio/backtester.html` — `renderConditionParams` for `sig === 'pe_ratio'` (lines 2915–2928)

**Current Behavior:**  
PE ratio condition shows a `<select>` with `ALL_INDICES` (all ~68 NSE indices). But only NIFTY 50 has reliable PE/PB/DivYield data via nsepython.

**Fix:**

1. **In signal type dropdown** (line 2866–2877), update options:
```js
['pe_ratio', 'NIFTY 50 PE Ratio'],
['pb_ratio', 'NIFTY 50 PB Ratio'],
['div_yield', 'NIFTY 50 Dividend Yield'],
```
Remove `['fixed_return','Fixed Return (always on)']` (this is replaced by proxy debt — see Issue 11).

2. **In `renderConditionParams` for `pe_ratio`, `pb_ratio`, `div_yield`:**  
Remove the index `<select>` — hardcode to NIFTY 50 only. Display a static label `<div style="font-size:11px;color:var(--text-muted)">Data source: NIFTY 50 (NSE)</div>`. Just show operator and threshold value inputs.

3. **Auto-set `params.index_name = 'NIFTY 50'`** in `updateConditionSignal()` when sig is `pe_ratio`, `pb_ratio`, or `div_yield`.

4. **Backend support in `backtester_v2.py`:** The signal evaluator (find `elif sig == "pe_ratio"` around line 600–700) needs cases for `pb_ratio` and `div_yield`. These use the same `pe_adapter.get_pe_series()` but for different columns.

**Fix in `pe_adapter.py`:**  
Add new function `get_pb_series(index_name, from_date, to_date)` and `get_div_yield_series(index_name, from_date, to_date)` that call nsepython and extract `pb` and `divYield` columns respectively.

---

### ISSUE 7 — nsepython PE/PB/DivYield Fetch Fails with JSONDecodeError

**Severity:** High — PE/PB/DivYield triggers completely broken  
**File:** `apps/portfolio/services/pe_adapter.py`

**Root Cause:**  
`nsepython.index_pe_pb_div()` POSTs to `https://niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString` with:
```python
data = {'cinfo': "{'name':'NIFTY 50','startDate':'01-Jun-2025','endDate':'30-Jun-2025','indexName':'NIFTY 50'}"}
```
The niftyindices.com API is returning a non-JSON response (HTML error page). This is a session/cookie authentication issue on niftyindices.com — the API requires browser-like headers and session cookies.

**Fix — Replace nsepython call with direct HTTP with proper headers:**

```python
import requests
import json

NIFTY_INDICES_HEADERS = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'host': 'niftyindices.com',
    'origin': 'https://niftyindices.com',
    'referer': 'https://niftyindices.com/reports/historical-data',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def _fetch_nifty_pe_raw(index_name: str, from_str: str, to_str: str, max_retries: int = 3) -> pd.DataFrame:
    """
    Direct HTTP fetch of PE/PB/divYield from niftyindices.com with retry.
    from_str / to_str: format 'DD-Mon-YYYY' (e.g. '01-Jun-2025')
    Returns DataFrame with columns: DATE (str), pe (float), pb (float), divYield (float)
    """
    url = 'https://niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString'
    payload = {
        'cinfo': json.dumps({
            'name': index_name,
            'startDate': from_str,
            'endDate': to_str,
            'indexName': index_name
        })
    }
    
    session = requests.Session()
    # First: get the page to establish cookies
    session.get('https://niftyindices.com/reports/historical-data', headers=NIFTY_INDICES_HEADERS, timeout=15)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = session.post(url, json=payload, headers=NIFTY_INDICES_HEADERS, timeout=20)
            resp.raise_for_status()
            outer = resp.json()
            inner = json.loads(outer['d'])
            df = pd.DataFrame.from_records(inner)
            # Normalize columns: expected: 'INDEX_NAME', 'HistoricalDate', 'TIMESTAMP', 'pe', 'pb', 'divYield'
            return df
        except Exception as e:
            last_error = e
            time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s
    raise PEDataUnavailableError(f"Failed to fetch PE data for '{index_name}' after {max_retries} retries: {last_error}")
```

**SQLite Cache:** Add a new Django model `PEPBCache` or use a simple file-based SQLite DB (not the main DB) to cache PE/PB/divYield data:

```python
# Option A (simpler): use Python's sqlite3 directly in pe_adapter.py
import sqlite3, os
CACHE_DB = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.cache', 'pe_cache.db')

def _init_cache_db():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS pe_cache (
        index_name TEXT, date TEXT, pe REAL, pb REAL, div_yield REAL,
        PRIMARY KEY (index_name, date))''')
    conn.commit()
    conn.close()

def _get_cached_series(index_name, from_date, to_date):
    """Returns DataFrame from cache, None if not fully covered."""
    ...

def _save_to_cache(index_name, df):
    """Save DataFrame to cache."""
    ...
```

**Updated `get_pe_series` / `get_pb_series` / `get_div_yield_series`:**
1. Check SQLite cache first
2. If not fully covered, call `_fetch_nifty_pe_raw()` (with retry)
3. Save new data to SQLite cache
4. Return requested column as pd.Series

**Date format note:** nsepython uses `'DD-Mon-YYYY'` (e.g. `'01-Jun-2025'`). The current code correctly formats with `from_date.strftime("%d-%m-%Y")` but the API expects `%d-%b-%Y`. **This may be the actual root cause of the JSON error** — verify correct date format expected by the API.

**Also fix:** `pe_adapter.py` currently only returns `pe`. Extend to return `pb` and `div_yield` by adding new functions or a `metric` parameter.

---

### ISSUE 8 — wbgapi Inflation: Import Works but Wrong API Call

**Severity:** Medium — feature non-functional  
**File:** `apps/portfolio/services/backtester_v2.py` — `_fetch_wbgapi_cpi_rate()` (lines 807–835)

**Root Cause:**  
The function uses `wb.data.fetch('FP.CPI.TOTL.ZG', 'IND', mrv=...)` but the correct API for getting a DataFrame is `wb.data.DataFrame('FP.CPI.TOTL.ZG', 'IND')`. The DataFrame API returns:
- Index: `['IND']` (economy)
- Columns: `['YR1960', 'YR1961', ..., 'YR2024', 'YR2025']`
- Values: annual CPI inflation % (e.g., 5.64 for 2023, 4.95 for 2024)

**Also:** `manage.py shell` uses system Python, but wbgapi is only in `venv`. This is not an issue at runtime (Django server uses venv), only affects shell testing.

**Fix — Rewrite `_fetch_wbgapi_cpi_rate()`:**
```python
def _fetch_wbgapi_cpi_rate(sim_start: date, sim_end: date, warnings: List[str]) -> Optional[float]:
    """
    Fetch average annual India CPI inflation from World Bank API.
    Uses wbgapi.data.DataFrame which returns columns as 'YR{YYYY}'.
    Returns average % over the simulation window, or None on failure.
    """
    try:
        import wbgapi as wb
        df = wb.data.DataFrame('FP.CPI.TOTL.ZG', 'IND')
        # df has index=['IND'], columns=['YR1960',...,'YR2025']
        # Extract rates for years in [sim_start.year, sim_end.year]
        rates = []
        for yr in range(sim_start.year, sim_end.year + 1):
            col = f'YR{yr}'
            if col in df.columns:
                val = df.loc['IND', col]
                if val is not None and not pd.isna(val):
                    rates.append(float(val))
        if rates:
            avg = sum(rates) / len(rates)
            warnings.append(f"World Bank CPI (India): using average {avg:.2f}% over {sim_start.year}–{sim_end.year} ({len(rates)} years of data)")
            return round(avg, 2)
        warnings.append("World Bank CPI: no data for simulation period, using manual rate.")
    except ImportError:
        warnings.append("wbgapi not installed — using manual inflation rate instead.")
    except Exception as e:
        warnings.append(f"World Bank CPI fetch failed: {e}. Using manual rate.")
    return None
```

---

### ISSUE 9 — Switch Rule: Target Only Shows Selected Assets

**Severity:** Medium  
**File:** `templates/portfolio/backtester.html` — `renderRuleCard` for `rule.rule_type === 'switch'` (lines 1910–1944)

**Current Behavior:**  
Line 1922: `${assets.map((a, i) => i !== ai ? `<option value="${a.source_id}" ...>...</option>` : '').join('')}` — only shows OTHER currently selected portfolio assets.

**Required:** User should be able to switch to ANY fund or index, searched live.

**Fix:** Replace the `<select>` with a live search input (same pattern as Issue 5):
```js
`<div class="search-wrap" style="position:relative">
  <input type="text" id="switchToSearch-${ai}-${ri}" placeholder="Search fund or index to switch to…" autocomplete="off"
    value="${rule.switch_to_label || ''}"
    oninput="onSwitchToSearch(${ai}, ${ri}, this.value)" />
  <div class="search-dropdown" id="switchToDropdown-${ai}-${ri}"></div>
</div>`
```

Add to asset rule state: `switch_to_label: ''` (for display only).

Add `onSwitchToSearch(ai, ri, q)` function:
```js
function onSwitchToSearch(ai, ri, q) {
  clearTimeout(searchTimer);
  if (q.length < 2) { document.getElementById(`switchToDropdown-${ai}-${ri}`).classList.remove('open'); return; }
  searchTimer = setTimeout(() => doSearch(q, `switchToDropdown-${ai}-${ri}`, (result) => {
    assets[ai].rules[ri].switch_to_id = String(result.id);
    assets[ai].rules[ri].switch_to_label = result.name;
    assets[ai].rules[ri].switch_to_type = result.type === 'scheme' ? 'scheme' : 'index';
    document.getElementById(`switchToSearch-${ai}-${ri}`).value = result.name;
    document.getElementById(`switchToDropdown-${ai}-${ri}`).classList.remove('open');
  }, 'all'), 350);
}
```

Also update `buildPlan()` to include `switch_to_type` in the rule payload so the backend knows whether the target is a scheme or index.

---

### ISSUE 10 — Proxy Debt Option in Switch Rule; Remove Synthetic Debt Rate Field

**Severity:** Medium — UX improvement  
**File:** `templates/portfolio/backtester.html`

**Context:** Currently there's a "Synthetic Debt Rate (%/yr)" field in Step 3 settings and a "Fixed Return (always on)" trigger signal. These are confusing. The intended use case is: user wants to park money in a debt-like instrument. The proper way is via Switch rule.

**Fix:**

1. **Remove** `debtRate` / "Synthetic Debt Rate" input from Step 3 simulation settings (lines 1161–1163)
2. **Remove** `fixed_return` from trigger signal dropdown
3. **Add Proxy Debt option in Switch rule** — a mode selector at the top of switch rule:
```html
<div class="field-group" style="grid-column:1/-1">
  <label>Switch Target Type</label>
  <select onchange="updateRule(${ai},${ri},'switch_target_mode',this.value);renderAssets()">
    <option value="fund" ${rule.switch_target_mode==='fund'?'selected':''}>Fund / Index (search)</option>
    <option value="proxy_debt" ${rule.switch_target_mode==='proxy_debt'?'selected':''}>Proxy Debt (flat rate)</option>
  </select>
</div>
```

When `switch_target_mode === 'proxy_debt'`:
- Show: `<input type="number" id="proxyDebtRate" value="${rule.proxy_debt_rate||6}" step="0.1" min="0" max="30"> %/yr`
- Set `switch_to_id = '__proxy_debt__'` in `buildPlan()`

When `switch_target_mode === 'fund'`:
- Show the search input from Issue 9

**Backend:** In `backtester_v2.py`, when processing a switch rule with `switch_to_id == '__proxy_debt__'`, model the target as a synthetic series growing at `proxy_debt_rate` (compounding daily from the switch date). This is similar to the existing `synthetic_debt_rate` logic — reuse it but apply per-switch rule.

Also remove `synthetic_debt_rate` from `SimSettingsV2` dataclass since it's no longer a global setting.

---

### ISSUE 11 — Remove CAGR, Keep Only XIRR

**Severity:** Low — metric correctness  
**File:** `templates/portfolio/backtester.html` — `renderSummaryTab()` function, `apps/portfolio/views.py` — response dict, `apps/portfolio/services/backtester_v2.py` — result object

**Fix:**
1. **Backend (`backtester_v2.py`):** Keep `cagr` field in `BacktestResult` for backward compatibility but stop displaying it
2. **Frontend:** Remove CAGR from all metric cards in `renderSummaryTab()` and `renderRiskTab()`. Where CAGR appeared, show nothing or a tooltip explaining "Use XIRR for accurate SIP return measurement".
3. **API response (`views.py`):** Can keep sending `cagr` but frontend ignores it

---

### ISSUE 12 — Sharpe Ratio is Zero

**Severity:** High — metric incorrect  
**File:** `apps/portfolio/services/backtester_v2.py` lines 1294–1297 and line 1611

**Root Cause Analysis:**  
```python
def _sharpe(xirr: Optional[float], vol: Optional[float], rf: float = RF_ANNUAL) -> Optional[float]:
    if xirr is None or vol is None or vol == 0:
        return None
    return (xirr - rf) / vol
```
- `xirr` is in decimal (e.g., 0.127 for 12.7%)
- `RF_ANNUAL = 0.065` (6.5% in decimal) — reasonable
- `vol` from `metrics.get("volatility")` is also decimal (e.g., 0.18 for 18%)

This formula is correct: `(0.127 - 0.065) / 0.18 = 0.344`. Should NOT be zero.

**Possible causes:**
1. `vol` is `None` — means `_compute_metrics` returned empty metrics → means `portfolio_values_out` is all zeros or has < 2 elements
2. `vol` is `0` — series is constant (no trading, all zeros → pct_change() all zero)
3. `xirr_raw` is None

**Root cause likely:** `pf_series_for_metrics` is built from `portfolio_values_out` which is populated as the portfolio evolves. If the first SIP only happens mid-simulation, earlier values are 0. `pct_change()` on a series with leading zeros gives 0% returns until investment starts. `daily_ret.std()` would be near-zero. Need to **trim the series to start from first non-zero value**.

**Fix in `backtester_v2.py` around line 1604:**
```python
# Trim to first non-zero portfolio value
pf_series_raw = pd.Series(portfolio_values_out, index=pd.to_datetime(chart_dates_out))
first_nonzero = pf_series_raw[pf_series_raw > 0]
pf_series_for_metrics = first_nonzero if not first_nonzero.empty else pf_series_raw
metrics = _compute_metrics(pf_series_for_metrics)
```

Also display the Sharpe correctly — line 2321: `(data.sharpe||0).toFixed(2)` — if sharpe is `null`, this shows `0.00`. Fix to: `data.sharpe != null ? data.sharpe.toFixed(2) : 'N/A'`.

---

### ISSUE 13 — Fund Contribution (% of Portfolio) is Empty

**Severity:** High — chart broken  
**File:** `templates/portfolio/backtester.html` — `renderContributionChart()` (line 2649) and `apps/portfolio/services/backtester_v2.py` — `_build_per_asset_summary()`

**Root Cause:**  
`contribution_pct = round(current_val / total_final_value * 100, 2) if total_final_value > 0 else 0.0`

If there is only 1 asset, `current_val == total_final_value`, so `contribution_pct = 100.0`. But if `current_val = 0` (NAV lookup failed or no units), it shows 0.

The chart itself uses `a.contribution_pct || 0` — if value is `null` or `undefined`, shows 0.

**Fix in `_build_per_asset_summary`:**
1. Verify `nav_end` lookup works — `_nav_asof(series, sim_end)` must find a price for the end date. If NAV data ends before `sim_end`, it should forward-fill to find the last available price, not return None.
2. Ensure `asset_state[asset.source_id]["units"]` is correct at end of simulation.
3. Add logging: `logger.debug(f"Per-asset {asset.label}: units={units}, nav_end={nav_end}, current_val={current_val}")`.

**Fix in `renderContributionChart`:** If all values are 0, show a message instead of an empty chart.

---

### ISSUE 14 — Save Strategies Feature (NEW)

**Severity:** High — requested feature  
**Files:** `apps/portfolio/models.py`, `apps/portfolio/views.py`, `apps/portfolio/urls.py`, `templates/portfolio/backtester.html`, new template `templates/portfolio/strategies.html`

#### 14a — New Django Model

```python
# In apps/portfolio/models.py — add:
class SavedStrategy(BaseModel):
    """A saved backtester strategy plan."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='saved_strategies')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    plan_json = models.JSONField(help_text="Full plan payload as sent to backtester_v2_run_api")
    last_result_json = models.JSONField(null=True, blank=True, 
                                        help_text="Last backtest result for quick preview")
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.username} — {self.name}"
```

Run: `python manage.py makemigrations portfolio && python manage.py migrate`

#### 14b — New Views

```python
# In apps/portfolio/views.py — add:
@login_required
def save_strategy_api(request):
    """POST: save or update a strategy. GET: list saved strategies."""
    if request.method == 'GET':
        strats = SavedStrategy.objects.filter(user=request.user).values(
            'id', 'name', 'description', 'created_at', 'updated_at')
        return JsonResponse({'strategies': list(strats)})
    
    if request.method == 'POST':
        data = json.loads(request.body)
        strat_id = data.get('id')  # if updating
        if strat_id:
            strat = get_object_or_404(SavedStrategy, id=strat_id, user=request.user)
        else:
            strat = SavedStrategy(user=request.user)
        strat.name = data.get('name', 'My Strategy')
        strat.description = data.get('description', '')
        strat.plan_json = data.get('plan')
        strat.save()
        return JsonResponse({'id': strat.id, 'name': strat.name})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required  
def delete_strategy_api(request, pk):
    """DELETE a saved strategy."""
    strat = get_object_or_404(SavedStrategy, pk=pk, user=request.user)
    strat.delete()
    return JsonResponse({'status': 'deleted'})

@login_required
def strategies_page(request):
    """The saved strategies listing page."""
    return render(request, 'portfolio/strategies.html')
```

#### 14c — URLs

```python
# In apps/portfolio/urls.py — add:
path('strategies/', views.strategies_page, name='strategies'),
path('strategies/api/', views.save_strategy_api, name='save_strategy_api'),
path('strategies/api/<int:pk>/delete/', views.delete_strategy_api, name='delete_strategy'),
```

#### 14d — Frontend in Backtester

Add a **"💾 Save Strategy"** button in the left panel header area.

On click: show a modal with:
- Name input (required)
- Description textarea (optional)
- "Save" button → calls `POST /portfolio/strategies/api/` with current `buildPlan()` payload

Add **"📂 Load Strategy"** button → shows a modal listing `GET /portfolio/strategies/api/` and clicking one loads its `plan_json` into the current backtester state (populates `assets[]`, `rebalanceRule`, and all settings fields).

#### 14e — Compare Page (`templates/portfolio/strategies.html`)

A new page listing all saved strategies in a grid of cards. Each card shows:
- Strategy name + description
- Last saved date
- Key metrics from `last_result_json` (if available): XIRR, total invested, final value
- Buttons: "Load & Run", "Delete", "Compare"

**Compare feature:**
- User selects 2–4 strategies via checkboxes → "Compare Selected" button
- Opens a side-by-side comparison table showing: XIRR, Max Drawdown, Volatility, Sharpe, Total Invested, Final Value, Absolute Gain
- Runs the simulation fresh for each selected strategy in parallel (`Promise.all`) and displays results

---

## Implementation Order

### Phase 1 — Quick Fixes (No new models, minimal risk)
1. **Issue 1:** Fix MC toggle "on" visual state — add `--accent` color or use `#22c55e` directly
2. **Issue 2:** Remove broken PE widget from header
3. **Issue 3a:** Fix benchmark search to `type=index` only
4. **Issue 3b:** Default benchmark to NIFTY 50 in DOMContentLoaded
5. **Issue 6:** Fix PE signal → NIFTY 50 only; add PB + div yield signal types
6. **Issue 10:** Remove "Synthetic Debt Rate" field from settings; remove `fixed_return` trigger
7. **Issue 11:** Remove CAGR display from frontend

### Phase 2 — Backend Analytics Fixes
8. **Issue 12:** Fix Sharpe (trim leading zeros from portfolio series)
9. **Issue 13:** Debug and fix contribution_pct (add logging, verify NAV lookup)
10. **Issue 8:** Fix `_fetch_wbgapi_cpi_rate()` to use `wb.data.DataFrame` correctly

### Phase 3 — Trigger Panel + Switch UX
11. **Issue 5:** RSI/MA/RelVal trigger → live search for any fund/index
12. **Issue 9:** Switch target → live search for any fund/index
13. **Issue 10:** Proxy debt in switch rule

### Phase 4 — Date Validation
14. **Issue 4:** Frontend + backend date validation with fund-specific error messages

### Phase 5 — Benchmark Enhancements
15. **Issue 3c:** Custom weighted benchmark UI + backend composite series
16. **Issue 3d:** Benchmark metrics in all analysis tabs

### Phase 6 — PE/PB Data Infrastructure
17. **Issue 7:** Robust PE/PB/DivYield fetch with retry, session cookies, SQLite cache

### Phase 7 — Save Strategies (New Feature)
18. **Issue 14:** New model, views, URLs, frontend save/load/compare

---

## File Change Summary

| File | Changes |
|------|---------|
| `templates/portfolio/backtester.html` | Issues 1,2,3a,3b,3c,3d,4,5,6,9,10,11,12,13,14d |
| `apps/portfolio/services/backtester_v2.py` | Issues 8,10,12,13,3c,3d |
| `apps/portfolio/services/pe_adapter.py` | Issues 6,7 |
| `apps/portfolio/views.py` | Issues 3c,14b |
| `apps/portfolio/models.py` | Issue 14a (new model) |
| `apps/portfolio/urls.py` | Issue 14c (new URLs) |
| `templates/portfolio/strategies.html` | Issue 14e (new page) |
| Migration file (auto-generated) | Issue 14a |

---

## Technical Notes

### nsepython date format
The `index_pe_pb_div` function expects dates as `'DD-Mon-YYYY'` (e.g., `'01-Jun-2025'`). But `pe_adapter.py` formats them as `'%d-%m-%Y'` (`'01-06-2025'`). **This is the likely root cause of the JSONDecodeError** — wrong date format in the payload causes niftyindices.com to return an HTML error page instead of JSON. Fix: use `from_date.strftime("%d-%b-%Y")` (e.g., `01-Jun-2025`).

### wbgapi location
wbgapi is installed in `venv/Lib/site-packages/wbgapi`. It is available when Django runs with the venv Python. The issue was only in `manage.py shell` which was using system Python — not relevant for production.

### Sharpe units
All Sharpe/Sortino inputs in `backtester_v2.py` use decimal rates (not %). `RF_ANNUAL = 0.065 = 6.5%`. `xirr_raw` = decimal (from `_compute_xirr` which returns decimal). `vol` from `_compute_metrics` = decimal (daily std × √252). The formula `(xirr_raw - RF_ANNUAL) / vol` is correct in principle but may give near-zero due to leading-zero portfolio values. Trim first.

### Contribution % chart
`renderContributionChart` is called from `renderAllResults(data)`. If `data.per_asset` is empty or all `contribution_pct` are 0, the chart shows empty bars. The real fix is ensuring `current_val > 0` for each asset in `_build_per_asset_summary`.
