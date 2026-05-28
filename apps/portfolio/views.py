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

    # Auto-fix missing NAV/units for transactions (e.g. from manual entry before NAV was fetched)
    from django.db.models import Q
    unprocessed_txs = portfolio.transactions.filter(Q(units=0.0) | Q(nav__isnull=True))
    if unprocessed_txs.exists():
        from apps.funds.services import get_or_fetch_nav_history
        from apps.funds.models import NAVHistory
        from decimal import Decimal
        # Group by scheme to avoid duplicate fetches
        schemes_to_fetch = set(tx.scheme for tx in unprocessed_txs if tx.scheme)
        for scheme in schemes_to_fetch:
            get_or_fetch_nav_history(scheme)
            
        # Re-fetch and re-calculate
        for tx in unprocessed_txs:
            if tx.scheme:
                nav_history = NAVHistory.objects.filter(scheme=tx.scheme, date__lte=tx.tx_date).order_by('-date').first()
                if nav_history:
                    tx.nav = nav_history.nav
                    tx.units = Decimal(str(float(tx.amount) / float(tx.nav)))
                    tx.save(update_fields=['nav', 'units'])

    transactions = portfolio.transactions.select_related('scheme').order_by('tx_date')

    from apps.portfolio.services.analytics import (
        calculate_portfolio_xirr,
        calculate_xirr,
        simulate_benchmark,
        calculate_diversification_score,
        calculate_portfolio_ratios,
        get_portfolio_journey
    )
    
    # Group by scheme and compute current value + per-fund XIRR
    fund_summary = _compute_portfolio_summary(transactions)
    _enrich_fund_xirr(fund_summary, transactions)

    total_invested = sum(f['invested'] for f in fund_summary)
    total_current = sum(f['current_value'] for f in fund_summary if f['current_value'])
    total_gain = total_current - total_invested
    abs_return = (total_gain / total_invested * 100) if total_invested else 0
    
    portfolio_xirr = calculate_portfolio_xirr(portfolio)
    benchmark_current, benchmark_xirr = simulate_benchmark(portfolio, "^NSEI")
    
    diversification_score, diversification_comment = calculate_diversification_score(portfolio)
    ratios = calculate_portfolio_ratios(portfolio)
    
    journey_dates, journey_invested, journey_value = get_portfolio_journey(portfolio)
    
    # Portfolio composition analysis
    composition = _compute_portfolio_composition(fund_summary, transactions)

    return render(request, 'portfolio/dashboard.html', {
        'portfolio': portfolio,
        'fund_summary': fund_summary,
        'total_invested': total_invested,
        'total_current': total_current,
        'total_gain': total_gain,
        'abs_return': abs_return,
        'portfolio_xirr': portfolio_xirr,
        'benchmark_xirr': benchmark_xirr,
        'diversification_score': diversification_score,
        'diversification_comment': diversification_comment,
        'ratios': ratios,
        'journey_dates': json.dumps(journey_dates),
        'journey_invested': json.dumps(journey_invested),
        'journey_value': json.dumps(journey_value),
        'tx_count': transactions.count(),
        'transactions': transactions.order_by('-tx_date'),
        'composition': composition,
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
            'xirr': None,  # Enriched separately
        })
    return sorted(result, key=lambda x: -(x['current_value'] or 0))


def _enrich_fund_xirr(fund_summary, transactions):
    """Compute and attach per-fund XIRR to each entry in fund_summary in-place."""
    from apps.portfolio.services.analytics import calculate_xirr
    tx_list = list(transactions)
    for fund in fund_summary:
        amfi = fund['amfi_code']
        name = fund['scheme_name']
        cfs = []
        for tx in tx_list:
            key = tx.amfi_code or tx.scheme_name
            if key != amfi and tx.scheme_name != name:
                continue
            amt = float(tx.amount)
            if tx.tx_type in ('BUY', 'SIP', 'SWITCH_IN'):
                cfs.append((tx.tx_date, -amt))
            elif tx.tx_type in ('SELL', 'REDEEM', 'SWITCH_OUT'):
                cfs.append((tx.tx_date, amt))
        if fund['current_value'] and fund['current_value'] > 0:
            cfs.append((date.today(), fund['current_value']))
        try:
            xirr_val = calculate_xirr(cfs)
            fund['xirr'] = round(xirr_val, 2) if xirr_val is not None else None
        except Exception:
            fund['xirr'] = None


