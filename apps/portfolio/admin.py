from django.contrib import admin
from .models import Portfolio, Transaction


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_private', 'created_at')
    search_fields = ('name', 'user__username')
    list_filter = ('is_private',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('portfolio', 'scheme_name', 'tx_type', 'tx_date', 'amount', 'units')
    list_filter = ('tx_type', 'tx_date', 'portfolio')
    search_fields = ('scheme_name', 'amfi_code', 'folio')
    raw_id_fields = ('portfolio', 'scheme')
