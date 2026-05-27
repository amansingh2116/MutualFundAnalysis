from django.contrib import admin
from .models import Holding, SectorAllocation, MarketCapAllocation


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ('scheme', 'security_name', 'weight_pct', 'sector', 'as_of_month', 'source')
    list_filter = ('as_of_month', 'source', 'holding_type')
    search_fields = ('security_name', 'isin', 'ticker', 'scheme__scheme_name')
    raw_id_fields = ('scheme',)


@admin.register(SectorAllocation)
class SectorAllocationAdmin(admin.ModelAdmin):
    list_display = ('scheme', 'sector', 'weight_pct', 'as_of_month', 'source')
    list_filter = ('as_of_month', 'source')
    raw_id_fields = ('scheme',)


@admin.register(MarketCapAllocation)
class MarketCapAllocationAdmin(admin.ModelAdmin):
    list_display = ('scheme', 'large_pct', 'mid_pct', 'small_pct', 'as_of_month')
    list_filter = ('as_of_month',)
    raw_id_fields = ('scheme',)
