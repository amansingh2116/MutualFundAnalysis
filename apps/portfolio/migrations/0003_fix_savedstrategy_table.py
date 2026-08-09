"""
Migration 0003 — no-op on PostgreSQL / CockroachDB.

HISTORY
-------
This migration was originally written as a local SQLite hotfix: migration 0002
had been ``--fake``d on the developer's machine so the portfolio_savedstrategy
table was created with old columns (payload, metrics, …).  The raw SQL here
dropped and re-created the table with the current schema.

WHY THIS IS A NO-OP NOW
------------------------
The raw SQL used SQLite-specific syntax:
  • ``integer NOT NULL PRIMARY KEY AUTOINCREMENT`` — valid only in SQLite
  • ``DEFERRABLE INITIALLY DEFERRED``              — not implemented in CockroachDB

On a fresh CockroachDB (or PostgreSQL) deployment migration 0002 runs normally
and already creates the table with the correct schema (plan_json JSONField,
last_result_json JSONField).  There is nothing to fix.

LOCAL DEV
---------
If your local SQLite database still has the old columns, run::

    python manage.py migrate --run-syncdb

or delete the SQLite file and migrate from scratch.
"""
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0002_saved_strategy_model"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # No database operations required.
        # 0002 already created portfolio_savedstrategy with the correct schema
        # on any fresh PostgreSQL / CockroachDB deployment.
    ]
