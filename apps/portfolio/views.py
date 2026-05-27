"""apps/portfolio/views.py — Portfolio analysis views"""
import json
import logging
from datetime import date

import numpy as np
import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from apps.funds.models import NAVHistory, Scheme
from apps.holdings.models import Holding
from apps.portfolio.models import Portfolio, Transaction
from apps.portfolio.parsers import parse_portfolio_file

logger = logging.getLogger('mfanalysis')


@login_required
def portfolio_list_view(request):
    portfolios = Portfolio.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'portfolio/list.html', {'portfolios': portfolios})


@login_required
def portfolio_upload_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', 'My Portfolio').strip() or 'My Portfolio'
        file_obj = request.FILES.get('portfolio_file')
        if not file_obj:
            messages.error(request, 'Please upload an Excel or CSV file.')
            return render(request, 'portfolio/upload.html')
        try:
            transactions = parse_portfolio_file(file_obj)
        except ValueError as e:
            messages.error(request, str(e))
            return render(request, 'portfolio/upload.html')

        # Create portfolio
        portfolio = Portfolio.objects.create(user=request.user, name=name, is_private=True)

        # Save transactions
        tx_objs = []
        for tx in transactions:
            scheme = None
            if tx.get('matched_scheme') and tx['match_score'] >= 80:
                try:
                    scheme = Scheme.objects.get(id=tx['matched_scheme']['id'])
                except Scheme.DoesNotExist:
                    pass
            tx_objs.append(Transaction(
                portfolio=portfolio,
                scheme=scheme,
                scheme_name=tx['scheme_name'],
                amfi_code=tx['matched_scheme']['amfi_code'] if scheme else '',
                tx_type=tx['tx_type'],
                tx_date=tx['tx_date'] or date.today(),
                units=tx['units'],
                nav=tx['nav'],
                amount=tx['amount'],
                folio=tx['folio'],
            ))
        Transaction.objects.bulk_create(tx_objs)

        matched = sum(1 for tx in transactions if tx.get('match_score', 0) >= 80)
        messages.success(
            request,
            f'Portfolio "{name}" created with {len(transactions)} transactions ({matched} matched to funds).'
        )
        return redirect('portfolio:dashboard', pk=portfolio.pk)

    return render(request, 'portfolio/upload.html')


@login_required
def portfolio_dashboard_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    transactions = portfolio.transactions.select_related('scheme').order_by('tx_date')

    # Group by scheme and compute current value + XIRR
    fund_summary = _compute_portfolio_summary(transactions)

    total_invested = sum(f['invested'] for f in fund_summary)
    total_current = sum(f['current_value'] for f in fund_summary)
    total_gain = total_current - total_invested
    abs_return = (total_gain / total_invested * 100) if total_invested else 0

    return render(request, 'portfolio/dashboard.html', {
        'portfolio': portfolio,
        'fund_summary': fund_summary,
        'total_invested': total_invested,
        'total_current': total_current,
        'total_gain': total_gain,
        'abs_return': abs_return,
        'tx_count': transactions.count(),
    })


def _compute_portfolio_summary(transactions):
    """Group transactions by scheme and compute invested, units, current value."""
    from collections import defaultdict
    fund_data = defaultdict(lambda: {'invested': 0, 'units': 0, 'scheme': None, 'scheme_name': ''})

    for tx in transactions:
        key = tx.amfi_code or tx.scheme_name
        d = fund_data[key]
        d['scheme'] = tx.scheme
        d['scheme_name'] = tx.scheme_name

        if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN'):
            d['invested'] += float(tx.amount)
            d['units'] += float(tx.units)
        elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
            d['invested'] -= float(tx.amount)
            d['units'] -= float(tx.units)

    result = []
    for key, d in fund_data.items():
        if d['units'] <= 0:
            continue
        scheme = d['scheme']
        nav_latest = float(scheme.nav_latest) if scheme and scheme.nav_latest else None
        current_value = d['units'] * nav_latest if nav_latest else None
        gain = (current_value - d['invested']) if current_value is not None else None
        result.append({
            'amfi_code': key,
            'scheme_name': d['scheme_name'],
            'scheme': scheme,
            'invested': round(d['invested'], 2),
            'units': round(d['units'], 4),
            'nav_latest': nav_latest,
            'current_value': round(current_value, 2) if current_value else None,
            'gain': round(gain, 2) if gain is not None else None,
            'gain_pct': round(gain / d['invested'] * 100, 2) if gain is not None and d['invested'] else None,
        })
    return sorted(result, key=lambda x: -(x['current_value'] or 0))


@login_required
def portfolio_delete_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    if request.method == 'POST':
        portfolio.delete()
        messages.success(request, 'Portfolio deleted.')
    return redirect('portfolio:list')


@login_required
def portfolio_overlap_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    transactions = portfolio.transactions.filter(scheme__isnull=False).select_related('scheme')
    schemes = list({tx.scheme for tx in transactions if tx.scheme})

    overlap_matrix = []
    if len(schemes) >= 2:
        today_month = date(date.today().year, date.today().month, 1)
        for i, s1 in enumerate(schemes):
            row = []
            h1 = {
                h['security_name']: float(h['weight_pct'])
                for h in Holding.objects.filter(scheme=s1).order_by('-as_of_month').values('security_name', 'weight_pct')[:50]
            }
            for j, s2 in enumerate(schemes):
                if i == j:
                    row.append(100.0)
                    continue
                h2 = {
                    h['security_name']: float(h['weight_pct'])
                    for h in Holding.objects.filter(scheme=s2).order_by('-as_of_month').values('security_name', 'weight_pct')[:50]
                }
                common = set(h1.keys()) & set(h2.keys())
                score = sum(min(h1[n], h2[n]) for n in common)
                row.append(round(score, 1))
            overlap_matrix.append(row)

    return render(request, 'portfolio/overlap.html', {
        'portfolio': portfolio,
        'schemes': schemes,
        'overlap_matrix': overlap_matrix,
        'matrix_json': json.dumps(overlap_matrix),
        'scheme_names_json': json.dumps([s.scheme_name[:40] for s in schemes]),
    })


@login_required
def portfolio_benchmark_view(request, pk):
    """Compare portfolio returns vs Nifty 50."""
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    return render(request, 'portfolio/benchmark.html', {
        'portfolio': portfolio,
        'benchmark': 'NIFTY 50 (Price Index)',
        'note': 'Benchmark simulation coming soon — requires NAV data for your funds.',
    })


@login_required
def portfolio_rebalance_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    return render(request, 'portfolio/rebalance.html', {
        'portfolio': portfolio,
    })
