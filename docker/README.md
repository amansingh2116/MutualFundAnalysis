# Docker Development Guide — MutualFundAnalysis

This guide explains how to run the application locally using Docker Compose, giving you a fully
isolated environment with **PostgreSQL 16** that mirrors the production database dialect.

---

## Architecture

| Service  | Image / Source | Purpose |
|----------|----------------|---------|
| `db`     | `postgres:16-alpine` | Local PostgreSQL 16 database |
| `web`    | Built from `Dockerfile` | Django dev server at `http://localhost:8000` |
| `worker` | Built from `Dockerfile` | `django-q2` background task cluster |

All services use `config.settings.local_pg`, which inherits `dev.py` (DEBUG=True, relaxed security)
but swaps the database to the Dockerized Postgres 16 instance.

> **Important**: Your existing `python manage.py runserver` SQLite workflow is completely unaffected.
> Docker is an *alternative* way to run the app — not a replacement.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A valid `.env` file at the repo root (copy `.env.example` and fill in `SECRET_KEY` at minimum)

---

## Quick Start

### 1. First time setup

```bash
# Build the image and start all services (takes ~5 minutes first time — Playwright Chromium downloads ~130 MB)
docker compose up --build

# In a second terminal: run migrations against the local Postgres DB
docker compose run --rm web python manage.py migrate

# (Optional) Create a superuser for the Django admin
docker compose run --rm web python manage.py createsuperuser
```

Open your browser at **http://localhost:8000** — the app is running against PostgreSQL 16.

### 2. Subsequent starts

```bash
docker compose up       # starts db + web + worker
docker compose down     # stops all containers (DB data is preserved)
```

### 3. Wipe the database and start fresh

```bash
docker compose down -v   # stops containers AND deletes the postgres_data volume
docker compose up --build
docker compose run --rm web python manage.py migrate
```

---

## Running Management Commands & Data Seeding

All management commands run inside the `web` container with the Postgres-pointing settings:

### 1. Seeding / Syncing Local Data

```bash
# Transfer your local db.sqlite3 data straight into Docker PostgreSQL
docker compose exec web python manage.py sync_from_sqlite

# Sync from production CockroachDB (when network/IP allowlist is accessible)
docker compose exec web python manage.py sync_from_prod --url "<DATABASE_URL>"

# Or seed fresh from AMFI / upstream APIs
docker compose exec web python manage.py build_scheme_master
docker compose exec web python manage.py ingest_benchmarks
docker compose exec web python manage.py populate_screener
```

### 2. Exporting & Sharing Data Snapshots (For Research & Distribution)

You can package your database into a compressed `.tar.gz` bundle for research or distribution:

```bash
# Export all tables (portable gzipped JSONL format)
docker compose exec web python manage.py export_data --output /app/data_snapshot.tar.gz

# Export metadata & screener only (lightweight, excludes raw NAV history)
docker compose exec web python manage.py export_data --output /app/data_snapshot_lite.tar.gz --skip-nav

# Import a dataset archive into any clean local or staging environment
docker compose exec web python manage.py import_data --file /app/data_snapshot.tar.gz
```

---

## Connecting to Postgres directly

The Postgres container exposes port `5432` on your host machine:

```bash
# psql (if installed on host)
psql -h localhost -p 5432 -U mfanalysis -d mfanalysis

# Or connect from any GUI tool (DBeaver, pgAdmin, TablePlus, etc.):
#   Host:     localhost
#   Port:     5432
#   Database: mfanalysis
#   User:     mfanalysis
#   Password: mfanalysis
```

---

## Live Code Reloading

The repo root is **volume-mounted** into `/app` inside the `web` and `worker` containers.
This means any Python, HTML, CSS, or JavaScript change you make locally is **immediately
reflected** in the running container — no rebuild needed.

You only need to **rebuild the image** (`docker compose up --build`) when you:
- Add or change packages in `requirements.txt`
- Modify the `Dockerfile` itself

---

## Settings Hierarchy

```
config/settings/
├── base.py          # Shared settings (apps, middleware, logging, Q_CLUSTER)
├── dev.py           # LOCAL SQLite dev — python manage.py runserver
├── local_pg.py      # LOCAL Postgres dev — docker compose up      ← used here
└── prod.py          # PRODUCTION CockroachDB on Render              ← unchanged
```

---

## PostgreSQL Validation

The primary purpose of the Docker setup (beyond convenience) is to validate that all ORM
queries and management commands work correctly against PostgreSQL — not just SQLite.

After loading data with `build_scheme_master`:

```bash
# Verify NAV ingestion works on Postgres
docker compose run --rm web python manage.py ingest_nav --limit=10

# Verify benchmark upsert (uses ON CONFLICT DO UPDATE — Postgres-specific)
docker compose run --rm web python manage.py ingest_benchmarks

# Verify full analytics pipeline
docker compose run --rm web python manage.py populate_screener --limit=20
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `web` exits immediately with `django.db.OperationalError` | Run `docker compose up` (not `run`) first so the `db` service is healthy |
| `python manage.py migrate` fails with `relation does not exist` | Postgres volume may be corrupted. Run `docker compose down -v && docker compose up --build` |
| Port 5432 already in use | You have a local Postgres running. Stop it or change the port mapping in `docker-compose.yml` to e.g. `"5433:5432"` and update `local_pg.py` PORT accordingly |
| Playwright/Chromium errors | Run `docker compose run --rm web playwright install chromium` to re-install the browser binary |
| Changes to `.py` files not reflected | Ensure the volume mount `- .:/app` is in `docker-compose.yml`. If you used `docker run` directly, the mount is absent |
