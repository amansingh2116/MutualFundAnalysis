# Generated migration: add rolling median fields + category snapshot metrics
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('funds', '0013_fundscreenersnapshot_rolling_min_3y_pct_and_more'),
    ]

    operations = [
        # FundScreenerSnapshot: Rolling median columns
        migrations.AddField(model_name='fundscreenersnapshot', name='rolling_median_1y_pct',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 1Y rolling return %', max_digits=8, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='rolling_median_3y_pct',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 3Y rolling return %', max_digits=8, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='rolling_median_5y_pct',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 5Y rolling return %', max_digits=8, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='rolling_median_7y_pct',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 7Y rolling return %', max_digits=8, null=True)),
        # FundScreenerSnapshot: Category peer metric columns
        migrations.AddField(model_name='fundscreenersnapshot', name='category_alpha_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Category avg alpha_3y', max_digits=8, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='category_beta_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Category avg beta_3y', max_digits=8, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='category_expense_ratio',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Category avg expense_ratio', max_digits=5, null=True)),
        migrations.AddField(model_name='fundscreenersnapshot', name='category_turnover',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Category avg portfolio_turnover', max_digits=8, null=True)),
        # CategorySnapshot: Alpha / Beta / Expense / Turnover columns
        migrations.AddField(model_name='categorysnapshot', name='avg_alpha_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Average 3Y alpha across funds', max_digits=8, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='median_alpha_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 3Y alpha across funds', max_digits=8, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='avg_beta_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Average 3Y beta across funds', max_digits=8, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='median_beta_3y',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median 3Y beta across funds', max_digits=8, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='avg_expense_ratio',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Average expense ratio across funds', max_digits=5, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='median_expense_ratio',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Median expense ratio across funds', max_digits=5, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='avg_turnover',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Average portfolio turnover across funds', max_digits=8, null=True)),
        migrations.AddField(model_name='categorysnapshot', name='median_turnover',
            field=models.DecimalField(blank=True, decimal_places=4, help_text='Median portfolio turnover across funds', max_digits=8, null=True)),
    ]
