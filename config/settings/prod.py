"""config/settings/prod.py — Production settings (Render.com + PostgreSQL).

Supports any standard PostgreSQL provider: Neon, Supabase, Railway, or plain
Render PostgreSQL. Set DATABASE_URL in Render env vars and GitHub Secrets.

DATABASE_URL format:
    postgresql://user:pass@host/dbname?sslmode=require
"""
from .base import *
import os
import dj_database_url

DEBUG = False

# ── Database (Turso libSQL or PostgreSQL via DATABASE_URL) ───────────────────
# If TURSO_DB_URL is provided, use django-libsql-backend (Turso serverless SQLite).
# Otherwise, fall back to standard PostgreSQL via DATABASE_URL (Neon, Supabase, etc.).
_turso_url = os.environ.get('TURSO_DB_URL', '')
_raw_url = os.environ.get('DATABASE_URL', '')

if _turso_url:
    DATABASES = {
        'default': {
            'ENGINE': 'django_libsql',
            'NAME': _turso_url,
            'AUTH_TOKEN': os.environ.get('TURSO_AUTH_TOKEN', ''),
            'OPTIONS': {
                'timeout': 60,
            }
        }
    }
elif _raw_url:
    DATABASES = {
        'default': dj_database_url.parse(
            _raw_url,
            conn_max_age=0,          # No persistent connections — cloud DBs drop idle
            conn_health_checks=True,  # Validate connection before reuse
            ssl_require=True,         # Always encrypt
        )
    }
else:
    # App will fail on first DB access if neither is set
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql'}}


# WhiteNoise for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


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
    EMAIL_HOST      = config('EMAIL_HOST',   default='smtp.sender.net')
    EMAIL_PORT      = config('EMAIL_PORT',   default=587, cast=int)
    EMAIL_USE_TLS   = config('EMAIL_USE_TLS', default=True, cast=bool)
    # Fail fast if SMTP is unreachable (e.g. port blocked on cloud host).
    # Without a timeout, smtplib blocks the gunicorn worker indefinitely,
    # causing a 500 after 120 s when gunicorn kills the hung worker.
    EMAIL_TIMEOUT   = 10  # seconds
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

