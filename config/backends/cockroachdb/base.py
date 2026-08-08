"""
config/backends/cockroachdb/base.py
====================================
Minimal CockroachDB-compatible Django database backend.

WHY THIS EXISTS
---------------
CockroachDB is PostgreSQL wire-compatible but has two incompatibilities
with Django 5.x out of the box:

1. VERSION CHECK
   CockroachDB reports "PostgreSQL 13.0" for wire-protocol compatibility.
   Django 5.x added a hard check requiring PostgreSQL 14+, causing:
       django.db.utils.NotSupportedError: PostgreSQL 14 or later is required

2. PRIMARY-KEY COLUMN DROPS
   CockroachDB cannot DROP a column that is (or was) the primary key within
   the same transaction. Django's migration for django-q/django-q2 (0003)
   tries to remove the old integer `id` primary-key column, which fails with:
       django.db.utils.ProgrammingError: column "id" is referenced by the primary key

SOLUTION
--------
This module subclasses Django's standard PostgreSQL backend and patches
only the two broken methods, leaving everything else (psycopg2, connection
pool, query execution, etc.) exactly as-is.

Note: django_q migrations are bypassed entirely in prod.py via
MIGRATION_MODULES so the schema is created by syncdb from the final model
definition — no migration incompatibilities are triggered.
"""

from django.db.backends.postgresql.base import DatabaseWrapper as _PgWrapper


class DatabaseWrapper(_PgWrapper):
    # ── Patch 1: Skip PostgreSQL version check ────────────────────────────────
    def check_database_version_supported(self):
        """
        CockroachDB reports 'PostgreSQL 13.0' for wire-compatibility, which
        causes Django 5.x to raise NotSupportedError. We skip this check —
        CockroachDB supports all Django ORM features we use.
        """
        pass
