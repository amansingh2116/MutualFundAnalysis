"""
config/settings/local_pg.py — Local PostgreSQL settings (Docker Compose only).
================================================================================
Inherits all dev settings (SQLite, DEBUG=True, relaxed security) but overrides
the database to use the Dockerized PostgreSQL 16 service.

Purpose:
  Used EXCLUSIVELY when developing inside docker-compose. This lets us run and
  validate all queries against a real PostgreSQL 16 database locally, exposing
  any SQLite-to-Postgres dialect incompatibilities before they reach production.

Backend choice:
  Uses the STANDARD Django PostgreSQL backend (django.db.backends.postgresql),
  NOT the CockroachDB compat backend from config.backends.cockroachdb. This
  gives us clean, unpatched PostgreSQL behaviour for accurate local testing.

Host resolution:
  'HOST': 'db' — Docker Compose creates an internal network where each service
  is reachable by its service name. 'db' resolves to the postgres:16 container.
  Outside Docker (e.g. running manage.py on the host), this will fail — use
  dev.py (SQLite) for host-side development.

Usage (via docker-compose.yml):
  docker compose up               # starts web + worker + db
  docker compose run web python manage.py migrate
  docker compose run web python manage.py build_scheme_master
  docker compose run web python manage.py populate_screener
"""

from .dev import *  # noqa — inherit DEBUG, ALLOWED_HOSTS, Q_SCHEDULE, logging, etc.

# ── Override: use the Dockerized PostgreSQL 16 instance ──────────────────────
# Credentials match docker-compose.yml environment variables exactly.
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql',
        'NAME':     'mfanalysis',
        'USER':     'mfanalysis',
        'PASSWORD': 'mfanalysis',
        'HOST':     'db',      # Docker Compose service name — resolves internally
        'PORT':     '5432',
        # Keep connections open for the lifetime of the request to avoid
        # per-query reconnect overhead in the dev server.
        'CONN_MAX_AGE': 60,
    }
}

# ── Hint in logs which settings are active ───────────────────────────────────
import logging as _logging
_logging.getLogger('mfanalysis').info(
    '[settings] local_pg: using Dockerized PostgreSQL 16 at db:5432'
)
