# Data Pipeline & Commands Guide

This document details the data pipeline architecture for the **MutualFundAnalysis** project.

## Fund Universe Scope

The platform is strictly scoped to **Open-Ended Direct Growth mutual funds + all ETFs** only:
- **~2,280+ Open-Ended Direct Growth schemes & ETFs** — Close-Ended schemes, Interval funds, regular plans, and IDCW/dividend plans are excluded platform-wide

This is enforced at **two layers**:
1. **`build_scheme_master`** — Only imports schemes matching `is_open_ended_scheme(stype, name) AND (is_etf_scheme(name) OR (is_direct_scheme(name) AND is_growth_scheme(name)))` from AMFI's NAVAll.txt. Any scheme that doesn't match is immediately discarded.
2. **`populate_screener`** — Filters `Q(is_direct=True, plan="GROWTH") | Q(is_etf=True)` and excludes `Close Ended` & `Interval` schemes before iterating, providing a second hard gate.

Search, browse, screener, category analysis, calculators, and all tools apply the same filter — **no Close-Ended, Interval, regular, dividend, or IDCW options are ever shown.**

---

## The Core Concept

- **Search & Browsing:** Real-time search uses an AMFI cache pre-filtered to Direct Growth + ETF. Fund detail pages (`/funds/<amfi_code>/`) fetch NAVs and metadata dynamically at runtime and compute analytics in memory.
- **Screener & Dashboard:** To filter thousands of funds instantly, a denormalised snapshot table (`FundScreenerSnapshot`) is pre-calculated via background commands. This is what populates the Screener, Compare tools, and Home Page.

---

## Command Reference

### 1. `build_scheme_master`
**Purpose:** Fetches the complete list of registered mutual funds from AMFI.
**When to run:** Initial setup, or monthly to catch newly launched funds.
**Action:** Overwrites/updates the `funds_scheme` table. **Immediately drops any scheme that is not Direct Growth or an ETF**, keeping the base table lean.

```bash
python manage.py build_scheme_master
```

### 2. `ingest_benchmarks`
**Purpose:** Fetches metadata and historical daily NAV values for the exact whitelist of **51** required benchmark indices defined in `benchmark_config.py` (41 equity/hybrid + 10 debt/bond duration indices).
**When to run:** Daily, before updating fund snapshots.
**Action:** Uses **nselib** (which manages NSE session/cookie handling) to fetch equity indices, and immediately falls back to **Yahoo Finance** on failure. Updates `BenchmarkIndex` and `BenchmarkNAV`. Features SQLite lock resilience and incremental date-range fetching (only new rows since last DB date).

> [!NOTE]
> Debt/bond indices (NIFTY COMPOSITE DEBT INDEX, NIFTY CORPORATE BOND INDEX, etc.) are defined in the config but cannot be fetched via nselib because the NSE API returns empty data for them. These indices fall back to NIFTY 50 as a proxy in analytics, which is shown with a UI note to the user.

```bash
python manage.py ingest_benchmarks
```

### 3. `populate_benchmark_returns`
**Purpose:** Computes standard analytics (1M, 3M, 6M, 1Y, 3Y, 5Y, etc., calendar returns, and rolling return stats with **avg, median, min, max, pos_pct**) for all benchmark indices based on the NAVs fetched above.
**When to run:** Daily, immediately after `ingest_benchmarks`.
**Action:** Populates the `BenchmarkReturns` table which powers the Home Dashboard Benchmark Monitor.

```bash
python manage.py populate_benchmark_returns
```

### 4. `populate_screener` (The Master Pipeline)
**Purpose:** This is the heaviest and most important command. It loops through all ~3,000 Direct Growth + ETF funds, downloads their NAVs from `mfapi.in`, fetches their metadata (AUM, expense ratio) from `captnemo.in`, computes all risk and return metrics (trailing, rolling, max drawdown, Sharpe, Sortino), scores the fund out of 100, and saves a `FundScreenerSnapshot` and `FundModelScore`.

**Incremental NAV Ingestion (key feature):**  
The pipeline is smart about NAV downloads:
- **Existing fund** (has NAV history in DB): calls `GET /mf/{code}?startDate=<last_date+1>&endDate=<today>` — only new rows are downloaded. On a daily re-run this is typically 1-2 rows per fund.
- **New fund** (no history in DB) or `--force-nav`: downloads full history.
- **Empty incremental response** (no new trading days since last date): counted as success, not an error.

**Features:**
- **Retry Phase:** At the end of the main loop, any fund that failed NAV or Metadata fetching during the run is automatically retried once more with a short pause between retries.
- **Failure Report:** After the retry phase, any funds that still failed are written to `media/reports/failed_funds_report.json` with the AMFI code, fund name, and specific error reason — giving you full visibility over data gaps.

