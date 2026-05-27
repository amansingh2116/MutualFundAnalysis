"""apps/calculators/urls.py"""
from django.urls import path
from . import views

app_name = 'calculators'

urlpatterns = [
    path('', views.hub_view, name='hub'),
    path('sip/', views.sip_view, name='sip'),
    path('lumpsum/', views.lumpsum_view, name='lumpsum'),
    path('xirr/', views.xirr_view, name='xirr'),
    path('swp/', views.swp_view, name='swp'),
    path('goal/', views.goal_view, name='goal'),
    path('tax/', views.tax_view, name='tax'),
    path('overlap/', views.overlap_view, name='overlap'),
    path('step-sip/', views.step_sip_view, name='step_sip'),
    # API endpoints
    path('api/sip/', views.calc_sip_api, name='api_sip'),
    path('api/lumpsum/', views.calc_lumpsum_api, name='api_lumpsum'),
    path('api/swp/', views.calc_swp_api, name='api_swp'),
    path('api/goal/', views.calc_goal_api, name='api_goal'),
    path('api/tax/', views.calc_tax_api, name='api_tax'),
    path('api/overlap/', views.calc_overlap_api, name='api_overlap'),
    path('api/xirr/', views.calc_xirr_api, name='api_xirr'),
    path('api/step-sip/', views.calc_step_sip_api, name='api_step_sip'),
]
