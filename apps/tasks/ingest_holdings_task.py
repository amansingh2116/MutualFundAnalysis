# Task to ingest holdings data using django-q2

import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')

def ingest_holdings_task():
    """Enqueue holdings ingestion.
    Runs monthly.
    """
    try:
        call_command('ingest_holdings')
    except Exception as e:
        logger.error(f"[ingest_holdings_task] failed: {e}")
        raise
