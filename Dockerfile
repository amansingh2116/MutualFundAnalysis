# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — MutualFundAnalysis
# ─────────────────────────────────────────────────────────────────────────────
# Multi-stage build:
#   Stage 1 "builder"  – pip-install all Python dependencies into /opt/venv
#   Stage 2 "runtime"  – copy the venv, install Playwright Chromium, copy code
#
# Runtime image: python:3.12-slim-bookworm (matches Render's build environment)
#
# Usage (docker compose handles this automatically):
#   docker compose up --build          # full stack
#   docker compose run web python manage.py migrate
#   docker compose run web python manage.py build_scheme_master
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build-time OS tools (gcc needed for some C-extension packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated venv to copy cleanly into the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first (Docker layer-caches this step if reqs don't change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Default to dev settings; docker-compose overrides to local_pg
    DJANGO_SETTINGS_MODULE=config.settings.dev

WORKDIR /app

# ── System packages ───────────────────────────────────────────────────────────
# Required by:
#   • psycopg2-binary  → libpq5
#   • Playwright Chromium → the rest (same as what Render installs via its
#     managed environment; see build.sh comment about ~/.cache/ms-playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
        # PostgreSQL client library (psycopg2-binary needs this at runtime)
        libpq5 \
        # Playwright / Chromium runtime dependencies
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libx11-xcb1 \
        libxcb1 \
        libxext6 \
        fonts-liberation \
        # Misc utilities useful in dev containers
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Copy virtualenv from builder ──────────────────────────────────────────────
COPY --from=builder /opt/venv /opt/venv

# ── Install Playwright Chromium browser binary ────────────────────────────────
# Playwright downloads to ~/.cache/ms-playwright (user-writable).
# We cache it at /root/.cache/ms-playwright inside the image so every
# container start doesn't have to re-download Chromium (~130 MB).
RUN playwright install chromium

# ── Copy application source ───────────────────────────────────────────────────
# NOTE: In development (docker-compose), the source directory is volume-mounted
# over /app so this COPY is effectively overridden at runtime. It is kept here
# so the image is self-contained and can be used standalone (e.g. CI builds).
COPY . .

# ── Default command ───────────────────────────────────────────────────────────
# docker-compose.yml overrides this per service (web / worker).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
