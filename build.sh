#!/usr/bin/env bash
# build.sh — Render.com build script for the WEB SERVICE only.
# Used by: mfanalysis-web (needs Chromium for PDF generation)
# NOT used by: mfanalysis-daily-pipeline cron job (uses plain pip install)
set -o errexit   # exit immediately on any error

# ── 1. Python packages ─────────────────────────────────────────────────────────
# Install first so that the playwright CLI is available for step 2.
echo "==> Installing Python dependencies..."
pip install -r requirements.txt

# ── 2. Playwright Chromium browser (headless PDF generation) ───────────────────
# Playwright downloads a self-contained Chromium binary to ~/.cache/ms-playwright
# (a user-writable directory). This bypasses the read-only system filesystem on
# Render's free tier where apt-get is not available.
echo "==> Downloading Playwright Chromium browser..."
python -m playwright install chromium