**When to run:** Daily (usually overnight).

**Command line arguments:**
- `--limit=N`: Process only N funds (useful for testing).
- `--amfi=CODE`: Process one specific fund.
- `--skip-nav`: Skip downloading new NAVs.
- `--skip-metadata`: Skip downloading metadata (AUM/expense ratio) from Captnemo.
- `--skip-analytics`: Skip computing the heavy math metrics.
- `--skip-model-score`: Skip calculating the 100-point fund score.
- `--skip-home-dashboard`: By default, this command triggers the home dashboard update at the end. Use this flag to prevent that.
- `--force-nav`: Force re-download of **full** NAV history (ignores incremental logic). Useful after DB reset.
- `--force-metadata`: Force re-download of metadata even if recent.
- **`--resume`**: Skip funds already processed. Checks `FundScreenerSnapshot.updated_at`; skips any fund whose snapshot is newer than `--resume-hours` (default 24h). **Use this when you restart after a Ctrl+C interruption.** Funds are always processed in `amfi_code` order so this is deterministic.
- **`--resume-hours=N`**: Window in hours for resume detection (default 24). Set to 48 if the run spans multiple days.
- **`--start-from=CODE`**: Skip all funds with `amfi_code < CODE`. Use when you know exactly which AMFI code was interrupted on (check the last log line before interruption).

```bash
# Typical full run
python manage.py populate_screener

# Fast test run on 50 funds
python manage.py populate_screener --limit=50

# Resume after Ctrl+C — skip already-done funds (safe restart)
python manage.py populate_screener --resume

# Resume from a specific fund if you know the AMFI code
python manage.py populate_screener --start-from=153000

# Run only analytics (re-use existing NAV + metadata)
python manage.py populate_screener --skip-nav --skip-metadata

# Re-fetch full NAV history for all funds (e.g. after DB reset)
python manage.py populate_screener --force-nav
```

### 5. `populate_home_dashboard`
**Purpose:** Aggregates the completed `FundScreenerSnapshot` table to create `CategorySnapshot` records (which contain average returns and average risk metrics per sub-category) and assigns Quartile Rankings (Q1-Q4) to every fund within its category.

**Important:** When computing category aggregates (averages, medians, rolling stats, risk measures), **funds with less than 1 year of NAV history (`fund_age_years < 1.0`) are excluded from all mathematical computations** to prevent young funds from skewing category statistics. These young funds still appear in the category fund list on the UI, but with blank metrics.

**When to run:** Automatically runs at the end of `populate_screener`. Run manually if you've altered the database manually.

```bash
python manage.py populate_home_dashboard

# Re-compute category snapshots without re-running quartile ranking (faster)
python manage.py populate_home_dashboard --skip-quartiles
```

### 6. `generate_screener_reports`
**Purpose:** Generates static CSVs and HTML reports of the top-performing funds based on screener snapshots.
**Output:** Saves to `media/reports/fund_screener/YYYY-MM-DD/`.

**Command line arguments:**
- `--top N`: Number of funds to include.
- `--sort FIELD`: Sort by `cagr_3y`, `rolling_3y`, `return_1y`, `sharpe`, or `aum`.

```bash
python manage.py generate_screener_reports --top 20 --sort cagr_5y
```

### 7. `sync_content`
**Purpose:** Syncs the Learn section content from local files into admin-manageable Django records.
**When to run:** After adding or editing PDF guides, project reports, markdown blogs, thumbnails, or Learn metadata.
**Action:** Updates `LearnPDFGuide` from `Resources/PDF Guides/guides.json` and `LearnBlogPost` from markdown front matter in `Resources/Blogs/*.md`.

```bash
python manage.py sync_content
```

Learn content source files:
- PDF files: `Resources/PDF Guides/pdfs/`
- PDF metadata: `Resources/PDF Guides/guides.json`
- Blogs: `Resources/Blogs/*.md`
- Blog images: usually under `Resources/Blogs/images/<blog-slug>/`

See `documentation/LEARN_CONTENT.md` for the full metadata format.

---

## Daily Operations Workflow

For a production environment the nightly pipeline runs automatically via **django-q2** as a single unified task (`daily_full_pipeline`). The scheduled task in `config/settings/dev.py` runs at **02:00 IST daily** (AMFI and mfapi.in publish NAV by ~01:30 IST).

**Automated flow (via `daily_pipeline_task.py`):**
1. `populate_screener` — incremental NAV + metadata + analytics + home dashboard (the master pipeline)
2. `ingest_benchmarks` — incremental benchmark NAV sync
3. `populate_benchmark_returns` — benchmark trailing/rolling stats

