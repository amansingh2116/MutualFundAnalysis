# Data Pipeline & Commands Guide

This document details the data pipeline architecture for the **MutualFundAnalysis** project.

## Fund Universe Scope

The platform is strictly scoped to **Open-Ended Direct Growth mutual funds + all ETFs** only:
- **~2,280+ Open-Ended Direct Growth schemes & ETFs** — Close-Ended schemes, Interval funds, regular plans, and IDCW/dividend plans are excluded platform-wide

This is enforced at **two layers**:
1. **`build_scheme_master`** — Imports schemes matching `is_open_ended_scheme(stype, name) AND (is_etf_scheme(name) OR is_direct_growth(plan_col, option_col))` from AMFI's NAVAll.txt. As of mid-2026, AMFI's format includes explicit Plan and Option columns; the parser uses these directly and falls back to name heuristics for legacy format. Any scheme not matching is immediately discarded.
2. **`populate_screener`** — Filters `Q(is_direct=True, plan="GROWTH") | Q(is_etf=True)` and excludes `Close Ended` & `Interval` schemes, providing a second hard gate.

Search, browse, screener, category analysis, calculators, and all tools apply the same filter — **no Close-Ended, Interval, regular, dividend, or IDCW options are ever shown.**

> [!NOTE]
> **AMFI Format Change (mid-2026):** AMFI changed NAVAll.txt from 6 columns to 8 columns, adding explicit `Plan` and `Option` fields. The `AMFIAdapter._parse_navall()` method auto-detects this via the header line and populates `plan_col`/`option_col` accordingly. Both `build_scheme_master` and `get_amfi_scheme_list()` (search autocomplete) use these explicit fields, with name-heuristic fallback for old format.

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
**Purpose:** The heaviest and most important command. Loops through all ~2,300 Direct Growth + ETF funds, downloads NAVs from `mfapi.in`, fetches metadata (AUM, expense ratio) from `captnemo.in`, computes all risk and return metrics (trailing, rolling, max drawdown, Sharpe, Sortino), scores the fund out of 100, and saves a `FundScreenerSnapshot` and `FundModelScore`.

**Incremental NAV Ingestion (key feature):**
The pipeline is smart about NAV downloads:
- **Existing fund** (has NAV history in DB): calls `GET /mf/{code}?startDate=<last_date+1>&endDate=<today>` — only new rows downloaded. Daily re-runs fetch 1–2 rows per fund.
- **New fund** (no history in DB) or `--force-nav`: downloads full history.
- **Empty incremental response** (no new trading days since last date): counted as success, not an error.

**Features:**
- **Retry Phase:** At the end of the main loop, funds that failed NAV or metadata fetching are automatically retried once.
- **Failure Report:** Funds that still failed after retry are written to `media/reports/failed_funds_report.json`.
- **Graceful time limit:** `--time-limit-minutes=N` exits cleanly at N minutes so downstream steps (like `sync_content`) always run.

**When to run:** Weekly (automated via GitHub Actions Mon–Sat).

**Command-line arguments:**
- `--limit=N`: Process only N funds (useful for testing).
- `--offset=N`: Skip the first N funds in the ordered queryset. Combined with `--limit` gives a precise contiguous batch (e.g. `--offset=384 --limit=384` = Tuesday batch).
- `--amfi=CODE`: Process one specific fund.
- `--skip-nav`: Skip downloading new NAVs.
- `--skip-metadata`: Skip downloading metadata (AUM/expense ratio).
- `--skip-analytics`: Skip computing the heavy math metrics.
- `--skip-model-score`: Skip calculating the 100-point fund score.
- `--skip-home-dashboard`: Skip home dashboard update at the end.
- `--skip-analytics-if-no-new-nav`: Skip analytics for any fund that received no new NAV rows. Useful on weekends/holidays.
- `--force-nav`: Force re-download of full NAV history (ignores incremental logic).
- `--force-metadata`: Force re-download of metadata even if recent.
- **`--resume`**: Skip funds already processed (checks `FundScreenerSnapshot.updated_at`).
- **`--resume-hours=N`**: Window in hours for resume detection (default 24). Use 23 for same-day re-run safety.
- **`--start-from=CODE`**: Skip all funds with `amfi_code < CODE`.
- **`--time-limit-minutes=N`**: Stop gracefully after N minutes. Use `310` in GitHub Actions so post-processing always runs before the 6-hour hard job timeout.
- `--shard=N --num-shards=M`: Interleaved shard filter (legacy — prefer `--offset`/`--limit` for weekly batching).

