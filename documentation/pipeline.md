# Data Pipeline Reference

This document describes all data ingestion and computation commands, their
schedule, what each produces, and which application features they enable.

---

## Pipeline Overview

```
                    ┌─────────────────────────────────────────┐
                    │              WEEKLY PIPELINE             │
                    │  (run every Sunday, or after any change) │
                    └──────────────┬──────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ingest_nav              ingest_metadata           ingest_score_trend
 (NAV history)           (AUM, expense ratio,      (score/rank snapshot
                          managers, captnemo)        per fund per week)
          │                        │
          └────────────┬───────────┘
                       ▼
               populate_screener
            (analytics: returns, risk,
             alpha, Sharpe, model score,
             FundScreenerSnapshot)
                       │
                       ▼
           populate_home_dashboard
            (CategorySnapshot,
             benchmark returns)

                    ┌─────────────────────────────────────────┐
                    │             MONTHLY PIPELINE             │
                    │   (run 5th–10th of month, after SEBI     │
                    │    publishes portfolio disclosures)       │
                    └──────────────┬──────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ingest_holdings         ingest_aum_snapshots     ingest_industry_inflows
 (Holding, Sector,          (SchemeAumSnapshot         (IndustryInflow
  MarketCapAllocation)       per fund per month)         from AMFI)
```

---

## Commands Reference

### Weekly Commands

#### `ingest_nav` — NAV History

```bash
docker compose exec web python manage.py ingest_nav
```

- **What it does**: Downloads NAV history for all active schemes from mfapi.in
- **Writes to**: `NavEntry` (via DB or in-memory cache for runtime)
- **Run**: Every Sunday
- **Enables**: All return calculations, rolling returns, risk metrics

---

#### `ingest_metadata` — Fund Metadata

```bash
docker compose exec web python manage.py ingest_metadata
```

- **What it does**: Fetches AUM, expense ratio, managers, category from mf.captnemo.in
- **Writes to**: `SchemeMeta`, updates `Scheme.aum_cr`, `Scheme.expense_ratio`
- **Run**: Weekly (Sunday, after `ingest_nav`)
- **Enables**: Fund detail page metadata, screener filters, AUM data for snapshots

---

#### `ingest_score_trend` — Score & Rank Snapshots (Weekly)

```bash
docker compose exec web python manage.py ingest_score_trend
docker compose exec web python manage.py ingest_score_trend --date 2026-08-18  # specific week
docker compose exec web python manage.py ingest_score_trend --force            # overwrite week
```

- **What it does**: Snapshots each fund's current model score + category rank into `FundScoreTrend`
- **Writes to**: `FundScoreTrend` (keeps last 52 weeks, auto-prunes older)
- **Depends on**: `FundModelScore` + `FundScreenerSnapshot` (run `populate_screener` first)
- **Run**: Weekly (Sunday, after `populate_screener`)
- **Enables**:
  - Fund Detail → **Score Trend** chart (Fund Score tab)
  - AMC Analysis → **Score Trend** tab

---

#### `populate_screener` — Analytics Computation

```bash
docker compose exec web python manage.py populate_screener
docker compose exec web python manage.py populate_screener --limit 50  # test subset
```

- **What it does**: Computes trailing returns, rolling returns, risk metrics, alpha, Sharpe, model
  score; updates `FundScreenerSnapshot` and `FundModelScore` for every active fund
- **Depends on**: NAV data (run `ingest_nav` first), `SchemeMeta` (run `ingest_metadata` first)
- **Run**: Weekly (after `ingest_nav` + `ingest_metadata`)
- **Enables**: Screener, Fund Score tab metrics, AMC analytics stats

---

#### `populate_home_dashboard` — Category & Benchmark Snapshots

```bash
docker compose exec web python manage.py populate_home_dashboard
```

- **What it does**: Aggregates `FundScreenerSnapshot` into `CategorySnapshot`; computes
  benchmark return strips
- **Depends on**: `populate_screener` having run first
- **Run**: Weekly (after `populate_screener`)
- **Enables**: Category Analysis page, Home page Category section

---

