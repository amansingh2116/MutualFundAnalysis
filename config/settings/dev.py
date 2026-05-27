"""
Development settings — SQLite, DEBUG=True, relaxed security.
"""
from .base import *  # noqa

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Allow all hosts in dev
ALLOWED_HOSTS = ['*']

# Disable WhiteNoise manifest in dev (use plain static)
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Show emails in console during dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Django Debug Toolbar (install separately if needed)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
# INTERNAL_IPS = ['127.0.0.1']

# ── django-q2 scheduled tasks ────────────────────────────────────────────────
# These are registered programmatically; run `python manage.py qcluster` to
# start the worker that picks them up.
Q_SCHEDULE = [
    {
        'name': 'daily_nav_ingest',
        'func': 'apps.tasks.ingest_nav_task.ingest_nav_task',
        'schedule_type': 'C',
        'cron': '0 2 * * *',      # 02:00 IST daily
        'repeats': -1,
    },
    {
        'name': 'weekly_metadata_ingest',
        'func': 'apps.tasks.ingest_metadata_task.ingest_metadata_task',
        'schedule_type': 'C',
        'cron': '0 3 * * 1',      # 03:00 IST Monday
        'repeats': -1,
    },
    {
        'name': 'weekly_benchmarks_ingest',
        'func': 'apps.tasks.ingest_benchmarks_task.ingest_benchmarks_task',
        'schedule_type': 'C',
        'cron': '0 4 * * 0',      # 04:00 IST Sunday
        'repeats': -1,
    },
    {
        'name': 'nightly_analytics_compute',
        'func': 'apps.tasks.compute_analytics_task.compute_analytics_task',
        'schedule_type': 'C',
        'cron': '0 5 * * *',      # 05:00 IST daily (after NAV ingest)
        'repeats': -1,
    },
]
