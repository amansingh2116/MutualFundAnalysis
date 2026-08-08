# MF Analysis — Deployment Guide

> **Production Stack:** Render.com (web + cron) + CockroachDB Serverless (database)
> **Cost:** $0 — no credit card required on either platform.

---

## Local Development (Windows)

### Step 1 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

> Chrome (for PDF generation) must be installed at the standard OS path. Download from [google.com/chrome](https://google.com/chrome).

### Step 2 — Create your `.env` file

```powershell
Copy-Item .env.example .env
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

### Step 5 — Load fund data

```powershell
# Load ~2,300 fund scheme records (~1 minute)
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

## Deploy to Production (Render + CockroachDB)

### Architecture Overview

```
GitHub (code + Resources/ + Actions)
   │
   ├── Render Web Service (mfanalysis-web)
   │     ├── build.sh → installs Chromium + pip install
   │     ├── gunicorn → serves the Django app
   │     └── sleeps after 15 min inactivity (free tier)
   │
   ├── GitHub Actions (daily pipeline)
   │     ├── Runs at 1:30 AM IST every day (free 2,000 mins/month)
   │     └── Runs populate_screener + ingest_benchmarks directly on CockroachDB
   │
   └── CockroachDB Basic (database)
         ├── Free forever — 10 GB storage
         ├── PostgreSQL wire-compatible (psycopg2 works directly)
         └── Serverless — scales to zero when idle
```


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

In the cluster dashboard → **Connect** → **Connection string**

It will look like:
```
postgresql://mfanalysis:<PASSWORD>@mfanalysis-abc123.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
```

Copy this entire string — you will paste it into Render as `DATABASE_URL`.

---

### Phase 2 — Commit and Push to GitHub (5 minutes)

**2.1 Commit all pending code changes**

Run in PowerShell from the project folder:

```powershell
git add apps/core/views.py `
        apps/funds/report.py `
        apps/funds/views.py `
        config/settings/base.py `
        config/settings/prod.py `
        config/urls.py `
        render.yaml `
        requirements.txt `
        build.sh `
        .env.example `
        README.md `
        documentation/DEPLOYMENT.md

git commit -m "feat: production deployment config — Render + CockroachDB, rate limiting, auth hardening"
```

**2.2 Commit the Resources folder**

The `Resources/` folder (PDF guides + blog posts) is 17 MB and must be committed to Git so it is available on Render.

```powershell
git add Resources/
git commit -m "content: commit PDF guides and blog posts for production deployment"
```

**2.3 Push to GitHub**

```powershell
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
3. Render reads `render.yaml` automatically and shows what it will create:
   - `mfanalysis-web` (web service) ✅
   - `mfanalysis-daily-pipeline` (cron job) ✅
4. Click **Apply**

**3.3 Set Environment Variables — Web Service**

Render dashboard → `mfanalysis-web` → **Environment** tab

Add each variable:

| Variable | Value |
|---|---|
| `DATABASE_URL` | The full CockroachDB connection string from Step 1.4 |
| `SECRET_KEY` | Run `python -c "import secrets; print(secrets.token_urlsafe(50))"` locally and paste the result |
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `.onrender.com` |
| `RF_ANNUAL_RATE` | `0.065` |
| `DEFAULT_FROM_EMAIL` | your email address (e.g. `yourname@gmail.com`) |
| `CONTACT_RECIPIENT_EMAIL` | your personal inbox for contact form messages |

> Leave `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` blank for now. The app works without them — emails will fail silently in prod until you configure an SMTP provider.

**3.4 Trigger the first deploy**

Click **Manual Deploy** → **Deploy Latest Commit** on `mfanalysis-web`.

Wait for the build to complete (5–8 minutes — Chromium install + pip install).

After the deploy, Render's Procfile automatically runs:
- `python manage.py migrate` — creates all database tables on CockroachDB
- `python manage.py collectstatic` — bundles static files


---

### Phase 4 — First Data Load (from Render Shell)

> This is the most important step. Do it immediately after the first successful deploy.

Render dashboard → `mfanalysis-web` → **Shell** tab

Run these commands **in order**:

```bash
# 1. Create your admin account
python manage.py createsuperuser

# 2. Load fund universe (~2,300 schemes, ~1 minute)
python manage.py build_scheme_master

# 3. Sync PDF guides and blog posts from Resources/
python manage.py sync_content

# 4. Load benchmark data (~51 indices, ~5 minutes)
python manage.py ingest_benchmarks
python manage.py populate_benchmark_returns

# 5. Full fund data pipeline — THE BIG ONE (~6-12 hours on first run)
#    Close the shell after starting — it keeps running in the background
python manage.py populate_screener
```

> **⚠️ About `populate_screener`:** Downloads NAV history for all ~2,300 funds (5–10 million rows). Takes 6–12 hours on the first run. If interrupted, run `python manage.py populate_screener --resume` to continue from where it stopped.
>
> **Tip:** Start it on a Friday evening and check Saturday morning. All 10 GB of CockroachDB's free storage easily fits your data.

**For a quick demo while the full load runs:**

```bash
# Load only 300 funds (~20 minutes) to get a working screener immediately
python manage.py populate_screener --limit=300
```

---

### Phase 5 — Configure Anti-Sleep (5 minutes)

Render free web services sleep after **15 minutes of inactivity** (30–60 second cold start on first request).

To prevent this, use **UptimeRobot** (free, no credit card):

1. Go to [uptimerobot.com](https://uptimerobot.com) → Create free account
2. **Add New Monitor**:
   - Type: **HTTP(s)**
   - Friendly Name: `MF Analysis Keepalive`
   - URL: `https://your-app-name.onrender.com/` (your actual Render URL)
   - Monitoring Interval: **Every 14 minutes**
3. Click **Create Monitor**

UptimeRobot will ping your app every 14 minutes, keeping it awake. **Free plan covers up to 50 monitors.**

---

### Phase 6 — Configure Email (Optional, when ready)

> Skip this for launch. Set it up when you want real email delivery.

**Using Sender.net (15,000 free emails/month):**

1. [sender.net](https://sender.net) → Create free account → Verify email address
2. Dashboard → **SMTP Settings** → copy Host, Port, Username, Password
3. Sender.net → **Senders** → verify your sender email address

**Using Gmail App Password:**

1. Google Account → Security → 2-Step Verification (must be enabled)
2. App Passwords → Generate new → name it "MF Analysis"
3. Copy the 16-character password

**Add to Render dashboard (both web service and cron job):**

| Variable | Sender.net | Gmail |
|---|---|---|
| `EMAIL_HOST` | `smtp.sender.net` | `smtp.gmail.com` |
| `EMAIL_HOST_USER` | Your Sender.net SMTP username | Your Gmail address |
| `EMAIL_HOST_PASSWORD` | Your Sender.net SMTP password | 16-char App Password |

---

## Verification Checklist

After the full data load completes, check these URLs on your Render deployment:

| URL | What to verify |
|---|---|
| `/` | Home dashboard loads, category cards visible |
| `/funds/` | Screener shows funds with scores (0–100) |
| `/funds/120503/` | Fund detail page, all 7 tabs work |
| `/screener/` | Filter controls work |
| `/register/` | Registration form submits, activation email appears in Render logs |
| `/accounts/login/` | Login redirects to `/portfolio/` |
| `/accounts/password_reset/` | Form loads and submits |
| `/contact/` | Contact form submits |
| `/calculators/` | Calculator hub loads |
| `/portfolio/` | Portfolio section accessible after login |
| `/learn/resources/` | PDF guides and blog posts appear |
| `/admin/` | Admin panel accessible |

**Check Render Logs** (dashboard → your service → **Logs** tab) for any errors.

---

## Available Management Commands

| Command | What it does | When to Run |
|---|---|---|
| `build_scheme_master` | Loads ~2,300 AMFI direct growth / ETF schemes | Initial setup; monthly to pick up new funds |
| `sync_content` | Syncs PDF guides and blogs from `Resources/` to the database | After adding new PDFs/blogs + on first deploy |
| `ingest_benchmarks` | Incremental NAV sync for 51 benchmark indices | Daily (automated via cron) |
| `populate_benchmark_returns` | Computes trailing/rolling returns for benchmarks | Daily (automated via cron) |
| `populate_screener` | **Core pipeline:** NAV sync + metadata + analytics + 100-point scoring for all funds | Daily (automated via cron); use `--resume` after interruption |
| `populate_home_dashboard` | Aggregates category stats and quartile rankings | Auto-runs after `populate_screener` |
| `createsuperuser` | Creates an admin account | Once, after first deploy |

---

## Features Status

| Feature | Status |
|---|---|
| User registration (email required) | ✅ Working |
| Email verification on sign-up | ✅ Working (console in dev, SMTP in prod) |
| Login with rate limiting (5/min) | ✅ Working |
| Forgot password / password reset | ✅ Working (console in dev, SMTP in prod) |
| Contact form → email delivery | ✅ Working (console in dev, SMTP in prod) |
| Fund screener with 20+ filters | ✅ Working |
| Fund detail page (7 tabs) | ✅ Working |
| Fund comparison (up to 4) | ✅ Working |
| PDF fund report (Chrome headless) | ✅ Working (Chromium installed via build.sh) |
| 14+ Financial calculators | ✅ Working |
| Portfolio upload (Excel/CSV/CAS) | ✅ Working |
| Portfolio XIRR & analytics | ✅ Working |
| Backtester V2 | ✅ Working |
| Strategy comparison | ✅ Working |
| Learn section (PDF guides + blogs) | ✅ Working |
| Benchmark monitor | ✅ Working |
| Fund recommendations | 🚧 Draft UI (logic in progress) |
| Community feed | 🚧 Template only (backend coming) |
