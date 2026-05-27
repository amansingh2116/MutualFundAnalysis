# Task to compute analytics using django-q2

import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')

def compute_analytics_task():
    """Enqueue analytics computation.
    Runs nightly.
    """
    try:
        call_command('compute_analytics')
    except Exception as e:
        logger.error(f"[compute_analytics_task] failed: {e}")
        raise
