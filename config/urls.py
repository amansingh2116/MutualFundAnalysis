"""
Root URL configuration.
"""
import logging

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.views import LoginView, PasswordResetView
from django.shortcuts import render
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import RateLimitedLoginView

logger = logging.getLogger('mfanalysis')


class SafePasswordResetView(PasswordResetView):
    """
    Wraps Django's built-in PasswordResetView to catch email-sending errors.
    Without this, any SMTP failure (blocked port, wrong credentials, timeout)
    propagates as an unhandled exception → 500.
    """
    def form_valid(self, form):
        try:
            response = super().form_valid(form)
            return response
        except Exception as exc:
            logger.error('Password reset email failed: %s', exc)
            messages.error(
                self.request,
                'We could not send the password reset email right now. '
                'Please try again later or contact support.',
            )
            return render(
                self.request,
                self.template_name,
                self.get_context_data(form=form),
            )


urlpatterns = [
    path('admin/', admin.site.urls),

    # Login uses our rate-limited subclass; everything else comes from Django's auth URLs.
    path('accounts/login/',          RateLimitedLoginView.as_view(), name='login'),
    # Override password_reset BEFORE including auth.urls so our safe version wins.
    path('accounts/password_reset/', SafePasswordResetView.as_view(), name='password_reset'),
    path('accounts/',                include('django.contrib.auth.urls')),

    # Core (register page)
    path('', include('apps.core.urls', namespace='core')),

    # Apps
    path('',             include('apps.funds.urls',           namespace='funds')),
    path('calculators/', include('apps.calculators.urls',     namespace='calculators')),
    path('portfolio/',   include('apps.portfolio.urls',       namespace='portfolio')),
    path('recommend/',   include('apps.recommendations.urls', namespace='recommendations')),

    # JSON / HTMX API endpoints
    path('api/',         include('apps.analytics.api_urls',   namespace='analytics_api')),
    path('api/market/',  include('apps.benchmarks.urls',      namespace='benchmarks')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
