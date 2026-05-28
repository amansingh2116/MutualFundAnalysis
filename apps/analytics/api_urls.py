"""apps/analytics/api_urls.py"""
from django.urls import path
from . import api_views

app_name = 'api'

urlpatterns = [
    path('funds/<str:amfi_code>/nav/', api_views.nav_chart_api, name='nav'),
    path('funds/<str:amfi_code>/returns/', api_views.returns_api, name='returns'),
    path('funds/<str:amfi_code>/calendar/', api_views.calendar_api, name='calendar'),
    path('funds/<str:amfi_code>/drawdown/', api_views.drawdown_api, name='drawdown'),
    path('funds/<str:amfi_code>/risk/', api_views.risk_api, name='risk'),
    path('funds/<str:amfi_code>/holdings/', api_views.holdings_api, name='holdings'),
    path('funds/<str:amfi_code>/sector/', api_views.sector_api, name='sector'),
    path('funds/<str:amfi_code>/sip/', api_views.sip_simulate_api, name='sip'),
    path('funds/<str:amfi_code>/lumpsum/', api_views.lumpsum_simulate_api, name='lumpsum'),
    path('funds/<str:amfi_code>/swp/', api_views.swp_simulate_api, name='swp'),
    path('funds/<str:amfi_code>/rolling/', api_views.rolling_chart_api, name='rolling'),
    path('funds/<str:amfi_code>/rolling-timeseries/', api_views.rolling_timeseries_api, name='rolling_timeseries'),
    path('funds/<str:amfi_code>/analysis/', api_views.analysis_api, name='analysis'),
    path('funds/<str:amfi_code>/peers/', api_views.peer_comparison_api, name='peers'),
]

