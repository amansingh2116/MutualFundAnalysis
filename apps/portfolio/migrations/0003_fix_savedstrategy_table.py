"""
Migration 0003: Drop and recreate portfolio_savedstrategy with the correct schema.

The table was created by an old migration with columns (payload, metrics, etc.)
but the model now uses (plan_json, last_result_json). Since the migration was
faked, the table was never updated. This migration fixes that.
"""
from django.conf import settings
from django.db import migrations


RECREATE_SQL = """
DROP TABLE IF EXISTS portfolio_savedstrategy;

CREATE TABLE "portfolio_savedstrategy" (
    "id"               integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "created_at"       datetime NOT NULL,
    "updated_at"       datetime NOT NULL,
    "name"             varchar(200) NOT NULL,
    "description"      text NOT NULL DEFAULT '',
    "plan_json"        text NOT NULL DEFAULT '{}',
    "last_result_json" text NULL,
    "user_id"          integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX "portfolio_savedstrategy_user_id_idx"
    ON "portfolio_savedstrategy" ("user_id");
"""


class Migration(migrations.Migration):

    dependencies = [
        ("portfolio", "0002_saved_strategy_model"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql=RECREATE_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
