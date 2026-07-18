"""apps/benchmarks/api_views.py — Market index endpoints"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .market_data import get_live_indices
from .registry import MARKET_INDICES

logger = logging.getLogger('mfanalysis')

# ── Default keys shown to everyone (including anonymous users) ─────────────────
DEFAULT_METRIC_KEYS = ['nifty50', 'sensex', 'midcap', 'smallcap', 'nifty200', 'usdinr']

# Full catalogue: key → label (built from registry, stable)
ALL_METRICS = {idx['key']: idx['label'] for idx in MARKET_INDICES}


def _user_metric_keys(request) -> list[str]:
    """Return the ordered metric keys for the current user.

    - Anonymous → DEFAULT_METRIC_KEYS
    - Authenticated, no profile → DEFAULT_METRIC_KEYS
    - Authenticated, has profile with non-empty list → their saved list
    """
    if not request.user.is_authenticated:
        return DEFAULT_METRIC_KEYS
    try:
        from .models import UserMarketStripProfile
        profile = UserMarketStripProfile.objects.filter(user=request.user).first()
        if profile and profile.metrics:
            return [k for k in profile.metrics if k in ALL_METRICS]
    except Exception as exc:
        logger.warning('_user_metric_keys error: %s', exc)
    return DEFAULT_METRIC_KEYS


@require_GET
def market_indices_api(request):
    """
    GET /api/market/indices/
    Returns live index values as JSON.
    """
    indices = get_live_indices()
    return JsonResponse({'indices': indices})


@require_GET
def market_strip_partial(request):
    """
    GET /api/market/strip/
    Returns HTML partial for HTMX market strip refresh.
    Respects per-user metric preferences (DB-persisted for logged-in users).
    """
    chosen_keys = _user_metric_keys(request)
    all_indices = get_live_indices()
    # Build an ordered lookup
    index_map = {idx['key']: idx for idx in all_indices}
    indices = [index_map[k] for k in chosen_keys if k in index_map]
    # Fallback: if no valid indices resolved, show all
    if not indices:
        indices = all_indices

    return render(request, 'benchmarks/_market_strip.html', {
        'indices': indices,
        'all_metrics': ALL_METRICS,
        'chosen_keys': chosen_keys,
        'is_authenticated': request.user.is_authenticated,
    })


@require_GET
def market_metrics_catalogue(request):
    """
    GET /api/market/metrics/
    Returns the full catalogue of available metric keys + labels.
    Used by the Manage Metrics modal.
    """
    all_indices = get_live_indices()
    index_map = {idx['key']: idx for idx in all_indices}
    chosen_keys = _user_metric_keys(request)
    data = [
        {
            'key': idx['key'],
            'label': idx['label'],
            'selected': idx['key'] in chosen_keys,
        }
        for idx in MARKET_INDICES
        if idx['key'] in index_map
    ]
    return JsonResponse({'metrics': data, 'chosen': chosen_keys})


@require_POST
def save_market_strip_metrics(request):
    """
    POST /api/market/metrics/save/
    Body: {"metrics": ["nifty50", "sensex", ...]}
    Saves the user's chosen metric keys to DB.
    Requires authentication.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    try:
        from .models import UserMarketStripProfile
        data = json.loads(request.body)
        metrics = data.get('metrics', [])
        # Validate: only store known keys
        valid = [k for k in metrics if k in ALL_METRICS]
        profile, _ = UserMarketStripProfile.objects.get_or_create(user=request.user)
        profile.metrics = valid
        profile.save()
        return JsonResponse({'saved': True, 'count': len(valid), 'metrics': valid})
    except Exception as exc:
        logger.error('save_market_strip_metrics error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)
