from django.contrib import admin
from .models import BenchmarkIndex, BenchmarkNAV


@admin.register(BenchmarkIndex)
class BenchmarkIndexAdmin(admin.ModelAdmin):
    list_display  = ['name', 'nse_type_str', 'yahoo_ticker', 'is_active']
    search_fields = ['name']
    list_filter   = ['is_active']


@admin.register(BenchmarkNAV)
class BenchmarkNAVAdmin(admin.ModelAdmin):
    list_display  = ['index', 'date', 'close', 'source']
    list_filter   = ['index', 'source']
    ordering      = ['-date']
    raw_id_fields = ['index']
    list_per_page = 100
