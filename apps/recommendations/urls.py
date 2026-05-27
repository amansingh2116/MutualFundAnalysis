"""apps/recommendations/urls.py"""
from django.urls import path
from . import views

app_name = 'recommendations'

urlpatterns = [
    path('', views.engine_view, name='engine'),
    path('result/', views.result_view, name='result'),
    path('backtest/', views.backtest_view, name='backtest'),
]
