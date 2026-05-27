"""apps/funds/urls.py"""
from django.urls import path
from . import views

app_name = 'funds'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('funds/', views.CategoryListView.as_view(), name='category_list'),
    path('funds/search/', views.fund_search_api, name='search'),
    path('funds/<str:amfi_code>/', views.FundDetailView.as_view(), name='detail'),
    path('funds/<str:amfi_code>/export/', views.export_pdf_view, name='export_pdf'),
]
