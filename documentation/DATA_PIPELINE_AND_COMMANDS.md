# Data Pipeline & Commands Guide

This document details the data pipeline architecture for the **MutualFundAnalysis** project. Since there are over 14,000 mutual funds in India, the application uses an **on-demand runtime** combined with a **background screener pipeline** to ensure the platform remains fast without needing terabytes of local storage.

## The Core Concept
- **Search & Browsing:** Real-time search uses an AMFI cache. Fund detail pages (`/funds/<amfi_code>/`) fetch NAVs and metadata dynamically at runtime and compute analytics in memory.
- **Screener & Dashboard:** To filter thousands of funds instantly, a denormalised snapshot table (`FundScreenerSnapshot`) is pre-calculated via background commands. This is what populates the Screener, Compare tools, and Home Page.

---

## Command Reference

### 1. `build_scheme_master`
**Purpose:** Fetches the complete list of registered mutual funds from AMFI.
**When to run:** Initial setup, or monthly to catch newly launched funds.
**Action:** Overwrites/updates the `funds_scheme` table.

```bash
python manage.py build_scheme_master
```

### 2. `ingest_benchmarks`
**Purpose:** Fetches metadata and historical daily NAV values for the exact whitelist of 42 required benchmark indices defined in `benchmark_config.py`.
**When to run:** Daily, before updating fund snapshots.
**Action:** Tries the **NSE Direct API** first, and immediately falls back to **Yahoo Finance** on failure. Updates `BenchmarkIndex` and `BenchmarkNAV`. Features SQLite lock resilience.

```bash
python manage.py ingest_benchmarks
```

### 3. `populate_benchmark_returns`
**Purpose:** Computes standard analytics (1M, 3M, 6M, 1Y, 3Y, 5Y, etc., and calendar returns) for all benchmark indices based on the NAVs fetched above.
**When to run:** Daily, immediately after `ingest_benchmarks`.
**Action:** Populates the `BenchmarkReturns` table which powers the Home Dashboard Benchmark Monitor.

```bash
python manage.py populate_benchmark_returns
```

### 4. `populate_screener` (The Master Pipeline)
**Purpose:** This is the heaviest and most important command. It loops through active funds, downloads their NAVs from `mfapi.in`, fetches their metadata (AUM, expense ratio) from `captnemo.in`, computes all risk and return metrics (trailing, rolling, max drawdown, Sharpe, Sortino), scores the fund out of 100, and saves a `FundScreenerSnapshot` and `FundModelScore`.
**When to run:** Daily (usually overnight).

**Command line arguments:**
- `--limit=N`: Process only N funds (useful for testing).
- `--amfi=CODE`: Process one specific fund.
- `--direct-growth-only`: (Default: True) Skips regular and dividend plans to save time, as platform analysis focuses on Direct Growth.
- `--skip-nav`: Skip downloading new NAVs.
- `--skip-metadata`: Skip downloading metadata (AUM/expense ratio) from Captnemo.
- `--skip-analytics`: Skip computing the heavy math metrics.
- `--skip-model-score`: Skip calculating the 100-point fund score.
- `--skip-home-dashboard`: By default, this command triggers the home dashboard update at the end. Use this flag to prevent that.
- `--force-nav`: Force re-download of NAVs even if local DB is recent.
- `--force-metadata`: Force re-download of metadata even if recent.

```bash
# Typical daily run
python manage.py populate_screener

# Fast test run on 50 funds
python manage.py populate_screener --limit=50
```

### 5. `populate_home_dashboard`
**Purpose:** Aggregates the completed `FundScreenerSnapshot` table to create `CategorySnapshot` records (which contain average returns and average risk metrics per sub-category) and assigns Quartile Rankings (Q1-Q4) to every fund within its category.
**When to run:** Automatically runs at the end of `populate_screener`. Run manually if you've altered the database manually.

```bash
python manage.py populate_home_dashboard
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

For a production environment, you should set up a cron job or background scheduler (like GitHub Actions + Render Deploy Hook) to run these commands in the following order every night at ~11:00 PM IST (when AMFI and mfapi update):

1. `python manage.py ingest_benchmarks`
2. `python manage.py populate_benchmark_returns`
3. `python manage.py populate_screener`
4. `python manage.py sync_content` whenever Learn resources or blog files change

*Because `populate_screener` handles its own orchestration, it will automatically compute the analytics, build the scores, and cascade into `populate_home_dashboard` at the very end.*

---

## Troubleshooting

- **Rate Limits (mfapi / captnemo):** The pipeline uses `science_skills_common.http_client` to respect rate limits with exponential backoff. If you get 429 errors, let the script pause automatically.
- **Missing Benchmarks in Rolling Charts:** If an index (e.g., `NIFTYGSCOMPOSITE.NS`) is missing data on Yahoo Finance, the `ingest_benchmarks` script skips it. The platform frontend automatically falls back to proxy benchmarks (like Nifty 50 or NIFTY COMPOSITE DEBT INDEX) with UI alerts.
- **SQLite Database Locks:** If you run multiple heavy pipelines simultaneously on SQLite, you may encounter `database is locked` errors. Run commands sequentially. Use PostgreSQL for production.
- **OneDrive-backed SQLite files:** If `db.sqlite3` is inside OneDrive and a migration leaves a hot `db.sqlite3-journal`, Django may show `sqlite3.OperationalError: disk I/O error`. Close runserver/Python processes and allow OneDrive to finish syncing before retrying `migrate`; do not delete the journal unless you have a database backup or are comfortable rebuilding the local DB.
