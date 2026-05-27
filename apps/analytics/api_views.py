"""
apps/analytics/api_views.py — JSON API endpoints for chart data
"""
import json
import logging
from datetime import date, timedelta

import pandas as pd
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from apps.funds.models import NAVHistory, Scheme
from apps.analytics.models import TrailingReturn, CalendarReturn, RiskMetrics
from apps.analytics.engine import simulate_sip
from apps.holdings.models import SectorAllocation

logger = logging.getLogger('mfanalysis')


def get_scheme_or_404(amfi_code):
    return get_object_or_404(Scheme, amfi_code=amfi_code)


@require_GET
def nav_chart_api(request, amfi_code):
    """Returns NAV history as [{date, nav}, ...] with optional ?days= filter."""
    scheme = get_scheme_or_404(amfi_code)
    days = request.GET.get('days')
    qs = NAVHistory.objects.filter(scheme=scheme).order_by('date')
    if days:
        try:
            cutoff = date.today() - timedelta(days=int(days))
            qs = qs.filter(date__gte=cutoff)
        except ValueError:
            pass
    data = list(qs.values('date', 'nav'))
    for r in data:
        r['date'] = r['date'].isoformat()
        r['nav'] = float(r['nav'])
    return JsonResponse({'data': data, 'scheme_name': scheme.scheme_name})


@require_GET
def returns_api(request, amfi_code):
    """Trailing returns for returns bar chart."""
    scheme = get_scheme_or_404(amfi_code)
    latest = TrailingReturn.objects.filter(scheme=scheme).order_by('-as_of').values('as_of').first()
    trailing = []
    if latest:
        trailing = list(
            TrailingReturn.objects.filter(scheme=scheme, as_of=latest['as_of'])
            .order_by('years')
            .values('period', 'cagr_pct', 'bm_cagr', 'excess', 'years')
        )
        for r in trailing:
            r['cagr_pct'] = float(r['cagr_pct']) if r['cagr_pct'] else None
            r['bm_cagr'] = float(r['bm_cagr']) if r['bm_cagr'] else None
            r['excess'] = float(r['excess']) if r['excess'] else None
    return JsonResponse({'trailing': trailing})


@require_GET
def calendar_api(request, amfi_code):
    """Calendar year returns."""
    scheme = get_scheme_or_404(amfi_code)
    calendar = list(
        CalendarReturn.objects.filter(scheme=scheme)
        .order_by('year')
        .values('year', 'return_pct', 'bm_return', 'outperformed')
    )
    for r in calendar:
        r['return_pct'] = float(r['return_pct']) if r['return_pct'] else None
        r['bm_return'] = float(r['bm_return']) if r['bm_return'] else None
    return JsonResponse({'calendar': calendar})


@require_GET
def drawdown_api(request, amfi_code):
    """Compute and return drawdown series from stored NAV."""
    scheme = get_scheme_or_404(amfi_code)
    qs = NAVHistory.objects.filter(scheme=scheme).order_by('date').values('date', 'nav')
    if not qs.exists():
        return JsonResponse({'data': []})
    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    df['nav'] = df['nav'].astype(float)
    df = df.set_index('date').sort_index()
    running_max = df['nav'].cummax()
    df['drawdown'] = (df['nav'] - running_max) / running_max * 100
    # Downsample to weekly for performance
    df_weekly = df.resample('W').last().dropna()
    data = [{'date': idx.date().isoformat(), 'drawdown': round(row['drawdown'], 4)} for idx, row in df_weekly.iterrows()]
    return JsonResponse({'data': data})


@require_GET
def risk_api(request, amfi_code):
    """Risk metrics for the fund."""
    scheme = get_scheme_or_404(amfi_code)
    result = {}
    for period in ['3Y', '5Y']:
        rm = RiskMetrics.objects.filter(scheme=scheme, period=period).order_by('-as_of').first()
        if rm:
            result[period] = {
                'std_dev_ann': float(rm.std_dev_ann) if rm.std_dev_ann else None,
                'sharpe_ratio': float(rm.sharpe_ratio) if rm.sharpe_ratio else None,
                'sortino_ratio': float(rm.sortino_ratio) if rm.sortino_ratio else None,
                'max_drawdown': float(rm.max_drawdown) if rm.max_drawdown else None,
                'beta': float(rm.beta) if rm.beta else None,
                'alpha_ann': float(rm.alpha_ann) if rm.alpha_ann else None,
                'r_squared': float(rm.r_squared) if rm.r_squared else None,
            }
    return JsonResponse(result)


@require_GET
def holdings_api(request, amfi_code):
    """Top holdings as JSON."""
    from apps.holdings.models import Holding
    scheme = get_scheme_or_404(amfi_code)
    last = Holding.objects.filter(scheme=scheme).order_by('-as_of_month').values('as_of_month').first()
    if not last:
        return JsonResponse({'holdings': [], 'as_of': None})
    holdings = list(
        Holding.objects.filter(scheme=scheme, as_of_month=last['as_of_month'])
        .order_by('-weight_pct').values(
            'security_name', 'sector', 'weight_pct', 'isin', 'forward_pe', 'holding_type'
        )[:30]
    )
    for h in holdings:
        h['weight_pct'] = float(h['weight_pct']) if h['weight_pct'] else None
        h['forward_pe'] = float(h['forward_pe']) if h['forward_pe'] else None
    return JsonResponse({'holdings': holdings, 'as_of': last['as_of_month'].isoformat()})


@require_GET
def sector_api(request, amfi_code):
    """Sector allocation as JSON for Plotly donut."""
    scheme = get_scheme_or_404(amfi_code)
    last = SectorAllocation.objects.filter(scheme=scheme).order_by('-as_of_month').values('as_of_month').first()
    if not last:
        return JsonResponse({'sectors': []})
    sectors = list(
        SectorAllocation.objects.filter(scheme=scheme, as_of_month=last['as_of_month'])
        .order_by('-weight_pct').values('sector', 'weight_pct')
    )
    for s in sectors:
        s['weight_pct'] = float(s['weight_pct']) if s['weight_pct'] else 0
    return JsonResponse({'sectors': sectors, 'as_of': last['as_of_month'].isoformat()})


@require_http_methods(["POST"])
def sip_simulate_api(request, amfi_code):
    """SIP simulation endpoint. POST {amount, years} → returns simulation results."""
    scheme = get_scheme_or_404(amfi_code)
    try:
        body = json.loads(request.body)
        amount = float(body.get('amount', 10000))
        years = int(body.get('years', 10))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': 'Invalid input parameters.'}, status=400)

    qs = NAVHistory.objects.filter(scheme=scheme).order_by('date').values('date', 'nav')
    if not qs.exists():
        return JsonResponse({'error': 'No NAV data available. Run ingest_nav first.'})

    df = pd.DataFrame(list(qs))
    df['date'] = pd.to_datetime(df['date'])
    df['nav'] = df['nav'].astype(float)
    nav_series = df.set_index('date')['nav']

    # Trim to requested years
    from_date = nav_series.index[-1] - pd.DateOffset(years=years)
    nav_series = nav_series[nav_series.index >= from_date]

    if len(nav_series) < 12:
        return JsonResponse({'error': f'Insufficient NAV history for {years}-year simulation.'})

    result = simulate_sip(nav_series, monthly_amount=amount)
    if result is None:
        return JsonResponse({'error': 'SIP simulation returned no result.'})

    # Convert numpy types for JSON serialization
    return JsonResponse({k: float(v) if hasattr(v, '__float__') else v for k, v in result.items()})
