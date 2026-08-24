# MF Analysis — Deployment Guide

> **Production Stack:** Render.com (web service, free tier) + CockroachDB Serverless (database, free 10 GB) + GitHub Actions (weekly data pipeline, **free for public repositories**)
> **Cost:** $0 — no credit card required on any platform.

---

## Local Development (Windows / macOS / Linux)

### Step 1 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

> Chrome (for PDF generation) must be installed at the standard OS path. Download from [google.com/chrome](https://google.com/chrome).

### Step 2 — Create your `.env` file

```powershell
Copy-Item .env.example .env    # Windows
# cp .env.example .env          # Linux/macOS
```

Edit `.env` and set at minimum:

```env
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(50))">
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
```

> **Email in local dev:** All emails (account activation, password reset, contact form) are printed to the terminal console. No SMTP provider or internet connection needed for local testing.

### Step 3 — Run database migrations

```powershell
python manage.py migrate
```

### Step 4 — Create your admin user (optional)

```powershell
python manage.py createsuperuser
```

### Step 5 — Load fund data (optional for local dev)

```powershell
# Load ~2,300 fund scheme records (~2 minutes)
python manage.py build_scheme_master

# Sync PDF guides and blog posts from Resources/
python manage.py sync_content
```

### Step 6 — Start the server

```powershell
python manage.py runserver
```

Open **http://127.0.0.1:8000/**

---

## Deploy to Production (Render + CockroachDB + GitHub Actions)

### Architecture Overview

```
GitHub (public repository)
   │
   ├── Render Web Service (mfanalysis-web)
   │     ├── build.sh → installs Chromium + pip install
   │     ├── gunicorn → serves the Django app (2 workers)
   │     └── sleeps after 15 min inactivity (free tier)
   │
   ├── GitHub Actions (.github/workflows/weekly_pipeline.yml)
   │     ├── Runs Mon–Sat at 8:30 PM UTC (2 AM IST)
   │     ├── Each day processes 1 of 6 batches (~384 funds)
   │     ├── FREE for public repos (unlimited minutes)
   │     └── Writes directly to CockroachDB
   │
   └── CockroachDB Basic (database)
         ├── Free forever — 10 GB storage
         ├── PostgreSQL wire-compatible (psycopg2 works directly)
         └── Serverless — scales to zero when idle
```

> ⚠️ **Public Repository Required:** The GitHub Actions pipeline uses ~1,860 min/month. Private repos are capped at 2,000 min/month (would be fine, but barely). Public repos have **unlimited free minutes**. The repository should be public.

---

### Phase 1 — Set Up CockroachDB (10 minutes)

**1.1 Create a CockroachDB account**

Go to [cockroachlabs.cloud](https://cockroachlabs.cloud) → **Sign up**
- Use Google or GitHub login — no credit card required.

**1.2 Create a free cluster**

- Dashboard → **Create Cluster**
- Select **Basic** (free tier, 10 GB)
- Choose a region: **GCP us-east1** or **AWS ap-south-1** (India — lower latency)
- Cluster name: `mfanalysis`
- Click **Create Cluster**

**1.3 Create a database user**

When prompted after cluster creation:
- Username: `mfanalysis`
- Password: generate a strong random password and **save it somewhere safe**

**1.4 Get the connection string**

Cluster dashboard → **Connect** → **Connection string**

It will look like:
```
postgresql://mfanalysis:<PASSWORD>@mfanalysis-abc123.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
```

Copy this entire string — you will paste it into Render as `DATABASE_URL`.

---

### Phase 2 — Push to GitHub

**2.1 Ensure the repository is public**

GitHub → Settings → Danger Zone → **Change repository visibility** → **Make public**

This gives you **unlimited free GitHub Actions minutes**.

**2.2 Push all code changes**

```powershell
git add -A
git commit -m "feat: production-ready deployment"
git push origin main
```

---

### Phase 3 — Set Up Render (20 minutes)

**3.1 Create a Render account**

Go to [render.com](https://render.com) → **Sign up with GitHub**
Use the same GitHub account your repository is on.

**3.2 Deploy via Blueprint**

1. Render dashboard → **New** → **Blueprint**
2. Connect your GitHub account → select the `MutualFundAnalysis` repository
3. Render reads `render.yaml` automatically
4. Click **Apply**

**3.3 Set Environment Variables — Web Service**

Render dashboard → `mfanalysis-web` → **Environment** tab

Add each variable:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Full CockroachDB connection string from Phase 1 |
| `SECRET_KEY` | Run `python -c "import secrets; print(secrets.token_urlsafe(50))"` locally |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.onrender.com` |
| `RF_ANNUAL_RATE` | `0.065` |
| `DEFAULT_FROM_EMAIL` | your email address (e.g. `yourname@gmail.com`) |
| `CONTACT_RECIPIENT_EMAIL` | your inbox for contact form messages |

> Leave `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` blank for now. The app works without them — email delivery will fail silently until you configure SMTP (Phase 6).

**3.4 Trigger the first deploy**

Click **Manual Deploy** → **Deploy Latest Commit** on `mfanalysis-web`.

Wait 5–8 minutes (Chromium install + pip install). Build runs:
```
chmod +x build.sh && ./build.sh
python manage.py migrate --fake-initial --no-input
python manage.py collectstatic --no-input
```

---

### Phase 4 — Add GitHub Actions Secrets

The pipeline writes directly to CockroachDB. It needs the same secrets.

GitHub → repository → **Settings** → **Secrets and variables** → **Actions**

Add:

| Secret name | Value |
|---|---|
| `DATABASE_URL` | Same CockroachDB connection string |
| `SECRET_KEY` | Same secret key |

---

### Phase 5 — First Data Load (Initial Setup)

> This runs the **initial setup pipeline** — a one-time operation that loads all ~2,300 funds and their complete NAV history. Takes 3–6 hours total via GitHub Actions.

**Option A — Trigger via GitHub Actions (recommended)**

GitHub → Actions → **Initial Setup Pipeline** → **Run workflow**

The pipeline runs these steps automatically:
1. `build_scheme_master` — loads ~2,300 fund records
2. `ingest_benchmarks` — loads 51 benchmark indices  
3. `populate_benchmark_returns` — computes benchmark analytics
4. `populate_screener` — **THE BIG ONE:** downloads full NAV history for all funds (~4–6 hours on first run)
5. `sync_content` — syncs PDF guides and blog posts

**Option B — Render Shell (for quick testing)**

Render dashboard → `mfanalysis-web` → **Shell** tab:

```bash
# 1. Create admin account
python manage.py createsuperuser

# 2. Load 50 funds for a quick demo (~3-5 min)
python manage.py build_scheme_master
python manage.py populate_screener --limit=50
python manage.py sync_content
```

> To track progress, go to **Data Status** in the sidebar (`/data-status/`) — it shows coverage %, last update times, and the weekly batch schedule.

---

### Phase 6 — Configure Anti-Sleep (5 minutes)

Render free web services sleep after **15 minutes of inactivity** (30–60 second cold start on next request).

**Use UptimeRobot (free):**

1. Go to [uptimerobot.com](https://uptimerobot.com) → Create free account
2. **Add New Monitor**:
   - Type: **HTTP(s)**
   - Friendly Name: `MF Analysis Keepalive`
   - URL: `https://your-app-name.onrender.com/`
   - Monitoring Interval: **Every 14 minutes**
3. Click **Create Monitor**

---

### Phase 7 — Configure Email (Optional, when ready)

> The app works without email — password resets go to Render logs. Set this up when you want real email delivery for users.

**Using Sender.net (15,000 free emails/month):**

1. [sender.net](https://sender.net) → Create free account → Verify sender email
2. Dashboard → **SMTP Settings** → copy Host, Port, Username, Password

**Using Gmail App Password:**

1. Google Account → Security → 2-Step Verification (must be enabled)
2. App Passwords → Generate new → name it "MF Analysis"
3. Copy the 16-character password

**Add to Render Environment (web service only):**

| Variable | Sender.net | Gmail |
|---|---|---|
| `EMAIL_HOST` | `smtp.sender.net` | `smtp.gmail.com` |
| `EMAIL_HOST_USER` | SMTP username | Gmail address |
| `EMAIL_HOST_PASSWORD` | SMTP password | 16-char App Password |

---

## Verification Checklist

After deploy and data load, test these URLs:

| URL | What to verify |
|---|---|
| `/` | Home dashboard loads, benchmark monitor shows data, data freshness bar visible |
| `/funds/` | Category list with counts |
| `/screener/` | Fund screener with scores (0–100) and filters working |
| `/funds/120503/` | Fund detail page with all tabs loading |
| `/register/` | Registration form submits, check Render logs for activation email |
| `/accounts/login/` | Login redirects correctly |
| `/accounts/password_reset/` | Branded password reset page (not Django admin) |
| `/calculators/` | Calculator hub loads |
| `/portfolio/` | Portfolio section accessible after login |
| `/backtester/` | Strategy backtester loads |
| `/learn/resources/` | PDF guides and blog posts appear |
| `/data-status/` | Data Status dashboard shows coverage and batch cycle |
| `/admin/` | Admin panel accessible (redirect from `/admin/password_reset/` goes to our page) |

---

## Management Commands Reference

| Command | What it does | When to Run |
|---|---|---|
| `build_scheme_master` | Loads ~2,300 AMFI direct growth / ETF schemes | Initial setup; monthly to pick up new funds |
| `sync_content` | Syncs PDF guides and blogs from `Resources/` to the database | After adding new PDFs/blogs; daily pipeline |
| `ingest_benchmarks` | Incremental NAV sync for 51 benchmark indices | Daily (automated via GitHub Actions) |
| `populate_benchmark_returns` | Computes trailing/rolling returns for benchmarks | Daily (automated) |
| `populate_screener` | **Core pipeline:** NAV sync + metadata + analytics + 100-point scoring | Weekly batches (Mon–Sat via GitHub Actions) |
| `populate_home_dashboard` | Aggregates category stats and quartile rankings | Auto-runs inside `populate_screener` |
| `createsuperuser` | Creates an admin account | Once, after first deploy |

---

## Weekly Pipeline — How It Works

The pipeline runs **every 6 hours** (4 times/day, 365 days/year) — no day-of-week logic:

```
Run 1  (Week start, +0h):  ~250–350 stale funds processed → 5h 10min limit → exits
Run 2  (+6h):              Resumes from next stale fund
Run 3–7 (+12h–36h):        Continues until all ~2,300 funds refreshed ✅
Runs 8+ (+42h – week end): Finds 0 stale funds → completes in < 5 min 💤
Next Monday:               7-day window expires → full automatic restart 🔄
```

Each run uses `--resume --resume-hours=167` which skips funds updated in the last 7 days. Each run exits gracefully at 5h 10min (`--time-limit-minutes=310`) so `sync_content` always runs.

**Manual run (bypass schedule):**  
GitHub → Actions → **Weekly Data Pipeline** → **Run workflow**  
Use `resume_hours=0` to force-reprocess all funds (e.g. after a DB reset or scoring model change).

---

## Features Status

| Feature | Status | Notes |
|---|---|---|
| User registration (email required) | ✅ Working | Email verification sent on sign-up |
| Email verification on sign-up | ✅ Working | Console in dev, SMTP in prod |
| Login with rate limiting (5/min) | ✅ Working | IP-based, 429 on excess |
| Auto-activate stuck inactive accounts | ✅ Working | Recovers from prior SMTP failures |
| Forgot password / password reset | ✅ Working | Uses branded page, not Django admin |
| Change password in User Settings | ✅ Working | |
| Logout | ✅ Working | POST-based (Django 5.x compatible) |
| Personal API key storage (FRED) | ✅ Working | Stored in user settings |
| Fund screener with 20+ filters | ✅ Working | |
| Fund detail page (7 tabs) | ✅ Working | |
| Fund comparison (up to 4) | ✅ Working | |
| PDF fund report (Chrome headless) | ✅ Working | Chromium via build.sh |
| 18 Financial calculators | ✅ Working | |
| Portfolio upload (CAS PDF / manual) | ✅ Working | |
| Portfolio XIRR & analytics | ✅ Working | |
| Backtester V2 | ✅ Working | |
| Strategy comparison | ✅ Working | |
| Learn section (PDF guides + blogs) | ✅ Working | |
| Benchmark monitor | ✅ Working | |
| Data Status dashboard | ✅ Working | `/data-status/` |
| Market ticker strip | ✅ Working | |
| Fund recommendations | 🚧 Draft UI | Logic in progress |
| Community feed | 🚧 Template only | Backend coming |
| Email delivery (production) | ⚙️ Needs SMTP config | See Phase 7 |
