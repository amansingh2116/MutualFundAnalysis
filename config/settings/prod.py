"""config/settings/prod.py — Production settings (Render.com + CockroachDB)."""
from .base import *
import dj_database_url

DEBUG = False

# ── Database (CockroachDB via DATABASE_URL) ───────────────────────────────────
# CockroachDB is PostgreSQL wire-compatible but reports version 13.0.
# Django 5.x requires PG14+ and would reject the connection without our
# custom backend (config.backends.cockroachdb) which patches the version check.
# DATABASE_URL format from CockroachDB dashboard:
#   postgresql://user:pass@host.cockroachlabs.cloud:26257/defaultdb?sslmode=verify-full
_db_config = dj_database_url.config(
    env='DATABASE_URL',
    conn_max_age=600,
    ssl_require=True,
)
# Override ENGINE to our custom CockroachDB-compatible backend
if _db_config:
    _db_config['ENGINE'] = 'config.backends.cockroachdb'
    _db_config.setdefault('OPTIONS', {})
    _db_config['OPTIONS'].setdefault('sslmode', 'verify-full')

DATABASES = {'default': _db_config}

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

