from django.contrib import admin
from .models import Scheme, NAVHistory, SchemeMeta


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
