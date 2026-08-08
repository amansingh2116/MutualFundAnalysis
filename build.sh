#!/usr/bin/env bash
# build.sh — Render.com build script
# Runs before the app starts. Installs system dependencies that cannot be
# satisfied by pip alone, then installs Python packages.
set -o errexit   # exit immediately on any error

# ── 1. System deps: Chromium (headless PDF generation) ────────────────────────
# report.py uses Chrome/Chromium --print-to-pdf instead of WeasyPrint because
# WeasyPrint requires GTK/Cairo native libs that are harder to install reliably.
# Chromium is the lightest available option on Render's Ubuntu/Debian runners.
echo "==> Installing Chromium and fonts..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    chromium-browser \
    fonts-liberation \
    fonts-noto \
    libglib2.0-0 \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0

# ── 2. Python packages ─────────────────────────────────────────────────────────
echo "==> Installing Python dependencies..."
pip install -r requirements.txt
