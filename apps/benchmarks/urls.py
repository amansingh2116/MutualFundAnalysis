"""apps/benchmarks/urls.py"""
from django.urls import path
from . import api_views

app_name = 'benchmarks'

urlpatterns = [
    path('indices/', api_views.market_indices_api, name='indices'),
    path('strip/',   api_views.market_strip_partial, name='strip'),
]