def _compute_portfolio_composition(fund_summary, transactions):
    """Compute sector allocation, asset class allocation, concentration (HHI), and turnover."""
    import datetime
    from collections import defaultdict

    total_value = sum(f['current_value'] for f in fund_summary if f['current_value']) or 1

    # Asset-class allocation by scheme category
    asset_class_map = defaultdict(float)
    sector_map = defaultdict(float)
    weights = []

    for f in fund_summary:
        val = f['current_value'] or 0
        pct = val / total_value * 100
        weights.append(pct / 100)
        scheme = f['scheme']
        if scheme:
            cat = scheme.scheme_category or 'Unknown'
            # Derive broad asset class
            if 'Debt' in cat or 'Liquid' in cat or 'Bond' in cat or 'Duration' in cat or 'Credit' in cat:
                asset_class = 'Debt'
            elif 'Hybrid' in cat or 'Balanced' in cat or 'Multi Asset' in cat:
                asset_class = 'Hybrid'
            elif 'Gold' in cat or 'Commodity' in cat:
                asset_class = 'Commodity'
            elif 'International' in cat or 'Global' in cat or 'Overseas' in cat:
                asset_class = 'International Equity'
            else:
                asset_class = 'Domestic Equity'
            asset_class_map[asset_class] += pct

            # Sector from fund sub-category or name
            name_lower = (scheme.scheme_name or '').lower()
            if 'large cap' in name_lower or 'large & mid' in name_lower:
                sector = 'Large Cap'
            elif 'mid cap' in name_lower:
                sector = 'Mid Cap'
            elif 'small cap' in name_lower:
                sector = 'Small Cap'
            elif 'flexi' in name_lower or 'multi cap' in name_lower:
                sector = 'Multi/Flexi Cap'
            elif 'elss' in name_lower or 'tax sav' in name_lower:
                sector = 'ELSS'
            elif 'index' in name_lower or 'nifty' in name_lower or 'sensex' in name_lower:
                sector = 'Index'
            elif 'international' in name_lower or 'global' in name_lower or 'us ' in name_lower:
                sector = 'International'
            elif 'debt' in name_lower or 'liquid' in name_lower or 'bond' in name_lower:
                sector = 'Debt'
            elif 'hybrid' in name_lower or 'balanced' in name_lower:
                sector = 'Hybrid'
            else:
                sector = 'Other Equity'
            sector_map[sector] += pct
        else:
            asset_class_map['Unknown'] += pct
            sector_map['Unknown'] += pct

    # Concentration: Herfindahl-Hirschman Index (0–1, lower = more diversified)
    hhi = sum(w ** 2 for w in weights)
    if len(weights) > 1:
        hhi_norm = (hhi - 1 / len(weights)) / (1 - 1 / len(weights))  # normalized 0-1
    else:
        hhi_norm = 1.0
    concentration_label = (
        'High Concentration' if hhi_norm > 0.6
        else 'Moderate Concentration' if hhi_norm > 0.3
        else 'Well Diversified'
    )

    # Turnover: count buy transactions in last 12 months
    one_year_ago = datetime.date.today() - datetime.timedelta(days=365)
    tx_list = list(transactions)
    recent_buys = sum(
        1 for tx in tx_list
        if tx.tx_type in ('BUY', 'SIP') and tx.tx_date >= one_year_ago
    )

    return {
        'asset_classes': dict(sorted(asset_class_map.items(), key=lambda x: -x[1])),
        'sectors': dict(sorted(sector_map.items(), key=lambda x: -x[1])),
        'hhi': round(hhi_norm, 3),
        'concentration_label': concentration_label,
        'turnover_buys_12m': recent_buys,
        'num_funds': len(fund_summary),
    }


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
        'zipped_matrix': list(zip(schemes, overlap_matrix)),
        'matrix_json': json.dumps(overlap_matrix),
        'scheme_names_json': json.dumps([s.scheme_name[:40] for s in schemes]),
    })


