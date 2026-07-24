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
    path('rolling/', views.rolling_view, name='rolling'),
    path('step-sip/', views.step_sip_view, name='step_sip'),
    path('compare/', views.compare_view, name='compare'),
    path('stp/', views.stp_view, name='stp'),
    path('net-worth/', views.net_worth_view, name='net_worth'),
    path('child-education/', views.child_education_view, name='child_education'),
    path('retirement/', views.retirement_view, name='retirement'),
    path('peers/', views.peer_comparison_calc_view, name='peers'),
    # API endpoints

    path('api/sip/', views.calc_sip_api, name='api_sip'),
    path('api/lumpsum/', views.calc_lumpsum_api, name='api_lumpsum'),
    path('api/swp/', views.calc_swp_api, name='api_swp'),
    path('api/goal/', views.calc_goal_api, name='api_goal'),
    path('api/child-education/', views.calc_child_education_api, name='api_child_education'),
    path('api/retirement/', views.calc_retirement_api, name='api_retirement'),


    path('api/tax/', views.calc_tax_api, name='api_tax'),
    path('api/overlap/', views.calc_overlap_api, name='api_overlap'),
    path('api/xirr/', views.calc_xirr_api, name='api_xirr'),
    path('api/step-sip/', views.calc_step_sip_api, name='api_step_sip'),
    path('api/stp/', views.calc_stp_api, name='api_stp'),
    # Historical NAV-based endpoints
    path('api/nav-sip/',      views.calc_nav_sip_api,      name='api_nav_sip'),
    path('api/nav-swp/',      views.calc_nav_swp_api,      name='api_nav_swp'),
    path('api/nav-lumpsum/',  views.calc_nav_lumpsum_api,  name='api_nav_lumpsum'),
    path('api/nav-step-sip/', views.calc_nav_step_sip_api, name='api_nav_step_sip'),
    path('api/nav-stp/',      views.calc_nav_stp_api,      name='api_nav_stp'),
]
