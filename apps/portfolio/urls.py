"""apps/portfolio/urls.py"""
from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.portfolio_list_view, name='list'),
    path('upload/', views.portfolio_upload_view, name='upload'),
    path('manual/', views.portfolio_manual_entry_view, name='manual_entry'),
    path('manual/api/', views.portfolio_manual_entry_api, name='manual_entry_api'),
    path('<int:pk>/', views.portfolio_dashboard_view, name='dashboard'),
    path('<int:pk>/overlap/', views.portfolio_overlap_view, name='overlap'),
    path('<int:pk>/benchmark/', views.portfolio_benchmark_view, name='benchmark'),
    path('<int:pk>/rebalance/', views.portfolio_rebalance_view, name='rebalance'),
    path('<int:pk>/delete/', views.portfolio_delete_view, name='delete'),
    path('<int:pk>/forecast/api/', views.portfolio_forecast_api, name='forecast_api'),
]
