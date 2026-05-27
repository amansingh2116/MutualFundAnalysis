"""
Root URL configuration.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # Core (register page)
    path('', include('apps.core.urls', namespace='core')),

    # Apps
    path('',             include('apps.funds.urls',           namespace='funds')),
    path('screener/',    include('apps.screener.urls',        namespace='screener')),
    path('calculators/', include('apps.calculators.urls',     namespace='calculators')),
    path('portfolio/',   include('apps.portfolio.urls',       namespace='portfolio')),
    path('recommend/',   include('apps.recommendations.urls', namespace='recommendations')),

    # JSON / HTMX API endpoints
    path('api/',         include('apps.analytics.api_urls',   namespace='analytics_api')),
    path('api/market/',  include('apps.benchmarks.urls',      namespace='benchmarks')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
