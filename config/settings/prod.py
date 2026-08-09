"""config/settings/prod.py — Production settings (Render.com + CockroachDB)."""
from .base import *
import os
import urllib.parse

DEBUG = False

# ── Belt-and-suspenders: patch PostgreSQL 14 version check at import time ─────
# Our custom backend (config.backends.cockroachdb) already overrides
# check_database_version_supported to a no-op, but we also patch the base class
# here so the check is bypassed unconditionally — even in environments where
# Django somehow loads the standard postgresql backend instead of our custom one.
# CockroachDB reports "PostgreSQL 13.0" for wire-compatibility; Django 5.x would
# otherwise raise: NotSupportedError: PostgreSQL 14 or later is required.
from django.db.backends.postgresql.base import DatabaseWrapper as _PgDatabaseWrapper
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
            'ENGINE':       'config.backends.cockroachdb',  # our CockroachDB-compatible backend
            'NAME':         _p.path.lstrip('/') or 'defaultdb',
            'USER':         urllib.parse.unquote(_p.username or ''),
            'PASSWORD':     urllib.parse.unquote(_p.password or ''),
            'HOST':         _p.hostname or 'localhost',
            'PORT':         str(_p.port or 26257),
            'CONN_MAX_AGE': 600,
            'OPTIONS': {
                'sslmode':     _qs.get('sslmode',     ['verify-full'])[0],
                # Use OS trusted cert store instead of ~/.postgresql/root.crt
                # (that file does not exist on Render or GitHub Actions runners).
                'sslrootcert': _qs.get('sslrootcert', ['system'])[0],
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

# Security headers
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
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = config('EMAIL_HOST',          default='smtp.gmail.com')
EMAIL_PORT          = config('EMAIL_PORT',          default=587,   cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',       default=True,  cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL',  default='noreply@mfanalysis.com')
SERVER_EMAIL        = DEFAULT_FROM_EMAIL

# Where contact-form submissions get delivered (your personal inbox)
CONTACT_RECIPIENT_EMAIL = config('CONTACT_RECIPIENT_EMAIL', default=DEFAULT_FROM_EMAIL)

