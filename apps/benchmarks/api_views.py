"""apps/benchmarks/api_views.py — Market index endpoints"""
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .market_data import get_live_indices


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
    Cached 15 minutes.
    """
    indices = get_live_indices()
    return render(request, 'benchmarks/_market_strip.html', {'indices': indices})