@login_required
def portfolio_benchmark_view(request, pk):
    """Compare portfolio returns vs Blended Benchmark and Nifty 50."""
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    
    from apps.benchmarks.models import BenchmarkIndex
    from apps.portfolio.services.analytics import (
        get_default_blended_benchmark_weights,
        simulate_custom_benchmark,
        get_portfolio_journey,
        compute_advanced_risk_metrics,
        calculate_portfolio_xirr
    )
    
    indices = BenchmarkIndex.objects.filter(is_active=True).order_by('name')
    
    custom_weights = {}
    for key, value in request.GET.items():
        if key.startswith('weight_'):
            try:
                bm_name = key.replace('weight_', '')
                weight = float(value) / 100.0 # user provides %
                if weight > 0:
                    custom_weights[bm_name] = weight
            except ValueError:
                pass
                
    if custom_weights:
        total_w = sum(custom_weights.values())
        if total_w > 0:
            custom_weights = {k: v/total_w for k, v in custom_weights.items()}
        weights_dict = custom_weights
    else:
        weights_dict = get_default_blended_benchmark_weights(portfolio)
        
    formatted_weights = {k: round(v * 100, 2) for k, v in weights_dict.items()}
    
    port_dates, port_invested, port_values = get_portfolio_journey(portfolio)
    port_current = port_values[-1] if port_values else 0
    port_xirr = calculate_portfolio_xirr(portfolio)
    
    blend_current, blend_xirr, blend_dates, blend_values = simulate_custom_benchmark(portfolio, weights_dict)
    nifty_current, nifty_xirr, nifty_dates, nifty_values = simulate_custom_benchmark(portfolio, {'NIFTY 50': 1.0})
    
    blend_metrics = compute_advanced_risk_metrics(port_values, blend_values) if port_values and blend_values else {}
    nifty_metrics = compute_advanced_risk_metrics(port_values, nifty_values) if port_values and nifty_values else {}
    
    return render(request, 'portfolio/benchmark.html', {
        'portfolio': portfolio,
        'indices': indices,
        'weights_dict': formatted_weights,
        'port_current': port_current,
        'port_xirr': port_xirr,
        'blend_current': blend_current,
        'blend_xirr': blend_xirr,
        'nifty_current': nifty_current,
        'nifty_xirr': nifty_xirr,
        'blend_metrics': blend_metrics,
        'nifty_metrics': nifty_metrics,
        'journey_dates': json.dumps(port_dates),
        'port_values': json.dumps(port_values),
        'blend_values': json.dumps(blend_values),
        'nifty_values': json.dumps(nifty_values),
    })


@login_required
def portfolio_rebalance_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    return render(request, 'portfolio/rebalance.html', {
        'portfolio': portfolio,
    })

import calendar
from datetime import datetime

def _add_months(d, months):
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)

@login_required
def portfolio_manual_entry_view(request):
    return render(request, 'portfolio/manual_entry.html')