### Monthly Commands

Run these around the **5th–10th of each month**, after SEBI publishes the previous month's
portfolio disclosures (usually available by the 7th for most AMCs).

---

#### `ingest_holdings` — Portfolio Disclosures (MONTHLY KEY COMMAND)

```bash
# Full run (finapi first, yahoo fallback)
docker compose exec web python manage.py ingest_holdings

# Resume interrupted run
docker compose exec web python manage.py ingest_holdings --resume

# Test on first 20 funds
docker compose exec web python manage.py ingest_holdings --limit 20 -v 2

# Single fund (for testing / re-ingesting one fund)
docker compose exec web python manage.py ingest_holdings --amfi 120503

# Force re-fetch even if data already exists for this month
docker compose exec web python manage.py ingest_holdings --force

# Specific month (defaults to current month's 1st)
docker compose exec web python manage.py ingest_holdings --date 2026-07-01

# Slower to be extra polite to the API
docker compose exec web python manage.py ingest_holdings --delay 1.0
```

**Sources (in priority order):**

1. **Morningstar REST API** (`api-global.morningstar.com`) — Full holdings + sectors + asset
   allocation via plain HTTP using `Scheme.morningstar_id` (SecId starting with F0).
   This is the same API that powers the fund detail Portfolio tab in `runtime.py`.
   **Requires `morningstar_id` to be pre-populated** (run `build_mstar_ids` first).
   Retries on 429 with exponential backoff.
2. **yahooquery** — fallback for ETFs or new funds without a `morningstar_id`.
   Returns top-10 holdings + sector weights only.
3. **CapClassifier** — runs after either source succeeds. Maps equity stock names →
   Large/Mid/Small cap via rapidfuzz fuzzy matching against `data/nifty_caplist.json`.

> **Note on finapi**: `finapi.upvaly.com` previously returned full portfolio data
> but their API has since dropped the holdings fields. The source is retained in the
> DB for old data but no longer usable for fresh ingestion.

> **Note on mstarpy Selenium**: removed from ingestion. The Morningstar data is now
> fetched directly from the REST API (no browser needed), provided `morningstar_id`
> is populated via the one-time `build_mstar_ids` command.

**Prerequisites:**
```bash
# One-time setup: populate morningstar_id for all active equity/hybrid funds
# Requires Chrome/Selenium (run on a machine with a display or headless Chrome)
docker compose exec web python manage.py build_mstar_ids
# After this, ingest_holdings uses pure-HTTP REST API with no browser
```

**Writes to:**
- `Holding` — all stock/debt/cash positions per fund per month
- `SectorAllocation` — sector weights per fund per month
- `MarketCapAllocation` — large/mid/small split per fund per month

**Retains**: Last 3 months of data (not auto-pruned; old months persist)

**Enables:**
- Fund Detail → **Portfolio tab** (holdings table, sector pie, cap blend)
- Fund Detail → **Portfolio tab** → cap trend & sector trend over time
- AMC Analysis → **Portfolio Insights** tab (top holdings, sectors, cap blend, exits)
- AMC Analysis → **Portfolio Intelligence** tab data enrichment
- Category Analysis → portfolio composition metrics

---

#### `ingest_aum_snapshots` — Monthly AUM Trend Data

```bash
docker compose exec web python manage.py ingest_aum_snapshots
docker compose exec web python manage.py ingest_aum_snapshots --date 2026-07-01
docker compose exec web python manage.py ingest_aum_snapshots --force
```

- **What it does**: Snapshots current AUM from `SchemeMeta.aum` into `SchemeAumSnapshot`
  for every active scheme
- **Depends on**: `ingest_metadata` having run first (to populate `SchemeMeta.aum`)
- **Writes to**: `SchemeAumSnapshot` (one row per scheme per month)
- **Run**: Monthly (after `ingest_metadata`)
- **Enables**:
  - Fund Detail → **Overview** → AUM Trend chart
  - AMC Analysis → **Portfolio Insights** → AUM Trend chart

---

#### `ingest_industry_inflows` — AMFI Industry Flows

