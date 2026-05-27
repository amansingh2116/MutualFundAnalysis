# MF Analysis — Deployment Guide

> **Goal:** Get the app running locally for development, then deploy to [Render.com](https://render.com) for public access with login.

---

## Local Development (Windows)

### Step 1 — Install Python dependencies

Open a terminal in the project folder and run:

```powershell
pip install -r requirements.txt
```

> If you get `weasyprint` install errors on Windows, skip it for now — PDF export won't work but everything else will.

### Step 2 — Create your `.env` file

Create a file called `.env` in the root of the project:

```env
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=your-secret-key-change-this-to-any-long-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
RF_ANNUAL_RATE=0.065
```

> For `SECRET_KEY`, run this in Python: `import secrets; print(secrets.token_urlsafe(50))`

### Step 3 — Run database migrations

```powershell
python manage.py migrate --settings=config.settings.dev
```

### Step 4 — Create your admin user

```powershell
python manage.py createsuperuser --settings=config.settings.dev
```

### Step 5 — Load fund data (takes ~2 minutes)

```powershell
python manage.py build_scheme_master --settings=config.settings.dev
```

This downloads ~14,000 fund schemes from the AMFI API.

### Step 6 — Start the server

```powershell
python manage.py runserver --settings=config.settings.dev
```

Open your browser at **http://127.0.0.1:8000/**

---

## Quick Data Load (After First Setup)

To get meaningful data for a few funds:

```powershell
# Ingest latest NAVs for all schemes (~5 min)
python manage.py ingest_nav --settings=config.settings.dev

# Compute analytics (trailing returns, risk metrics) for top 100 funds
python manage.py compute_analytics --limit=100 --settings=config.settings.dev
```

---

## Deploy to Render.com (Free Hosting)

### Prerequisites
- GitHub account with this project pushed to a public/private repo
- [Render.com](https://render.com) account (free)

### Step 1 — Push to GitHub

```powershell
git init
git add .
git commit -m "Initial MF Analysis app"
git remote add origin https://github.com/YOUR_USERNAME/MutualFundAnalysis.git
git push -u origin main
```

### Step 2 — Create a New Web Service on Render

1. Go to [render.com/new](https://render.com/new) → **Blueprint**
2. Connect your GitHub repo
3. Render will auto-detect `render.yaml` and create:
   - **Web Service** (Django app)
   - **Worker** (background task queue for analytics)
   - **PostgreSQL database** (free tier)

### Step 3 — Set Environment Variables on Render

In the Render dashboard → your web service → **Environment**:

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | (generate a random 50-char string) |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.onrender.com` |

> `DATABASE_URL` is automatically set by Render from the linked database.

### Step 4 — Trigger First Deploy

Render will automatically:
1. Install `requirements.txt`
2. Run `python manage.py migrate`
3. Run `python manage.py collectstatic`
4. Start gunicorn

Your app will be live at `https://mfanalysis-web.onrender.com` (or similar).

### Step 5 — Create superuser on Render

In Render dashboard → your web service → **Shell**:

```bash
python manage.py createsuperuser
```

---

## App Architecture Overview

```
Browser
  │
  ├── Django Templates (HTML) ← HTMX for partial updates
  │     ├── base.html (sidebar + topbar)
  │     ├── funds/ (home, category list, detail, PDF export)
  │     ├── screener/ (filter + results)
  │     ├── calculators/ (hub + 8 tools)
  │     ├── portfolio/ (upload, dashboard, overlap)
  │     └── recommendations/ (questionnaire — draft)
  │
  ├── Django Views (Python)
  │     ├── apps/funds/views.py
  │     ├── apps/screener/views.py
  │     ├── apps/calculators/views.py  ← API endpoints return JSON
  │     ├── apps/portfolio/views.py
  │     └── apps/analytics/api_views.py  ← chart data endpoints
  │
  ├── Analytics Engine (pandas/numpy)
  │     └── apps/analytics/engine.py
  │         ├── Trailing CAGR (1M→SI)
  │         ├── Calendar returns
  │         ├── Rolling return stats
  │         ├── Risk metrics (Sharpe, Sortino, Beta, Alpha, etc.)
  │         └── SIP simulation (XIRR via scipy)
  │
  └── Database (SQLite dev / PostgreSQL prod)
        ├── funds.Scheme         — 14,000 AMFI schemes
        ├── funds.NAVHistory     — daily NAVs
        ├── analytics.*          — computed metrics
        ├── holdings.*           — portfolio composition
        └── portfolio.*          — user portfolios
```

---

## Available Management Commands

| Command | What it does |
|---------|-------------|
| `build_scheme_master` | Downloads all AMFI schemes |
| `ingest_nav` | Downloads latest NAVs |
| `compute_analytics` | Computes returns + risk for all funds |
| `ingest_holdings` | Fetches top holdings from Morningstar |
| `qcluster` | Starts background task worker |

---

## Features Status

| Feature | Status |
|---------|--------|
| User registration / login | ✅ Working |
| Fund search | ✅ Working |
| Fund detail page (6 tabs) | ✅ Working (needs data) |
| Fund screener with filters | ✅ Working |
| Fund comparison (up to 4) | ✅ Working |
| SIP / Lumpsum / SWP calculators | ✅ Working |
| Goal planner | ✅ Working |
| Tax calculator (STCG/LTCG) | ✅ Working |
| Step-up SIP | ✅ Working |
| XIRR calculator | ✅ Working |
| Fund overlap checker | ✅ Working (needs holdings data) |
| Portfolio upload (Excel/CSV) | ✅ Working |
| Portfolio analysis (gain/loss) | ✅ Working |
| Portfolio overlap heatmap | ✅ Working (needs holdings data) |
| PDF fund report | ✅ Working (needs weasyprint) |
| Fund recommendations | 🚧 Draft UI (logic coming) |
| Portfolio backtester | 🚧 Draft UI (logic coming) |
| Benchmark comparison | 🚧 Stub (coming) |
| Portfolio rebalancer | 🚧 Stub (coming) |
