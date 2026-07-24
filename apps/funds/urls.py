"""apps/funds/urls.py"""
from django.urls import path
from . import views

app_name = 'funds'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('home/category-funds/', views.home_category_funds, name='home_category_funds'),
    path('funds/', views.CategoryListView.as_view(), name='category_list'),
    path('funds/screener/', views.FundScreenerView.as_view(), name='screener'),
    path('funds/search/', views.fund_search_api, name='search'),
    path('funds/<str:amfi_code>/', views.FundDetailView.as_view(), name='detail'),
    path('funds/<str:amfi_code>/export/', views.export_pdf_view, name='export_pdf'),

    # ── Research Hub ────────────────────────────────────────────────────────
    path('research/benchmarks/', views.ResearchBenchmarksView.as_view(), name='research_benchmarks'),
    path('research/benchmarks/watchlist/', views.benchmark_watchlist_api, name='benchmark_watchlist_api'),
    path('research/category-meter/', views.ResearchCategoryMeterView.as_view(), name='research_category_meter'),
    path('research/categories/', views.ResearchCategoriesView.as_view(), name='research_categories'),
    path('research/categories/compare/', views.ResearchCategoryCompareView.as_view(), name='research_category_compare'),
    path('research/categories/api/list/', views.category_list_api, name='category_list_api'),
    path('research/categories/api/compare/', views.category_compare_api, name='category_compare_api'),
    path('research/categories/<str:slug>/', views.ResearchCategoryDetailView.as_view(), name='research_category_detail'),
    path('research/categories/<str:slug>/funds/', views.category_detail_funds_api, name='category_detail_funds_api'),
    path('research/quartiles/', views.ResearchQuartilesView.as_view(), name='research_quartiles'),
    path('research/quartiles/api/', views.quartile_rankings_api, name='quartile_rankings_api'),

    # ── AMC Analysis ─────────────────────────────────────────────────────────
    path('research/amcs/', views.ResearchAMCListView.as_view(), name='research_amcs'),
    path('research/amcs/compare/', views.ResearchAMCCompareView.as_view(), name='research_amc_compare'),
    path('research/amcs/api/list/', views.amc_list_api, name='amc_list_api'),
    path('research/amcs/api/compare/', views.amc_compare_api, name='amc_compare_api'),
    path('research/amcs/<str:slug>/', views.ResearchAMCDetailView.as_view(), name='research_amc_detail'),
    path('research/amcs/<str:slug>/funds/', views.amc_detail_funds_api, name='amc_detail_funds_api'),
]

# Aliases for calculator pages under funds namespace to prevent NoReverseMatch
from apps.calculators import views as calc_views
urlpatterns.append(path('calculators/child-education/', calc_views.child_education_view, name='child_education'))
urlpatterns.append(path('calculators/retirement/', calc_views.retirement_view, name='retirement'))
urlpatterns.append(path('calculators/peers/', calc_views.peer_comparison_calc_view, name='peers'))



