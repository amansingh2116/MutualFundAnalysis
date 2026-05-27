# Task to ingest benchmark index data using django-q2

import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')

def ingest_benchmarks_task():
    """Enqueue benchmark ingestion.
    Runs weekly.
    """
    try:
        call_command('ingest_benchmarks')
    except Exception as e:
        logger.error(f"[ingest_benchmarks_task] failed: {e}")
        raise
