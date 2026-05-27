from django.contrib import admin
from .models import TrailingReturn, CalendarReturn, RollingReturn, RiskMetrics


@admin.register(TrailingReturn)
class TrailingReturnAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'period', 'cagr_pct', 'bm_cagr', 'excess', 'as_of']
    list_filter   = ['period', 'as_of']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme']
    ordering      = ['-as_of', 'period']


@admin.register(CalendarReturn)
class CalendarReturnAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'year', 'return_pct', 'bm_return', 'outperformed']
    list_filter   = ['year', 'outperformed']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme']


@admin.register(RollingReturn)
class RollingReturnAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'window', 'min_pct', 'max_pct', 'mean_pct', 'win_rate_12', 'as_of']
    list_filter   = ['window', 'as_of']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme']


@admin.register(RiskMetrics)
class RiskMetricsAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'period', 'sharpe_ratio', 'beta', 'alpha_ann',
                     'max_drawdown', 'std_dev_ann', 'as_of']
    list_filter   = ['period', 'as_of']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme', 'benchmark']
