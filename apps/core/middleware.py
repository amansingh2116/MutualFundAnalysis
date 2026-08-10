"""
apps/core/middleware.py — Auto-login middleware for testing.
Automatically assigns a demo user to any unauthenticated request so all
features (portfolios, watchlists, backtester, recommendations) work without signing in.

Auth pages (/accounts/*, /register/, /activate/, /admin/) are EXCLUDED from
auto-login so that real Django authentication works correctly there — users
can register, log in, and reset passwords normally.
"""
from django.contrib.auth import get_user_model

_demo_user_cache = None

# URL prefixes that must NOT get demo_user assigned.
# Real Django auth (LoginView, register_view, PasswordResetView, etc.) lives
# under these paths and needs to see the actual AnonymousUser so it can
# show the forms and process credentials correctly.
_AUTH_PREFIXES = (
    '/accounts/',   # login, logout, password_reset, password_change, activate
    '/register/',   # registration form
    '/activate/',   # email-verification link handler
    '/admin/',      # Django admin (has its own auth)
)


class AutoLoginMiddleware:
    """
    Ensures every non-auth request has an active User (demo_user) so all site
    features can be explored without signing in.

    Auth pages are excluded — they work with AnonymousUser so the real login /
    register / password-reset flows function correctly.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── Skip for all auth-related paths ──────────────────────────────────
        # Without this guard, AutoLoginMiddleware would assign demo_user before
        # LoginView/register_view run, making request.user.is_authenticated=True
        # and causing both views to immediately redirect away (they redirect
        # already-authenticated users).  Result: forms are never shown. ❌
        if any(request.path.startswith(prefix) for prefix in _AUTH_PREFIXES):
            return self.get_response(request)

        # ── Assign demo_user to anonymous visitors on non-auth pages ─────────
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
