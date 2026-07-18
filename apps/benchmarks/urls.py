"""apps/benchmarks/urls.py"""
from django.urls import path
from . import api_views

app_name = 'benchmarks'

urlpatterns = [
    path('indices/',       api_views.market_indices_api,         name='indices'),
    path('strip/',         api_views.market_strip_partial,        name='strip'),
    path('metrics/',       api_views.market_metrics_catalogue,    name='metrics_catalogue'),
    path('metrics/save/',  api_views.save_market_strip_metrics,   name='metrics_save'),
]
