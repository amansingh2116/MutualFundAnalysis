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
from apps.analytics.engine import simulate_sip

logger = logging.getLogger('mfanalysis')


def get_scheme_or_404(amfi_code):
    return get_object_or_404(Scheme, amfi_code=amfi_code)


def _rebased_benchmark_rows(nav_rows, benchmark_series: pd.Series) -> list[dict]:
    if not nav_rows or benchmark_series is None or benchmark_series.empty:
        return []
    try:
        first_nav = float(nav_rows[0]['nav'])
        start = pd.Timestamp(nav_rows[0]['date'])
        end = pd.Timestamp(nav_rows[-1]['date'])
        bm = benchmark_series[(benchmark_series.index >= start) & (benchmark_series.index <= end)].dropna()
        if len(bm) < 2:
            return []
        base = float(bm.iloc[0])
        if not base:
            return []
        rebased = bm / base * first_nav
        return [
            {
                'date': idx.date().isoformat(),
                'value': round(float(value), 4),
                'raw_value': round(float(bm.loc[idx]), 4),
            }
            for idx, value in rebased.items()
        ]
    except Exception as exc:
        logger.info("Could not rebase benchmark chart rows: %s", exc)
        return []


@require_GET
def nav_chart_api(request, amfi_code):
    """Returns NAV history as [{date, nav}, ...] with optional ?days= filter."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    days = request.GET.get('days')
    data = snapshot.nav_rows
    if days:
        try:
            cutoff = date.today() - timedelta(days=int(days))
            data = [r for r in data if date.fromisoformat(r['date']) >= cutoff]
        except ValueError:
            pass
    benchmark_data = _rebased_benchmark_rows(data, snapshot.benchmark_series)
    return JsonResponse({
        'data': data,
        'benchmark_data': benchmark_data,
        'scheme_name': scheme.scheme_name,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def returns_api(request, amfi_code):
    """Trailing returns for returns bar chart."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    trailing = [
        {
            'period': r.period,
            'cagr_pct': float(r.cagr_pct) if r.cagr_pct is not None else None,
            'bm_cagr': float(r.bm_cagr) if r.bm_cagr is not None else None,
            'excess': float(r.excess) if r.excess is not None else None,
            'years': float(r.years) if r.years is not None else None,
        }
        for r in snapshot.trailing_returns
    ]
    return JsonResponse({
        'trailing': trailing,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def calendar_api(request, amfi_code):
    """Calendar year returns."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    calendar = [
        {
            'year': r.year,
            'return_pct': float(r.return_pct) if r.return_pct is not None else None,
            'bm_return': float(r.bm_return) if r.bm_return is not None else None,
            'outperformed': bool(r.outperformed) if r.outperformed is not None else None,
        }
        for r in sorted(snapshot.calendar_returns, key=lambda row: row.year)
    ]
    return JsonResponse({
        'calendar': calendar,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })


@require_GET
def drawdown_api(request, amfi_code):
    """Compute and return drawdown series from stored NAV."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    data = [{'date': r.date, 'drawdown': round(r.drawdown, 4)} for r in snapshot.drawdown]
    return JsonResponse({'data': data})


@require_GET
def risk_api(request, amfi_code):
    """Risk metrics for the fund."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    result = {}
    for period in ['3Y', '5Y']:
        rm = getattr(snapshot, f"risk_{period.lower()}", None)
        if rm:
            result[period] = {
                'std_dev_ann': float(rm.std_dev_ann) if rm.std_dev_ann is not None else None,
                'sharpe_ratio': float(rm.sharpe_ratio) if rm.sharpe_ratio is not None else None,
                'sortino_ratio': float(rm.sortino_ratio) if rm.sortino_ratio is not None else None,
                'max_drawdown': float(rm.max_drawdown) if rm.max_drawdown is not None else None,
                'beta': float(rm.beta) if rm.beta is not None else None,
                'alpha_ann': float(rm.alpha_ann) if rm.alpha_ann is not None else None,
                'r_squared': float(rm.r_squared) if rm.r_squared is not None else None,
                'tracking_error': float(rm.tracking_error) if rm.tracking_error is not None else None,
                'info_ratio': float(rm.info_ratio) if rm.info_ratio is not None else None,
                'upside_capture': float(rm.upside_capture) if rm.upside_capture is not None else None,
                'downside_capture': float(rm.downside_capture) if rm.downside_capture is not None else None,
                'rf_rate_pct': float(rm.rf_rate_pct) if rm.rf_rate_pct is not None else None,
                'as_of': rm.as_of.isoformat() if getattr(rm.as_of, 'isoformat', None) else rm.as_of,
            }
    payload = dict(result)
    payload.update({
        'risk': result,
        'benchmark_name': snapshot.benchmark_display_name,
        'benchmark_note': snapshot.benchmark_note,
    })
    return JsonResponse(payload)


@require_GET
def holdings_api(request, amfi_code):
    """Top holdings as JSON — uses lightweight snapshot that skips benchmark fetch."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_portfolio_snapshot

    snapshot = get_portfolio_snapshot(scheme)
    holdings = [
        {
            'security_name': h.security_name,
            'sector': h.sector,
            'weight_pct': float(h.weight_pct) if h.weight_pct is not None else None,
            'isin': h.isin,
            'forward_pe': float(h.forward_pe) if h.forward_pe is not None else None,
            'holding_type': h.holding_type,
        }
        for h in snapshot.top_holdings
    ]
    return JsonResponse({'holdings': holdings, 'as_of': snapshot.holdings_month.isoformat() if snapshot.holdings_month else None})


@require_GET
def sector_api(request, amfi_code):
    """Sector allocation as JSON for Plotly donut — uses lightweight snapshot that skips benchmark fetch."""
    scheme = get_scheme_or_404(amfi_code)
    from apps.funds.runtime import get_portfolio_snapshot

    snapshot = get_portfolio_snapshot(scheme)
    sectors = [{'sector': s.sector, 'weight_pct': float(s.weight_pct) if s.weight_pct else 0} for s in snapshot.sector_alloc]
    return JsonResponse({'sectors': sectors, 'as_of': snapshot.holdings_month.isoformat() if snapshot.holdings_month else None})


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

    from apps.funds.runtime import get_runtime_snapshot

    snapshot = get_runtime_snapshot(scheme)
    nav_series = snapshot.nav_series
    if nav_series.empty:
        return JsonResponse({'error': 'No NAV data available from mfapi.in right now.'})

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
