"""
config/backends/cockroachdb/base.py
====================================
CockroachDB-compatible Django database backend for Django 5.x.

CockroachDB is PostgreSQL wire-compatible but has a few key differences:
1. Version check: reports 'PostgreSQL 13.0' which Django 5.x rejects by default.
2. Constraints: does NOT support DEFERRABLE / INITIALLY DEFERRED constraints.
3. Column inline FK: does NOT support 'SET CONSTRAINTS ... IMMEDIATE'.
4. Index operator classes: does NOT support varchar_pattern_ops/text_pattern_ops on B-tree indexes.
"""

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.postgresql.base import DatabaseWrapper as _PgWrapper
from django.db.backends.postgresql.features import DatabaseFeatures as _PgFeatures
from django.db.backends.postgresql.operations import DatabaseOperations as _PgOperations
from django.db.backends.postgresql.schema import DatabaseSchemaEditor as _PgSchemaEditor


class DatabaseOperations(_PgOperations):
    def deferrable_sql(self):
        """CockroachDB does not support DEFERRABLE constraints."""
        return ""


class DatabaseFeatures(_PgFeatures):
    can_defer_constraint_checks = False
    supports_deferrable_unique_constraints = False


class DatabaseSchemaEditor(_PgSchemaEditor):
    # CockroachDB does not support SET CONSTRAINTS ... IMMEDIATE
    sql_create_column_inline_fk = (
        "CONSTRAINT %(name)s REFERENCES %(to_table)s(%(to_column)s)"
    )

    def _create_like_index_sql(self, model, field):
        """
        CockroachDB does not support varchar_pattern_ops / text_pattern_ops
        operator classes on standard B-tree indexes.
        """
        return None

    def _index_columns(self, table, columns, col_suffixes, opclasses):
        """
        Strip operator classes since CockroachDB only allows them for inverted/vector indexes.
        """
        return BaseDatabaseSchemaEditor._index_columns(self, table, columns, col_suffixes, ())


class DatabaseWrapper(_PgWrapper):
    ops_class = DatabaseOperations
    features_class = DatabaseFeatures
    SchemaEditorClass = DatabaseSchemaEditor

    def check_database_version_supported(self):
        """Bypass PostgreSQL 14+ version check for CockroachDB."""
        pass