```bash
# Typical full run (no limit)
python manage.py populate_screener

# Monday batch: funds 0–383
python manage.py populate_screener --offset=0 --limit=384

# Tuesday batch: funds 384–767
python manage.py populate_screener --offset=384 --limit=384

# Fast test on 50 funds
python manage.py populate_screener --limit=50

# Resume after Ctrl+C — skip already-done funds (safe restart)
python manage.py populate_screener --resume --resume-hours=23

# Resume from a specific AMFI code
python manage.py populate_screener --start-from=153000

# Run with graceful time limit (GitHub Actions safe)
python manage.py populate_screener --time-limit-minutes=310

# Re-fetch full NAV history for all funds (e.g. after DB reset)
python manage.py populate_screener --force-nav

# Skip analytics if no new NAV data (good for weekends)
python manage.py populate_screener --skip-analytics-if-no-new-nav
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
- **Interrupted `populate_screener` run:** Use `--resume --resume-hours=23` on the next run to skip already-processed funds. Or use `--start-from=<last_amfi_code>` from the last log line.
- **Category stats look wrong:** Re-run `populate_home_dashboard` after a fresh `populate_screener` to regenerate `CategorySnapshot` records. Category averages exclude funds < 1 year old.

---

## Weekly Automation via GitHub Actions

The file `.github/workflows/daily_pipeline.yml` runs **every 6 hours** (4 times per day), 365 days a year. No day-of-week logic — every run is identical.

### How it self-completes

| Run # | When | What happens |
|---|---|---|
| Run 1 | Week start, ~0h | Processes ~250–350 funds, hits 310-min limit, exits gracefully |
| Run 2 | +6h | Resumes from next stale fund, processes another ~250–350 |
| Run 3–7 | +12h to +36h | Continues until all ~2,300 funds are refreshed |
| Runs 8+ | +42h to end of week | Finds 0 stale funds (all fresh), completes in < 5 minutes 💤 |
| Next week | Monday | 7-day resume window expires → automatic full restart 🔄 |

The key mechanism: `--resume --resume-hours=167` skips any fund whose `FundScreenerSnapshot.updated_at` is newer than 167 hours (7 days). Once all funds are refreshed, every subsequent run processes 0 funds and exits immediately.

### What each run does (in order):
1. **Check data source contracts** (`check_data_sources --skip-nse`) — validates live AMFI, mfapi.in, captnemo schemas before anything writes to DB. Emits GitHub Actions warnings on format changes. `continue-on-error: true`
2. Apply pending database migrations
3. `build_scheme_master` — refresh AMFI fund universe (8-column format auto-detected)
4. `ingest_benchmarks` — incremental benchmark NAV sync
5. `populate_benchmark_returns` — benchmark analytics
6. `populate_screener --resume --resume-hours=167 --time-limit-minutes=310`
7. `sync_content` — sync PDF guides and blog posts

### Self-healing properties
- **If a run fails** (network error, API timeout): next run 6 hours later picks up automatically
- **If a run is delayed** (GitHub Actions queue): no problem — next run processes all pending funds
- **If data is added mid-week**: new funds get processed in the next run (not yet in the 7-day window)
- **No manual intervention ever needed** week to week

### Triggering Manually
Go to **GitHub → Actions → Weekly Data Pipeline → Run workflow**. Optional inputs:

| Input | Default | Description |
|---|---|---|
| `time_limit_minutes` | `310` | Stop fund pipeline after N minutes (0 = no limit) |
| `resume_hours` | `167` | Skip funds updated in last N hours (0 = reprocess all) |
| `limit` | `0` | Cap funds per run (0 = no cap; useful for quick tests) |

> **Force full re-run of all funds:** Set `resume_hours=0` to ignore the resume window and reprocess every fund. Useful after a DB reset or analytics model change.

### Required GitHub Secrets
| Secret | Description |
|---|---|
| `DATABASE_URL` | Full CockroachDB connection string |
| `SECRET_KEY` | Django secret key (same as Render) |

> **Public repo = unlimited free Actions minutes.** The pipeline runs 4x per day = ~1,440 invocations/year. With a public repository, this is completely free. Private repos are capped at 2,000 min/month, which this pipeline would exhaust.

---

## Data Portability & Export Commands

These commands are used to move data between environments (production -> local, local -> Kaggle, etc.).

### `check_data_sources`
**Purpose:** Validates live external data source schemas against known contracts. Detects API format changes (column count, key fields, value ranges) **before** the pipeline writes data to the database.

**Monitors:**
- AMFI NAVAll.txt (row count, column count, direct growth count, date/NAV parseability)
- mfapi.in (key presence, data structure, NAV count)
- captnemo.in (response shape, key fields)
- NSE benchmark (optional, `--skip-nse` for CI)

**Outputs:** `[OK]` / `[WARN]` / `[FAIL]` per check. Emits `::warning::` / `::error::` GitHub Actions annotations.

```bash
# Full check (all sources)
python manage.py check_data_sources

