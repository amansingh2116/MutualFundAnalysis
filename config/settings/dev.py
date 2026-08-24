"""
Development settings — SQLite, DEBUG=True, relaxed security.
"""
import os
from pathlib import Path

from .base import *  # noqa

DEBUG = True

SQLITE_DB_PATH = os.environ.get('SQLITE_DB_PATH')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': Path(SQLITE_DB_PATH) if SQLITE_DB_PATH else BASE_DIR / 'db.sqlite3',
    }
}

# Allow all hosts in dev
ALLOWED_HOSTS = ['*']

# Disable WhiteNoise manifest in dev (use plain static)
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Show emails in console during dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Use DummyCache in dev so stale in-memory snapshots never mask fresh DB data.
# Holdings ingestion writes to the DB; LocMemCache inside the dev server process
# would otherwise serve stale 10-holding Yahoo snapshots even after ingest_holdings runs.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Django Debug Toolbar (install separately if needed)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
# INTERNAL_IPS = ['127.0.0.1']


# ── django-q2 scheduled tasks ────────────────────────────────────────────────
# These are registered programmatically; run `python manage.py qcluster` to
# start the worker that picks them up.
#
# Daily pipeline covers: NAV ingestion + metadata + analytics + screener +
#   home dashboard + benchmark ingestion + benchmark returns
Q_SCHEDULE = [
    {
        # Full daily data pipeline (all-in-one)
        # Runs at 02:00 IST daily (NAV is published by ~01:30 IST)
        'name': 'daily_full_pipeline',
        'func': 'apps.tasks.daily_pipeline_task.daily_pipeline_task',
        'schedule_type': 'C',
        'cron': '0 2 * * *',      # 02:00 IST daily
        'repeats': -1,
    },
    {
        # Weekly metadata refresh (captnemo.in for expense_ratio, AUM etc.)
        # populate_screener already refreshes staleness > 7 days, but this
        # is a dedicated refresh to catch any funds missed during daily run.
        'name': 'weekly_metadata_refresh',
        'func': 'apps.tasks.ingest_metadata_task.ingest_metadata_task',
        'schedule_type': 'C',
        'cron': '0 3 * * 1',      # 03:00 IST Monday
        'repeats': -1,
    },
]

