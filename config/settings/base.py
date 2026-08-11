"""
Django settings — BASE (shared across dev and prod).
Import this in dev.py and prod.py, never use directly.
"""
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# ── Application definition ────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
]

THIRD_PARTY_APPS = [
    'django_q',   # background task queue (django-q2)
]

LOCAL_APPS = [
    'apps.core',
    'apps.funds',
    'apps.analytics',
    'apps.benchmarks',
    'apps.holdings',
    'apps.portfolio',
    'apps.calculators',
    'apps.recommendations',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # serve static files in prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.AutoLoginMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ── Password validation ───────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# NOTE: STATICFILES_STORAGE is intentionally NOT set here.
# prod.py sets it to WhiteNoise's CompressedManifestStaticFilesStorage.
# dev.py uses Django's default (no collectstatic required).

# ── Media files ───────────────────────────────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── Default primary key ───────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Login ─────────────────────────────────────────────────────────────────────
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/portfolio/'
LOGOUT_REDIRECT_URL = '/'

# ── Sessions ──────────────────────────────────────────────────────────────────
# Use signed-cookie sessions instead of DB sessions.
# Why: DB sessions (the default) require a CockroachDB write on every
# login/logout.  On the free tier, a momentary DB connection issue during
# the session save → 500 on login.  Cookie sessions:
#   • Are signed with SECRET_KEY (cannot be forged or tampered with)
#   • Are HTTPS-only in prod (SESSION_COOKIE_SECURE = True in prod.py)
#   • Store only the user ID (~50 bytes, far below the 4 KB cookie limit)
#   • Require ZERO extra DB reads/writes — auth is free
# Trade-off: sessions cannot be invalidated server-side (acceptable here).
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# ── Cache (used by django-ratelimit) ──────────────────────────────────────────
# LocMemCache is per-process — sufficient for a single gunicorn worker.
# Swap for a Redis cache backend if you scale to multiple workers.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'mfanalysis-ratelimit',
    }
}

# ── Rate-limiting (django-ratelimit) ──────────────────────────────────────────
# Don't silently pass requests when the cache is down — fail safe.
RATELIMIT_DENY_ON_CACHE_MISS = False  # False = allow through if cache is unavailable
RATELIMIT_USE_CACHE = 'default'

# ── Analytics constants ───────────────────────────────────────────────────────
# Risk-free rate for Sharpe/Sortino (Indian 91-day T-bill approximation).
# Update this quarterly in .env — do NOT hardcode in model/engine code.
RF_ANNUAL_RATE = config('RF_ANNUAL_RATE', default=0.065, cast=float)

# ── django-q2 cluster config ──────────────────────────────────────────────────
Q_CLUSTER = {
    'name': 'mfanalysis',
    'workers': 2,
    'recycle': 500,
    'timeout': 3600,     # 1 hour max per task
    'retry': 7200,       # retry after 2 hours if task fails
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',    # uses Django DB — no Redis needed in dev
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'mfanalysis': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'adapters': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