# Skip NSE (slow; not needed in CI)
python manage.py check_data_sources --skip-nse

# Single source
python manage.py check_data_sources --source amfi

# Fail fast on first FAIL (strict CI mode)
python manage.py check_data_sources --fail-fast
```

### `push_to_kaggle`
**Purpose:** Exports database tables to CSV files and publishes/updates a Kaggle dataset manually on demand.

**Exports:** `funds.csv`, `fund_screener.csv`, `nav_history.csv`, `benchmarks.csv`, `benchmark_returns.csv`, `trailing_returns.csv`, `risk_metrics.csv` plus a generated `README.md` and `dataset-metadata.json`.

**Credentials:** Set `KAGGLE_USERNAME` and `KAGGLE_KEY` environment variables, or create `~/.kaggle/kaggle.json` via the Kaggle website (Settings -> API -> Create Token).

```bash
# First time: create the dataset on Kaggle
python manage.py push_to_kaggle --create

# Subsequent updates
python manage.py push_to_kaggle
python manage.py push_to_kaggle --message "Data refresh Aug 2026"

# Skip large nav_history.csv (fast metadata-only update)
python manage.py push_to_kaggle --skip-nav

# Dry run: export CSVs but don't push
python manage.py push_to_kaggle --dry-run --output-dir /tmp/mf_export
```

A **GitHub Actions workflow** (`.github/workflows/publish_kaggle.yml`) also provides a manual dispatch button from the Actions tab. Required secrets: `KAGGLE_USERNAME`, `KAGGLE_KEY`, `DATABASE_URL`, `SECRET_KEY`.

### `sync_from_prod`
**Purpose:** Pulls live data from the CockroachDB production database into a local SQLite or PostgreSQL database. Useful for local development with real fund data.

```bash
# Sync all tables (funds, NAV, analytics, benchmarks)
python manage.py sync_from_prod

# Sync specific tables only
python manage.py sync_from_prod --tables funds,nav

# Sync funds created/updated after a date
python manage.py sync_from_prod --since 2026-01-01
```

### `export_data` / `import_data`
**Purpose:** Export database to portable JSON/CSV files and import them back. Useful for sharing snapshots or seeding a new environment.

```bash
# Export all data to a directory
python manage.py export_data --output-dir ./data_export

# Import from a previously exported directory
python manage.py import_data --input-dir ./data_export
```

---

## Docker Local Development

For full local testing against a real PostgreSQL database (matching production):

```bash
# First time: build image and start all services
docker compose up --build

# In another terminal: run setup commands
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm web python manage.py build_scheme_master

# Subsequent starts (no rebuild needed unless requirements.txt changed)
docker compose up

# Stop but preserve DB data
docker compose down

# Full reset (wipes DB volume)
docker compose down -v
```

**Services started:**
- `db` — PostgreSQL 16 (persistent named volume, survives restarts)
- `web` — Django dev server on http://localhost:8000
- `worker` — django-q2 background task cluster

**Settings:** Docker uses `config.settings.local_pg` which inherits `dev.py` but overrides the database to the containerized PostgreSQL. The DB host `db` resolves internally via Docker's network.

> [!TIP]
> Use `docker compose run --rm web python manage.py sync_from_prod` to populate your Docker PostgreSQL database with real production data after the initial migration.
