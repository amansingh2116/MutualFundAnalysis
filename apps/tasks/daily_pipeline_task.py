"""
Task to run the full daily data pipeline using django-q2.

This replaces the old ingest_nav_task + compute_analytics_task pattern.
populate_screener is the all-in-one command that does:
  1. Incremental NAV ingestion (only new rows since last DB date)
  2. Metadata refresh (captnemo, stale check)
  3. Analytics computation (trailing, calendar, rolling returns, risk metrics)
  4. FundScreenerSnapshot refresh
  5. FundModelScore computation
  6. populate_home_dashboard (CategorySnapshot + quartile ranks)

After populate_screener completes, also runs:
  7. ingest_benchmarks (incremental, only new NAV rows for benchmark indices)
  8. populate_benchmark_returns (compute period returns for all benchmarks)
"""
import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')


def daily_pipeline_task():
    """
    Full daily pipeline.
    Intended to run at 02:00 IST daily via django-q2.

    Schedule in settings/base.py Q_SCHEDULE or via the Admin UI.
    """
    logger.info("[daily_pipeline_task] Starting full daily pipeline...")

    # ── Step 1: Full fund pipeline (NAV + meta + analytics + screener + dashboard) ──
    try:
        logger.info("[daily_pipeline_task] Running populate_screener (incremental)...")
        call_command('populate_screener')
        logger.info("[daily_pipeline_task] populate_screener complete")
    except Exception as e:
        logger.error(f"[daily_pipeline_task] populate_screener failed: {e}")
        raise

    # ── Step 2: Benchmark NAV ingestion (incremental) ─────────────────────────────
    try:
        logger.info("[daily_pipeline_task] Running ingest_benchmarks (incremental)...")
        call_command('ingest_benchmarks')
        logger.info("[daily_pipeline_task] ingest_benchmarks complete")
    except Exception as e:
        logger.error(f"[daily_pipeline_task] ingest_benchmarks failed: {e}")
        # Don't raise — benchmarks failing should not block the pipeline

    # ── Step 3: Benchmark returns computation ─────────────────────────────────────
    try:
        logger.info("[daily_pipeline_task] Running populate_benchmark_returns...")
        call_command('populate_benchmark_returns')
        logger.info("[daily_pipeline_task] populate_benchmark_returns complete")
    except Exception as e:
        logger.error(f"[daily_pipeline_task] populate_benchmark_returns failed: {e}")

    logger.info("[daily_pipeline_task] Daily pipeline complete.")
