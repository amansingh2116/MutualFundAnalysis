"""apps/screener/urls.py"""
from django.urls import path
from . import views

app_name = 'screener'

urlpatterns = [
    path('', views.screener_view, name='screener'),
    path('results/', views.screener_results_view, name='results'),
    path('compare/', views.compare_view, name='compare'),
]
