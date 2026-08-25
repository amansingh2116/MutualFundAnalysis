import re
from django.db import migrations


def backfill_categories(apps, schema_editor):
    Scheme = apps.get_model('funds', 'Scheme')
    for s in Scheme.objects.filter(scheme_category=''):
        stype = s.scheme_type or ''
        m = re.search(r'\((.*?)\)', stype)
        if m:
            cat = m.group(1).strip()
            if cat:
                s.scheme_category = cat
                s.save(update_fields=['scheme_category'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('funds', '0017_add_screener_portfolio_cap_fields'),
    ]

    operations = [
        migrations.RunPython(backfill_categories, reverse_noop),
    ]
