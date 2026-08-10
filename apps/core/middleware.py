"""
apps/core/middleware.py — Auto-login middleware for testing.
Automatically assigns a demo user to any unauthenticated request so all
features (portfolios, watchlists, backtester, recommendations) work without signing in.
"""
from django.contrib.auth import get_user_model

_demo_user_cache = None


class AutoLoginMiddleware:
    """
    Ensures every request has an active User (demo_user) so all site features
    can be tested without hitting authentication barriers or login errors.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_anonymous:
            global _demo_user_cache
            if _demo_user_cache is None:
                User = get_user_model()
                try:
                    _demo_user_cache, _ = User.objects.get_or_create(
                        username='demo_user',
                        defaults={
                            'email': 'demo@mfanalysis.local',
                            'is_active': True,
                        }
                    )
                except Exception:
                    pass

            if _demo_user_cache:
                request.user = _demo_user_cache

        return self.get_response(request)
