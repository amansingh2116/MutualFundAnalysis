"""
Root URL configuration.
"""
import logging

from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.views import LoginView, PasswordResetView
from django.shortcuts import render, redirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import RateLimitedLoginView

logger = logging.getLogger('mfanalysis')


class SafePasswordResetView(PasswordResetView):
    """
    Wraps Django's built-in PasswordResetView to:
      1. Use our custom template (registration/password_reset.html)
         instead of Django's default registration/password_reset_form.html.
         Without this override the GET request 500s because the default template
         file does not exist in our templates directory.
      2. Catch email-sending errors so SMTP failures don't propagate as 500.
    """
    # Django's default is 'registration/password_reset_form.html'.
    # Our custom file is 'registration/password_reset.html'.
    template_name = 'registration/password_reset.html'

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

    # Redirect Django admin's built-in password-reset to our custom page.
    # Without this, users who end up on /admin/login/ click "Forgot password?"
    # and land on the bare Django admin UI instead of our branded page.
    path('admin/password_reset/', lambda r: redirect('/accounts/password_reset/')),

    # Login uses our rate-limited subclass; everything else comes from Django auth URLs.
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
