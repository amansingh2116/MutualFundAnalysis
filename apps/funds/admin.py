from django.contrib import admin
from .models import FundScreenerSnapshot, Scheme, NAVHistory, SchemeMeta


@admin.register(Scheme)
class SchemeAdmin(admin.ModelAdmin):
    list_display  = ['amfi_code', 'scheme_name', 'fund_house', 'scheme_category',
                     'plan', 'is_direct', 'is_active', 'nav_latest', 'nav_date']
    list_filter   = ['is_direct', 'is_active', 'plan', 'scheme_category', 'fund_house']
    search_fields = ['amfi_code', 'scheme_name', 'fund_house', 'isin_growth']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50

    fieldsets = (
        ('Identifiers', {
            'fields': ('amfi_code', 'isin_growth', 'isin_idcw', 'morningstar_id',
                       'yahoo_ticker', 'kuvera_code')
        }),
        ('Core Info', {
            'fields': ('scheme_name', 'fund_house', 'scheme_type', 'scheme_category',
                       'plan', 'is_direct', 'is_active')
        }),
        ('Cached Metrics', {
            'fields': ('nav_latest', 'nav_date', 'expense_ratio', 'aum_cr'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(NAVHistory)
class NAVHistoryAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'date', 'nav']
    list_filter   = ['date']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme']
    ordering      = ['-date']
    list_per_page = 100


@admin.register(SchemeMeta)
class SchemeMetaAdmin(admin.ModelAdmin):
    list_display  = ['scheme', 'expense_ratio', 'aum', 'fund_rating',
                     'returns_1y', 'returns_3y', 'last_fetched']
    search_fields = ['scheme__amfi_code', 'scheme__scheme_name']
    raw_id_fields = ['scheme']
    readonly_fields = ['last_fetched', 'created_at', 'updated_at']
    list_per_page = 50


@admin.register(FundScreenerSnapshot)
class FundScreenerSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        'scheme', 'fund_house', 'category_group', 'scheme_sub_category',
        'plan_type', 'benchmark_name', 'cagr_3y_pct', 'rolling_return_3y_pct',
        'volatility_3y_pct', 'data_as_of', 'updated_at',
    ]
    list_filter = [
        'category_group', 'scheme_sub_category', 'fund_house', 'plan_type',
        'benchmark_type', 'risk_label', 'is_direct', 'is_etf',
    ]
    search_fields = ['fund_name', 'fund_house', 'scheme__amfi_code', 'benchmark_name']
    raw_id_fields = ['scheme']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50
