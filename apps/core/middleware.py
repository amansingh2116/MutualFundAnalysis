"""
apps/core/middleware.py — Auto-login middleware for LOCAL DEVELOPMENT ONLY.
Automatically assigns a demo user to any unauthenticated request so all
features (portfolios, watchlists, backtester, recommendations) can be tested
without signing in during development.

⚠️  This middleware does NOTHING in production (when DEBUG=False).
In production, real Django authentication is used.  Users must register,
log in, and use forgot-password to reset their credentials.  All personal
data (portfolios, watchlists, settings) is stored per-user in CockroachDB.
"""
from django.conf import settings
from django.contrib.auth import get_user_model

_demo_user_cache = None

# URL prefixes that must NOT get demo_user assigned even in DEBUG.
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
    DEV ONLY: ensures every non-auth request has an active User (demo_user)
    so all site features can be explored without signing in locally.

    In PRODUCTION (DEBUG=False) this middleware is a complete no-op passthrough.
    Auth pages are excluded even in DEBUG so the real login/register/password-
    reset flows function correctly.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── Production: bypass entirely — use real Django auth ────────────────
        if not getattr(settings, 'DEBUG', False):
            return self.get_response(request)

        # ── Skip for all auth-related paths ──────────────────────────────────
        # Without this guard, AutoLoginMiddleware would assign demo_user before
        # LoginView/register_view run, making request.user.is_authenticated=True
        # and causing both views to immediately redirect away (they redirect
        # already-authenticated users).  Result: forms are never shown. ❌
        if any(request.path.startswith(prefix) for prefix in _AUTH_PREFIXES):
            return self.get_response(request)

        # ── Assign demo_user to anonymous visitors on non-auth pages (DEV) ───
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