**Manual one-time execution** (run once per the order below):
```bash
# Step 1 — Fund pipeline (NAV, metadata, analytics, dashboard)
python manage.py populate_screener

# Step 2 — Benchmark data
python manage.py ingest_benchmarks

# Step 3 — Benchmark computed returns
python manage.py populate_benchmark_returns

# Optionally re-sync Learn content when files change
python manage.py sync_content
```

*Because `populate_screener` handles its own orchestration, it will automatically compute the analytics, build the scores, and cascade into `populate_home_dashboard` at the very end.*

> [!TIP]
> On daily runs, `populate_screener` typically completes much faster than the initial full run because the incremental NAV logic only downloads 1-2 new NAV rows per fund instead of thousands of historical rows.

---

## Data Integrity Guardrails

The pipeline implements strict arithmetic overflow protection to prevent `decimal.InvalidOperation` errors when saving to Django `DecimalField` columns:

| Location | Protection |
|---|---|
| `apps/analytics/engine.py` — `_sn()` | All metrics passed through this guard before ORM save. Returns `None` for NaN, Inf, or values outside `[-9999, 9999]`. |
| `apps/analytics/engine.py` — `_compute_rolling_returns` | NumPy mask clips CAGRs to `[-9999, 9999]` before statistics are computed. |
| `apps/analytics/engine.py` — `_compute_calendar_returns` | Benchmark series is clipped to fund's last NAV date to prevent spurious future-date returns. |
| `apps/analytics/engine.py` — `_compute_trailing_returns` | Benchmark clipped to `today` (fund's last NAV date) before CAGR calculation. |
| `apps/funds/screener.py` — `_decimal()` | Dynamic bounds based on field's `max_digits/decimal_places`. Large fields (AUM Cr, NAV, lump_min, sip_min) use `max_digits=12` — not the default 8. |
| `apps/benchmarks/management/commands/populate_benchmark_returns.py` — `_decimal()` | `math.isfinite()` check before Decimal conversion. |

> [!IMPORTANT]
> **Large-value decimal fields** — `aum_cr`, `nav_latest`, `sip_min`, and `lump_min` — have `max_digits=12` in the model. The `_decimal()` helper **must** be called with explicit `max_digits=12, decimal_places=2` for these fields, not the default `max_digits=8`. This is already done correctly in `screener.py` as of the v2.0 precision audit.

## Data Pipeline Diagram

```
AMFI NAVAll.txt → build_scheme_master → Scheme (DB)
                  [drops non-Direct-Growth / non-ETF immediately]
                ↓
mfapi.in (REST) → ingest_nav → NAVHistory (DB)
                ↓
captnemo.in ISIN API → ingest_metadata → SchemeMeta (DB)
                ↓
analytics/engine.py → compute_all_metrics
  → TrailingReturn (per-period; skips if fund too young for that period)
  → RollingReturn  (min/max/mean/median per window)
  → CalendarReturn
  → RiskMetrics    (3Y, 5Y, SI; skips if fund too young for that period)
                ↓
screener.py → refresh_snapshot_for_scheme → FundScreenerSnapshot (DB)
  [excess_cat_1y/3y/5y/7y computed as fund_return − category_avg_return]
                ↓
populate_home_dashboard → CategorySnapshot (DB)
  [aggregates exclude funds with fund_age_years < 1.0]
  [rolling_returns_json includes avg, median, min, max, pos_pct]
                ↓
populate_benchmark_returns → BenchmarkReturns (DB)
  [rolling_returns_json includes avg, median, min, max, pos_pct]
```

---

## Short-History Fund Handling

Funds with fewer than 252 trading days (~1 year) of NAV history are handled as follows:

| Context | Behaviour |
|---|---|
| **Analytics engine** | Computes only the metrics that are valid for the available data window. E.g. a 6-month fund gets 1M, 3M, 6M returns and SI metrics but **not** 1Y, 3Y, 5Y (those are stored as `null`). |
| **Fund screener** | Appears normally. Null metric cells display as `--`. Sortable columns treat nulls as last. |
| **Search / tools / calculators** | Appears normally. Live data is fetched; results reflect available history. |
| **Category Analysis (aggregate stats)** | **Excluded** from all averages, medians, rolling stats, and risk aggregates. Does not skew category numbers. |
| **Category fund list** | **Included** — appears in the list with fund name and blank metrics. |

This ensures the platform surface area is complete (all ~3,000 schemes visible everywhere), while aggregate statistics remain statistically meaningful.

---

## Log Interpretation Guide

When running `populate_screener`, you will see various WARNING/INFO messages. Here is what they mean:

| Log Message | Severity | Meaning | Action Needed? |
|---|---|---|---|
| `Nifty Indices chunk skipped for X ... Expecting value: line 1 column 2` | INFO | The NiftyIndices.com API returned non-JSON (HTML error page) for that historical date range. Typically happens for debt indices before ~2015 which didn't exist yet. | ❌ None — aborts after 3 consecutive failures |
| `Nifty Indices deadline exceeded for X, aborting chunk loop` | INFO | The per-benchmark fetch time limit was hit. Falls back to Yahoo Finance. | ❌ None — expected fallback |
| `[captnemo] Attempt 1/1 failed (HTTP 0): ...` | WARNING | captnemo.in dropped the connection (ISIN not in their platform). Already trying AMFI-code fallback. | ❌ None — 1 retry by design; AMFI fallback runs next |
| `[captnemo] All 2 retries failed` | WARNING | captnemo.in fully failed for this fund via AMFI-code endpoint too. Will be queued for end-of-run retry phase. | ❌ None — retry phase handles it |
| `[AMFI] snapshot error: database is locked` | ERROR | Two processes writing to SQLite simultaneously. Transient — retried automatically. | ❌ None — run commands sequentially to prevent |
| `[AMFI] mfapi.in full fetch failed: Read timed out` | WARNING | mfapi.in API timed out (15s). Automatically falls back to mftool for NAV. Also queued for end-of-run retry. | ❌ None — retry phase handles it |
| `Fund has short history (N days) — computing partial analytics` | INFO | Fund is too new (<252 trading days of NAV). Partial analytics computed; unsupported periods stored as null. | ❌ None — expected for new/interval funds |
| `Retrying N failed funds...` | WARNING | End-of-run retry phase starting. | ❌ None — automatic |
| `Final failed funds: N → Saved to media/reports/failed_funds_report.json` | ERROR | N funds could not be fetched even after retry. Check the JSON report to see which funds and why. | ⚠️ Review report if N is large |
| `Nifty Indices mapping fetch failed for X: getaddrinfo failed` | INFO | CDN subdomain `iislliveblob.niftyindices.com` not resolving. Non-critical — index name lookup only. All subsequent calls skip immediately (CDN cache). | ❌ None — cached after first failure |

---

## Failure Report

After every `populate_screener` run, if any funds fail to fetch even after the retry phase, a JSON file is created at:

```
media/reports/failed_funds_report.json
```

Format:
```json
{
  "119056": {
    "name": "SBI Nifty 50 ETF",
    "reasons": ["NAV fetch returned empty"]
  },
  "149540": {
    "name": "HDFC Multi Cap Fund Direct Growth",
    "reasons": ["Captnemo metadata empty after retry"]
  }
}
```

Use this file to:
- Identify persistent data gaps.
- Manually re-run individual funds: `python manage.py populate_screener --amfi=119056`.

---

## Troubleshooting

- **Rate Limits (mfapi / captnemo):** The pipeline has exponential backoff for Captnemo (1 retry for ISIN lookups, 2 for AMFI-code lookups). Connection drops (HTTP 0) are handled with a 2-second retry cap instead of long exponential waits. If you get persistent failures, run during off-peak hours.
- **Missing Benchmarks in Rolling Charts:** If an index is missing data on Yahoo Finance and nselib, the `ingest_benchmarks` script skips it. The platform frontend automatically falls back to proxy benchmarks (like Nifty 50 or NIFTY COMPOSITE DEBT INDEX) with UI alerts. This is expected for all 10 debt duration indices.
- **Debt Index Benchmarks:** NIFTY CORPORATE BOND INDEX and other debt indices cannot be fetched via nselib (NSE API returns empty data for these). Analytics falls back to NIFTY 50 proxy with a UI note. This is documented, expected behaviour.
- **SQLite Database Locks:** If you run multiple heavy pipelines simultaneously on SQLite, you may encounter `database is locked` errors. Run commands sequentially. Use PostgreSQL for production.
- **OneDrive-backed SQLite files:** If `db.sqlite3` is inside OneDrive and a migration leaves a hot `db.sqlite3-journal`, Django may show `sqlite3.OperationalError: disk I/O error`. Close runserver/Python processes and allow OneDrive to finish syncing before retrying `migrate`; do not delete the journal unless you have a database backup or are comfortable rebuilding the local DB.
- **Interrupted `populate_screener` run:** Use `--resume` flag on the next run to skip already-processed funds. Alternatively use `--start-from=<last_amfi_code>` from the last log line.
- **Category stats look wrong:** Re-run `populate_home_dashboard` after a fresh `populate_screener` to regenerate `CategorySnapshot` records. Category averages exclude funds < 1 year old.
