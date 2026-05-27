# Task to ingest daily NAV data using django-q2

import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')

def ingest_nav_task(limit=None, amfi=None, force=False, direct_only=True):
    """Enqueue NAV ingestion.

    This function is intended to be used with ``django-q2``::

        from django_q.tasks import async_task
        async_task('apps.tasks.ingest_nav_task.ingest_nav_task')
    """
    try:
        args = []
        opts = {
            '--limit': limit,
            '--amfi': amfi,
            '--force': force,
            '--direct-only': direct_only,
        }
        # Filter out None values; bool flags need presence only when True
        filtered_opts = {k: v for k, v in opts.items() if v}
        # Build command options list
        opt_list = []
        for k, v in filtered_opts.items():
            if isinstance(v, bool):
                opt_list.append(k)
            else:
                opt_list.extend([k, str(v)])
        call_command('ingest_nav', *args, **dict(zip(opt_list[::2], opt_list[1::2])))
    except Exception as e:
        logger.error(f"[ingest_nav_task] failed: {e}")
        raise