```bash
docker compose exec web python manage.py ingest_industry_inflows --months 6
```

- **What it does**: Scrapes AMFI monthly industry flow reports (gross purchase, redemption,
  net inflow, total AUM by category group: Equity, Debt, Hybrid, etc.)
- **Writes to**: `IndustryInflow`
- **Run**: Monthly (data available ~10th of following month)
- **Enables**: Home page → **Industry Capital Flows** section

---

### One-Time / On-Demand Commands

#### `update_nifty_caplist` — Refresh Cap Classification List

```bash
docker compose exec web python manage.py update_nifty_caplist
```

- **Run when**: Quarterly SEBI rebalancing of Nifty indices (March, June, Sep, Dec)
- **Writes to**: `data/nifty_caplist.json`
- **Enables**: Accurate Large/Mid/Small classification in `ingest_holdings`

---

#### `build_scheme_master` — Rebuild Scheme Master from AMFI

```bash
docker compose exec web python manage.py build_scheme_master
```

- **Run when**: New fund houses or schemes appear; AMFI adds new codes

---

## Full Run Sequence

### First-Time Setup (empty DB)

```bash
# 1. Build scheme master
docker compose exec web python manage.py build_scheme_master

# 2. Fetch NAV history
docker compose exec web python manage.py ingest_nav

# 3. Fetch fund metadata (AUM, expense ratio, managers)
docker compose exec web python manage.py ingest_metadata

# 4. Compute screener analytics (returns, risk, model score)
docker compose exec web python manage.py populate_screener

# 5. Build dashboard snapshots (categories, benchmarks)
docker compose exec web python manage.py populate_home_dashboard

# 6. Score trend (weekly snapshot)
docker compose exec web python manage.py ingest_score_trend

# 7. Monthly portfolio disclosures (takes ~30–60 min for all funds)
docker compose exec web python manage.py ingest_holdings --resume

# 8. AUM trend snapshots
docker compose exec web python manage.py ingest_aum_snapshots

# 9. Industry flows
docker compose exec web python manage.py ingest_industry_inflows --months 6
```

### Weekly Routine (every Sunday)

```bash
docker compose exec web python manage.py ingest_nav
docker compose exec web python manage.py ingest_metadata
docker compose exec web python manage.py populate_screener
docker compose exec web python manage.py populate_home_dashboard
docker compose exec web python manage.py ingest_score_trend
```

### Monthly Routine (5th–10th of each month)

```bash
docker compose exec web python manage.py ingest_holdings --resume
docker compose exec web python manage.py ingest_aum_snapshots
docker compose exec web python manage.py ingest_industry_inflows --months 1
```

---

## Features → Data Dependencies

| Feature | Data Required | Command |
|---|---|---|
| Fund Detail: Returns, Risk, Sharpe | NAV history | `ingest_nav` + `populate_screener` |
| Fund Detail: Expense ratio, AUM, Managers | SchemeMeta | `ingest_metadata` |
| Fund Detail: Holdings table | Holding | `ingest_holdings` |
| Fund Detail: Sector pie chart | SectorAllocation | `ingest_holdings` |
| Fund Detail: Cap blend chart | MarketCapAllocation | `ingest_holdings` |
| Fund Detail: AUM trend | SchemeAumSnapshot | `ingest_aum_snapshots` |
| Fund Detail: Score trend | FundScoreTrend | `ingest_score_trend` |
| AMC Portfolio: Top holdings | Holding | `ingest_holdings` |
| AMC Portfolio: Sector allocation | SectorAllocation | `ingest_holdings` |
| AMC Portfolio: Cap blend | MarketCapAllocation | `ingest_holdings` |
| AMC Portfolio: AUM trend | SchemeAumSnapshot | `ingest_aum_snapshots` |
| AMC Portfolio: Exits | Holding (2 months) | `ingest_holdings` (2 runs) |
| Category Analysis: Cards | CategorySnapshot | `populate_home_dashboard` |
| Home: Industry Capital Flows | IndustryInflow | `ingest_industry_inflows` |
| Screener: All metrics | FundScreenerSnapshot | `populate_screener` |
