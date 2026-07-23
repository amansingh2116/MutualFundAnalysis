"""apps/benchmarks/urls.py"""
from django.urls import path
from . import api_views

app_name = 'benchmarks'

urlpatterns = [
    path('indices/',             api_views.market_indices_api,        name='indices'),
    path('strip/',               api_views.market_strip_partial,       name='strip'),
    path('metrics/',             api_views.market_metrics_catalogue,   name='metrics_catalogue'),
    path('metrics/save/',        api_views.save_market_strip_metrics,  name='metrics_save'),
    path('fund-metric/',         api_views.fund_metric_api,            name='fund_metric'),
    path('benchmark-metric/',    api_views.benchmark_metric_api,       name='benchmark_metric'),
    path('benchmark-search/',    api_views.benchmark_search_api,       name='benchmark_search'),
    path('apikeys/',             api_views.user_api_keys_list,         name='apikeys_list'),
    path('apikeys/save/',        api_views.save_api_key,               name='apikeys_save'),
    path('apikeys/delete/',      api_views.delete_api_key,             name='apikeys_delete'),
]