@login_required
def portfolio_manual_entry_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        data = json.loads(request.body)
        portfolio_name = data.get('portfolio_name', 'My Manual Portfolio')
        transactions_data = data.get('transactions', [])
        
        if not transactions_data:
            return JsonResponse({'error': 'No transactions provided'}, status=400)
            
        portfolio = Portfolio.objects.create(user=request.user, name=portfolio_name, is_private=True)
        tx_objs = []
        
        for tx in transactions_data:
            amfi_code = tx.get('scheme_id') # Front end sends scheme_id key but value is actually amfi_code
            tx_type = tx['tx_type']
            amount = float(tx['amount'])
            start_date = datetime.strptime(tx['start_date'], '%Y-%m-%d').date()
            
            try:
                scheme = Scheme.objects.get(amfi_code=amfi_code)
            except Scheme.DoesNotExist:
                continue
                
            # Fetch NAV history on-demand so units are calculated correctly
            from apps.funds.services import get_or_fetch_nav_history
            get_or_fetch_nav_history(scheme)
                
            dates_to_process = []
            if tx_type in ('SIP', 'SWP'):
                end_date = datetime.strptime(tx['end_date'], '%Y-%m-%d').date()
                curr_date = start_date
                while curr_date <= end_date:
                    dates_to_process.append(curr_date)
                    curr_date = _add_months(curr_date, 1)
            else:
                dates_to_process.append(start_date)
                
            for d in dates_to_process:
                # Find closest NAV on or before this date
                nav_history = NAVHistory.objects.filter(scheme=scheme, date__lte=d).order_by('-date').first()
                if nav_history:
                    nav = float(nav_history.nav)
                    units = amount / nav
                else:
                    nav = None
                    units = 0.0 # Will need user to manually fix if no NAV found
                    
                mapped_tx_type = 'BUY' if tx_type in ('BUY', 'SIP') else 'SELL'
                
                tx_objs.append(Transaction(
                    portfolio=portfolio,
                    scheme=scheme,
                    scheme_name=scheme.scheme_name,
                    amfi_code=scheme.amfi_code,
                    tx_type=mapped_tx_type,
                    tx_date=d,
                    units=units,
                    nav=nav,
                    amount=amount,
                    folio='MANUAL'
                ))
                
        Transaction.objects.bulk_create(tx_objs)
        
        return JsonResponse({
            'status': 'success',
            'portfolio_id': portfolio.id,
            'tx_count': len(tx_objs)
        })
    except Exception as e:
        logger.exception("Error processing manual entry")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def portfolio_forecast_api(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    
    # Extract query parameters
    model_type = request.GET.get('model', 'monte_carlo').lower()
    horizon_years = int(request.GET.get('horizon', 3))
    horizon_days = horizon_years * 365
    
    from apps.portfolio.services.forecasting import (
        simulate_monte_carlo,
        forecast_arima,
        forecast_machine_learning,
        calculate_ta_indicators,
        get_daily_portfolio_history
    )
    
    # Always include TA indicators for the consensus panel
    ta_data = calculate_ta_indicators(portfolio)
    
    forecast_data = None
    try:
        if model_type == 'monte_carlo':
            sims = int(request.GET.get('simulations', 250))
            vol_adj = float(request.GET.get('vol_adj', 0.0))
            forecast_data = simulate_monte_carlo(portfolio, horizon_days, sims, vol_adj)
        elif model_type == 'arima':
            p = int(request.GET.get('arima_p', 1))
            d = int(request.GET.get('arima_d', 1))
            q = int(request.GET.get('arima_q', 1))
            forecast_data = forecast_arima(portfolio, horizon_days, p, d, q)
        elif model_type == 'machine_learning':
            ml_model = request.GET.get('ml_model', 'RIDGE')
            lags = int(request.GET.get('ml_lags', 10))
            forecast_data = forecast_machine_learning(portfolio, horizon_days, ml_model, lags)
    except Exception as e:
        logger.exception(f"Forecasting model {model_type} failed")
        return JsonResponse({'error': f"Model execution failed: {str(e)}"}, status=400)
        
    # If the selected model failed or returned None, fall back to standard Monte Carlo
    if not forecast_data:
        try:
            forecast_data = simulate_monte_carlo(portfolio, horizon_days, 250, 0.0)
        except Exception:
            pass
            
    if not forecast_data:
        return JsonResponse({'error': 'Not enough historical NAV data to calculate forecast.'}, status=400)
        
    # Build historical daily series (last 90 days) for plot overlay
    hist_df = get_daily_portfolio_history(portfolio)
    hist_data = {}
    if not hist_df.empty:
        hist_subset = hist_df.tail(90)
        hist_data = {
            'dates': [d.strftime('%Y-%m-%d') for d in hist_subset['date']],
            'values': hist_subset['current_value'].tolist()
        }
        
    return JsonResponse({
        'forecast': forecast_data,
        'history': hist_data,
        'ta': ta_data
    })


# ─────────────────────────────────────────────────────────────────────────────
# BACKTESTER VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def portfolio_backtester_view(request):
    """Render the portfolio plan builder + backtester."""
    from apps.benchmarks.models import BenchmarkIndex

    indices = list(
        BenchmarkIndex.objects.filter(is_active=True).order_by('name').values('name', 'id')
    )
    return render(request, 'portfolio/backtester.html', {'indices': indices})


@login_required
def portfolio_fund_search_api(request):
    """
    AJAX fund search — returns matching MF schemes and indices.
    GET ?q=parag+parikh&type=all|scheme|index
    """
    q = request.GET.get('q', '').strip()
    src_type = request.GET.get('type', 'all')
    results = []

    if len(q) >= 2:
        if src_type in ('all', 'scheme'):
            from apps.funds.models import Scheme
            schemes = (
                Scheme.objects
                .filter(scheme_name__icontains=q, is_active=True, plan='GROWTH')
                .exclude(nav_latest__isnull=True)
                .order_by('-aum_cr')[:15]
                .values('amfi_code', 'scheme_name', 'fund_house', 'scheme_category',
                        'nav_latest', 'aum_cr', 'is_direct')
            )
            for s in schemes:
                results.append({
                    'type': 'scheme',
                    'id': s['amfi_code'],
                    'name': s['scheme_name'],
                    'sub': f"{s['fund_house']} · {s['scheme_category'][:45]}",
                    'nav': float(s['nav_latest']) if s['nav_latest'] else None,
                    'aum': float(s['aum_cr']) if s['aum_cr'] else None,
                    'is_direct': s['is_direct'],
                })

        if src_type in ('all', 'index'):
            from apps.benchmarks.models import BenchmarkIndex
            indices = (
                BenchmarkIndex.objects
                .filter(name__icontains=q, is_active=True)
                .order_by('name')[:10]
                .values('name', 'description')
            )
            for idx in indices:
                results.append({
                    'type': 'index',
                    'id': idx['name'],
                    'name': idx['name'],
                    'sub': idx.get('description', 'Index') or 'Index',
                    'nav': None,
                    'aum': None,
                    'is_direct': None,
                })

    return JsonResponse({'results': results})


@login_required
def portfolio_backtester_api(request):
    """
    POST endpoint — runs the plan simulation.

    Expected JSON body:
    {
      "funds": [
        {
          "label": "Parag Parikh Flexi Cap",
          "source_type": "scheme",     // "scheme" | "index"
          "source_id": "122639",        // amfi_code or index name
          "rules": [
            {
              "rule_type": "sip",
              "amount": 5000,
              "frequency": "monthly",
              "start_date": "2019-01-01",
              "end_date": null,
              "step_up_pct": 10
            },
            {
              "rule_type": "lumpsum",
              "amount": 50000,
              "lumpsum_date": "2020-03-23"
            }
          ]
        }
      ],
      "rebalance_mode": "annual",      // "none"|"annual"|"threshold"
      "rebalance_threshold": 5.0,
      "rebalance_anchor_month": 1,
      "debt_park_source_type": "index",
      "debt_park_id": "NIFTY LIQUID INDEX",
      "vol_threshold": 20,             // percent
      "start_date": null,
      "end_date": null
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from apps.portfolio.services.backtester import (
            InvestmentRule, FundPlan, PortfolioPlan, run_plan_simulation
        )

        raw_funds = data.get('funds', [])
        if not raw_funds:
            return JsonResponse({'error': 'Add at least one fund to your plan.'}, status=400)

        funds = []
        for fp in raw_funds:
            rules = []
            for r in fp.get('rules', []):
                def _parse_date(s):
                    if not s:
                        return None
                    try:
                        return date.fromisoformat(str(s))
                    except ValueError:
                        return None

                rules.append(InvestmentRule(
                    rule_type=str(r.get('rule_type', 'sip')),
                    amount=float(r.get('amount', 0)),
                    frequency=str(r.get('frequency', 'monthly')),
                    start_date=_parse_date(r.get('start_date')),
                    end_date=_parse_date(r.get('end_date')),
                    step_up_pct=float(r.get('step_up_pct', 0)),
                    lumpsum_date=_parse_date(r.get('lumpsum_date')),
                    sell_pct=float(r.get('sell_pct', 100)),
                    trigger=r.get('trigger') or None,
                    trigger_value=float(r['trigger_value']) if r.get('trigger_value') else None,
                ))

            if not rules:
                continue

            funds.append(FundPlan(
                label=str(fp.get('label', fp.get('source_id', 'Fund'))),
                source_type=str(fp.get('source_type', 'scheme')),
                source_id=str(fp.get('source_id', '')),
                rules=rules,
            ))

        if not funds:
            return JsonResponse({'error': 'No valid funds with rules found.'}, status=400)

        def _pd(s):
            if not s:
                return None
            try:
                return date.fromisoformat(str(s))
            except ValueError:
                return None

        plan = PortfolioPlan(
            funds=funds,
            rebalance_mode=str(data.get('rebalance_mode', 'none')),
            rebalance_threshold=float(data.get('rebalance_threshold', 5.0)),
            rebalance_anchor_month=int(data.get('rebalance_anchor_month', 1)),
            debt_park_source_type=str(data.get('debt_park_source_type', 'scheme')),
            debt_park_id=str(data.get('debt_park_id', '')),
            debt_park_name=str(data.get('debt_park_name', '')),
            vol_threshold=float(data.get('vol_threshold', 20)) / 100.0,
            start_date=_pd(data.get('start_date')),
            end_date=_pd(data.get('end_date')),
            debt_return_pct=float(data.get('debt_return_pct', 7.0)),
        )


        result = run_plan_simulation(plan)

        def ser(s):
            return {
                'strategy_key': s.strategy_key,
                'name': s.strategy_name,
                'description': s.description,
                'final_corpus': s.final_corpus,
                'total_invested': s.total_invested,
                'absolute_gain': s.absolute_gain,
                'absolute_return_pct': s.absolute_return_pct,
                'cagr': s.cagr,
                'xirr': s.xirr,
                'trailing_1y': s.trailing_1y,
                'trailing_3y': s.trailing_3y,
                'trailing_5y': s.trailing_5y,
                'rolling_5y_min': s.rolling_5y_min,
                'rolling_5y_max': s.rolling_5y_max,
                'rolling_5y_avg': s.rolling_5y_avg,
                'volatility_ann': s.volatility_ann,
                'max_drawdown': s.max_drawdown,
                'sharpe': s.sharpe,
                'sortino': s.sortino,
                'calendar_returns': s.calendar_returns,
                'downside_quarters': s.downside_quarters,
                'dates': s.dates,
                'portfolio_values': s.portfolio_values,
                'invested_cumulative': s.invested_cumulative,
                'equity_ratios': s.equity_ratios,
                'transactions': s.transactions if s.strategy_key == 'base' else [],
                'interpretation': s.interpretation,
            }

        return JsonResponse({
            'status': 'success',
            'start_date': result.start_date,
            'end_date': result.end_date,
            'plan_summary': result.plan_summary,
            'strategies': [ser(s) for s in result.strategies],
            'data_warnings': result.data_warnings,
            'conclusion': result.conclusion,
        })

    except Exception as exc:
        logger.exception("Backtester API error")
        return JsonResponse({'error': str(exc)}, status=400)
