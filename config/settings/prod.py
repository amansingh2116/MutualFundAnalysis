"""config/settings/prod.py — Production settings (Render.com + CockroachDB)."""
from .base import *
import os
import urllib.parse

DEBUG = False

# ── Belt-and-suspenders: patch PostgreSQL 14 version check at import time ─────
# CockroachDB reports "PostgreSQL 13.0" for wire-compatibility; Django 5.x would
# raise: NotSupportedError: PostgreSQL 14 or later is required.
# Our custom backend overrides check_database_version_supported, but we ALSO
# patch BaseDatabaseWrapper directly — that is the class where this method is
# DEFINED in Django 5.x (previously it was called DatabaseWrapper; patching the
# wrong name was a silent no-op and is why earlier attempts didn't work).
from django.db.backends.base.base import BaseDatabaseWrapper as _BaseDatabaseWrapper
from django.db.backends.postgresql.base import DatabaseWrapper as _PgDatabaseWrapper
_BaseDatabaseWrapper.check_database_version_supported = lambda self: None
_PgDatabaseWrapper.check_database_version_supported = lambda self: None

# ── Database (CockroachDB via DATABASE_URL) ───────────────────────────────────
# We parse DATABASE_URL ourselves with urllib.parse so ENGINE is set to
# 'config.backends.cockroachdb' unconditionally (no conditional branch to miss).
#
# Supported URL formats:
#   postgresql://user:pass@host.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
#   cockroachdb://user:pass@host.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
_raw_url = os.environ.get('DATABASE_URL', '')
if _raw_url:
    _url = (
        _raw_url
        .replace('cockroachdb://', 'postgresql://', 1)
        .replace('cockroach://', 'postgresql://', 1)
    )
    _p = urllib.parse.urlparse(_url)
    _qs = urllib.parse.parse_qs(_p.query)
    DATABASES = {
        'default': {
            'ENGINE':   'config.backends.cockroachdb',  # our CockroachDB-compatible backend
            'NAME':     _p.path.lstrip('/') or 'defaultdb',
            'USER':     urllib.parse.unquote(_p.username or ''),
            'PASSWORD': urllib.parse.unquote(_p.password or ''),
            'HOST':     _p.hostname or 'localhost',
            'PORT':     str(_p.port or 26257),
            # CONN_MAX_AGE=0: Do NOT use persistent connections.
            # CockroachDB Cloud drops idle connections after a few minutes;
            # reusing a dead connection causes a 500 on the next DB write
            # (e.g. session save on login). 0 = close after each request.
            'CONN_MAX_AGE':      0,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                # sslmode=require: keeps connection encrypted but skips cert
                # verification. verify-full fails on Render/GH Actions because
                # neither has a CockroachDB root cert file.
                'sslmode': 'require',
            },
        }
    }
else:
    # DATABASE_URL not set — app will fail on first DB access with a clear error.
    DATABASES = {'default': {'ENGINE': 'config.backends.cockroachdb'}}


# django_q migration 0003 is incompatible with CockroachDB (it tries to DROP
# the integer primary-key column, which CockroachDB blocks). Using None tells
# Django to skip the migration files and create these tables via syncdb from
# the final model definition instead — which CockroachDB handles correctly.
MIGRATION_MODULES = {
    'django_q': None,
}


# WhiteNoise for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ── Session backend ───────────────────────────────────────────────────────────
# Use signed-cookie sessions so that login() does NOT write to the database.
# Without this, every login does an INSERT/UPDATE to django_session on
# CockroachDB, which can fail on stale connections or transaction retries.
# Signed cookies are cryptographically signed with SECRET_KEY (safe) and
# never stored server-side. Size limit: 4 KB (enough for Django auth).
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# ── Security headers ─────────────────────────────────────────────────────────
# SECURE_PROXY_SSL_HEADER: Render.com terminates TLS at its load balancer and
# forwards requests to Django over HTTP internally, setting X-Forwarded-Proto.
# Without this, request.is_secure() returns False, SECURE_SSL_REDIRECT loops,
# and CSRF/session cookie Secure flags are not honoured correctly.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# CSRF trusted origins for Render subdomain
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.onrender.com',
).split(',')

# ── Email / SMTP (Sender.net, Postmark, or Gmail App Password) ────────────────
# For Sender.net: EMAIL_HOST=smtp.sender.net, EMAIL_HOST_USER=<your-username>
# For Gmail:   EMAIL_HOST=smtp.gmail.com,    EMAIL_HOST_USER=your@gmail.com
#
# If EMAIL_HOST_USER is not set we fall back to the console backend so that
# registration/password-reset emails are printed to Render logs instead of
# blocking on a failed SMTP connection (which can hang a gunicorn worker).
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
if EMAIL_HOST_USER:
    EMAIL_BACKEND   = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST      = config('EMAIL_HOST',   default='smtp.gmail.com')
    EMAIL_PORT      = config('EMAIL_PORT',   default=587, cast=int)
    EMAIL_USE_TLS   = config('EMAIL_USE_TLS', default=True, cast=bool)
else:
    # No SMTP credentials — print emails to stdout/Render logs.
    # Set EMAIL_HOST_USER + EMAIL_HOST_PASSWORD in the Render dashboard
    # to switch to real email delivery.
    EMAIL_BACKEND   = 'django.core.mail.backends.console.EmailBackend'
    EMAIL_HOST      = 'localhost'
    EMAIL_PORT      = 25
    EMAIL_USE_TLS   = False
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',  default='noreply@mfanalysis.com')
SERVER_EMAIL        = DEFAULT_FROM_EMAIL

# Where contact-form submissions get delivered (your personal inbox)
CONTACT_RECIPIENT_EMAIL = config('CONTACT_RECIPIENT_EMAIL', default=DEFAULT_FROM_EMAIL)

