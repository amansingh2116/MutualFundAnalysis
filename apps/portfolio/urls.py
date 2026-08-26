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
    # Backtester v2
    path('backtester/', views.portfolio_backtester_hub_view, name='backtester'),
    path('backtester/build/', views.portfolio_backtester_view, name='backtester_build'),
    path('backtester/v2/run/', views.backtester_v2_run_api, name='backtester_v2_run'),
    path('backtester/fund-search/', views.portfolio_fund_search_api, name='backtester_fund_search'),
    path('backtester/pe-data/', views.backtester_pe_api, name='backtester_pe_data'),
    # Saved Strategies (Phase 6 — Issue 14)
    path('strategies/', views.strategies_page, name='strategies'),
    path('strategies/compare/', views.strategy_compare_page, name='strategy_compare'),
    path('strategies/api/', views.strategy_list_api, name='strategy_list_api'),
    path('strategies/api/<int:strategy_id>/', views.strategy_detail_api, name='strategy_detail_api'),
    # Fund & ETF Watchlists
    path('watchlist/', views.watchlist_hub_view, name='watchlist_hub'),
    path('watchlist/api/', views.watchlist_api, name='watchlist_api'),
    path('watchlist/items/api/', views.watchlist_item_api, name='watchlist_items_api'),
    path('watchlist/item/api/', views.watchlist_item_api, name='watchlist_item_api'),
    path('watchlist/toggle/api/', views.watchlist_toggle_api, name='watchlist_toggle_api'),
    path('watchlist/search/api/', views.watchlist_search_api, name='watchlist_search_api'),
]
