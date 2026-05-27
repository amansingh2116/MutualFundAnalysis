# Task to ingest fund metadata using django-q2

import logging
from django.core.management import call_command

logger = logging.getLogger('mfanalysis')

def ingest_metadata_task(limit=None, amfi=None, force=False, skip_mstarpy=False):
    """Enqueue metadata ingestion.

    Intended usage with ``django-q2``::

        from django_q.tasks import async_task
        async_task('apps.tasks.ingest_metadata_task.ingest_metadata_task')
    """
    try:
        opts = {
            '--limit': limit,
            '--amfi': amfi,
            '--force': force,
            '--skip-mstarpy': skip_mstarpy,
        }
        filtered_opts = {k: v for k, v in opts.items() if v}
        opt_list = []
        for k, v in filtered_opts.items():
            if isinstance(v, bool):
                opt_list.append(k)
            else:
                opt_list.extend([k, str(v)])
        call_command('ingest_metadata', *opt_list)
    except Exception as e:
        logger.error(f"[ingest_metadata_task] failed: {e}")
        raise
