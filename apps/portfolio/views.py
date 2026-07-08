"""apps/portfolio/views.py — Portfolio analysis views"""
import calendar
import json
import logging
from datetime import date, datetime

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
from apps.portfolio.models import Portfolio, SavedStrategy, Transaction
from apps.portfolio.parsers import parse_portfolio_file

logger = logging.getLogger('mfanalysis')


def json_login_required(view_func):
    """
    Like @login_required but returns JSON 401 for AJAX/API calls instead of
    redirecting to the login page (which would cause "Unexpected token '<'" errors).
    Detects AJAX by checking Accept header or X-Requested-With.
    """
    from functools import wraps
    from django.http import JsonResponse

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            is_ajax = (
                request.headers.get('Accept', '').startswith('application/json')
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.content_type == 'application/json'
            )
            if is_ajax:
                return JsonResponse({'error': 'Authentication required. Please log in.', 'redirect': '/accounts/login/'}, status=401)
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return view_func(request, *args, **kwargs)
    return _wrapped


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
        # Ensure invested is never negative (can happen when proceeds > cost basis)
        invested = max(round(d['invested'], 2), 0)
        gain = (current_value - invested) if current_value is not None else None
        result.append({
            'amfi_code': key,
            'scheme_name': d['scheme_name'],
            'scheme': scheme,
            'invested': invested,
            'units': round(d['units'], 4),
            'nav_latest': nav_latest,
            'current_value': round(current_value, 2) if current_value else None,
            'gain': round(gain, 2) if gain is not None else None,
            'gain_pct': round(gain / invested * 100, 2) if gain is not None and invested > 0 else None,
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

    from apps.calculators.views import holding_key
    from apps.funds.runtime import get_runtime_snapshot
    
    # Pre-fetch snapshots and build holding maps
    holding_maps = []
    for s in schemes:
        snap = get_runtime_snapshot(s)
        hm = {}
        for h in snap.top_holdings:
            k = holding_key(h)
            if k and getattr(h, 'weight_pct', None) is not None:
                hm[k] = float(h.weight_pct)
        holding_maps.append(hm)

    overlap_matrix = []
    if len(schemes) >= 2:
        for i, hm1 in enumerate(holding_maps):
            row = []
            for j, hm2 in enumerate(holding_maps):
                if i == j:
                    row.append(100.0)
                else:
                    common = set(hm1.keys()) & set(hm2.keys())
                    score = sum(min(hm1[n], hm2[n]) for n in common)
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
    
    default_weights, fallbacks = get_default_blended_benchmark_weights(portfolio)
    default_formatted_weights = {k: round(v * 100, 2) for k, v in default_weights.items()}

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
    
    custom_formatted_weights = {k: round(v * 100, 2) for k, v in custom_weights.items()} if custom_weights else None
        
    port_dates, port_invested, port_values = get_portfolio_journey(portfolio)
    port_current = port_values[-1] if port_values else 0
    port_xirr = calculate_portfolio_xirr(portfolio)
    
    def_current, def_xirr, _, def_values = simulate_custom_benchmark(portfolio, default_weights)
    nifty_current, nifty_xirr, _, nifty_values = simulate_custom_benchmark(portfolio, {'NIFTY 50': 1.0})
    
    custom_current, custom_xirr, custom_values = None, None, None
    custom_metrics = {}
    if custom_weights:
        custom_current, custom_xirr, _, custom_values = simulate_custom_benchmark(portfolio, custom_weights)
        custom_metrics = compute_advanced_risk_metrics(port_values, custom_values) if port_values and custom_values else {}
    
    def_metrics = compute_advanced_risk_metrics(port_values, def_values) if port_values and def_values else {}
    nifty_metrics = compute_advanced_risk_metrics(port_values, nifty_values) if port_values and nifty_values else {}
    
    return render(request, 'portfolio/benchmark.html', {
        'portfolio': portfolio,
        'indices': indices,
        'default_weights': default_formatted_weights,
        'custom_weights': custom_formatted_weights,
        'fallbacks': fallbacks,
        'port_current': port_current,
        'port_xirr': port_xirr,
        'def_current': def_current,
        'def_xirr': def_xirr,
        'custom_current': custom_current,
        'custom_xirr': custom_xirr,
        'nifty_current': nifty_current,
        'nifty_xirr': nifty_xirr,
        'def_metrics': def_metrics,
        'custom_metrics': custom_metrics,
        'nifty_metrics': nifty_metrics,
        'journey_dates': json.dumps(port_dates),
        'port_values': json.dumps(port_values),
        'def_values': json.dumps(def_values),
        'custom_values': json.dumps(custom_values) if custom_values else 'null',
        'nifty_values': json.dumps(nifty_values),
    })


@login_required
def portfolio_rebalance_view(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk, user=request.user)
    return render(request, 'portfolio/rebalance.html', {
        'portfolio': portfolio,
    })



def _add_months(d, months):
    """Generate SIP dates by advancing the start date by `months` months at a time."""
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
# ═══════════════════════════════════════════════════════════════════════════════
# BACKTESTER V2 VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

ALL_INDICES = [
        "NASDAQ 100 TRI", "MSCI ACWI TRI", "S&P GLOBAL 1200", "S&P GLOBAL AGRIBUSINESS INDEX",
        "NIFTY 50 TRI", "NIFTY 100 TRI", "NIFTY 200 TRI", "NIFTY 500 TRI",
        "NIFTY TOTAL MARKET TRI", "NIFTY LARGE MIDCAP 250 TRI", "NIFTY MIDCAP SELECT TRI",
        "NIFTY Midcap 50 TRI", "NIFTY MIDCAP 100 TRI", "NIFTY MIDCAP 150 TRI",
        "NIFTY MIDSMALLCAP 400 TRI", "NIFTY Next 50 TRI", "NIFTY SMALLCAP 50 TRI",
        "NIFTY SMALLCAP 100 TRI", "NIFTY SMALLCAP 250 TRI", "NIFTY MICROCAP 250 TRI",
        "Nifty Metal TRI", "Nifty PSU Bank TRI", "NIFTY COMMODITIES TRI", "NIFTY MNC TRI",
        "Nifty Energy TRI", "Nifty Pharma TRI", "Nifty Auto TRI",
        "Nifty India Manufacturing TRI", "NIFTY Healthcare TRI", "NIFTY CPSE Total Return Index",
        "Nifty Infrastructure TRI", "NIFTY PSE TRI", "Nifty Financial Services TRI",
        "NIFTY OIL & GAS TRI", "Nifty Bank TRI", "Nifty Services Sector TRI",
        "Nifty India Consumption TRI", "Nifty FMCG TRI", "Nifty Media TRI",
        "Nifty Realty TRI", "Nifty IT TRI", "BSE Sensex", "BSE 100", "BSE 200",
        "BSE 500", "BSE AllCap", "BSE Mid Cap", "BSE Small Cap", "BSE LargeCap",
        "BSE LargeMidCap", "BSE 250 LargeMidCap Index", "BSE Midcap Select Index",
        "BSE 150 MidCap Index", "BSE Mid Small Cap Index", "BSE 250 SmallCap Index",
        "BSE SENSEX Next 50", "BSE SENSEX 50", "BSE Bharat 22 Index", "BSE PSU",
        "BSE POWER", "BSE Healthcare", "BSE Bankex", "BSE Financial Services",
        "BSE IT", "BSE FMCG", "BSE Teck", "BSE India Infrastructure Index",
        "BSE Enhanced Value Index", "BSE Quality Index", "BSE Low Volatility Index",
    ]

@login_required
def portfolio_backtester_hub_view(request):
    """Render the Backtester hub for authenticated users."""
    return render(request, 'portfolio/backtester_hub.html')


@login_required
def portfolio_backtester_view(request):
    """Render the Backtester v2 builder UI."""
    strategy_id = request.GET.get('strategy', '').strip()
    return render(request, 'portfolio/backtester.html', {
        'all_indices': json.dumps(ALL_INDICES),
        'initial_strategy_id': strategy_id if strategy_id.isdigit() else '',
    })


@json_login_required
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
                        'nav_latest', 'aum_cr', 'is_direct', 'nav_date')
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
                    'inception_date': s['nav_date'].isoformat() if s['nav_date'] else None,
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
                    'inception_date': None,
                })

            # BUG-05/09 FIX: In-memory fallback if DB is sparse
            if not results and len(q) >= 2:
                q_lower = q.lower()
                fallback_matches = [name for name in ALL_INDICES if q_lower in name.lower()]
                for name in fallback_matches[:10]:
                    results.append({
                        'type': 'index',
                        'id': name,
                        'name': name,
                        'sub': 'Index (Fallback)',
                        'nav': None,
                        'aum': None,
                        'is_direct': None,
                        'inception_date': None,
                    })

    return JsonResponse({'results': results})


@json_login_required
def backtester_v2_run_api(request):
    """
    POST /portfolio/backtester/v2/run/
    Runs the v2 simulation. Accepts a JSON body describing the plan.

    Request shape:
    {
      "assets": [
        {
          "label": "Parag Parikh Flexi Cap",
          "source_type": "scheme",
          "source_id": "122639",
          "rules": [
            {
              "rule_type": "sip",
              "amount": 5000,
              "frequency": "monthly",
              "start_date": "2019-01-01",
              "end_date": null,
              "step_up": {"step_type": "pct", "step_amount": 10, "step_frequency": "annual"},
              "trigger": null
            },
            {
              "rule_type": "lumpsum",
              "amount": 50000,
              "lumpsum_date": "2020-03-23",
              "trigger": {
                "conditions": [{"signal_type": "drawdown_ath", "params": {"reference_id": "122639"}, "operator": "gte", "value": 10}],
                "logic": "AND",
                "action_mode": "once"
              }
            }
          ]
        }
      ],
      "settings": {
        "start_date": "2019-01-01",
        "end_date": null,
        "benchmark_type": "index",
        "benchmark_id": "NIFTY 50 TRI",
        "synthetic_debt_rate": 7.0,
        "transaction_cost": 0,
        "tax_enabled": false,
        "inflation_enabled": false,
        "inflation_mode": "manual",
        "inflation_rate": 5.0
      }
    }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from apps.portfolio.services.backtester_v2 import (
            PortfolioPlanV2, AssetV2, RuleV2, StepUpConfig,
            TriggerConfig, TriggerCondition, SimSettingsV2,
            RebalanceRule, ExitLoadSchedule, run_backtest_v2,
        )

        def _pd(s):
            if not s:
                return None
            try:
                return date.fromisoformat(str(s))
            except ValueError:
                return None

        def _parse_step_up(raw):
            if not raw:
                return None
            return StepUpConfig(
                step_type=str(raw.get('step_type', 'pct')),
                step_amount=float(raw.get('step_amount', 0)),
                step_frequency=str(raw.get('step_frequency', 'annual')),
            )

        def _parse_trigger_condition(raw):
            return TriggerCondition(
                signal_type=str(raw.get('signal_type', '')),
                params=raw.get('params', {}),
                operator=str(raw.get('operator', 'lt')),
                value=float(raw.get('value', 0)),
            )

        def _parse_trigger(raw):
            if not raw:
                return None
            conds = [_parse_trigger_condition(c) for c in raw.get('conditions', [])]
            if not conds:
                return None
            return TriggerConfig(
                conditions=conds,
                logic=str(raw.get('logic', 'AND')),
                action_mode=str(raw.get('action_mode', 'every_period')),
                amount_modifier=raw.get('amount_modifier'),
            )

        def _parse_exit_load(raw):
            if not raw:
                return None
            tiers_raw = raw.get('tiers', [])
            tiers = [(int(t[0]), float(t[1])) for t in tiers_raw if len(t) == 2]
            return ExitLoadSchedule(tiers=tiers)

        def _parse_rule(raw):
            return RuleV2(
                rule_type=str(raw.get('rule_type', 'sip')),
                amount=float(raw.get('amount', 0)),
                frequency=str(raw.get('frequency', 'monthly')),
                start_date=_pd(raw.get('start_date')),
                end_date=_pd(raw.get('end_date')),
                step_up=_parse_step_up(raw.get('step_up')),
                lumpsum_date=_pd(raw.get('lumpsum_date') or raw.get('sell_date') or raw.get('switch_date')),
                amount_type=str(raw.get('amount_type', 'amount')),
                switch_from_id=str(raw['switch_from_id']) if raw.get('switch_from_id') else None,
                switch_to_id=str(raw['switch_to_id']) if raw.get('switch_to_id') else None,
                switch_date=_pd(raw.get('switch_date')),
                trigger=_parse_trigger(raw.get('trigger')),
            )

        def _parse_rebalance(raw):
            if not raw:
                return None
            return RebalanceRule(
                target_weights={str(k): float(v) for k, v in raw.get('target_weights', {}).items()},
                mode=str(raw.get('mode', 'frequency')),
                frequency=str(raw.get('frequency', 'annually')),
                anchor_month=int(raw.get('anchor_month', 1)),
                drift_threshold=float(raw.get('drift_threshold', 5.0)),
                drift_type=str(raw.get('drift_type', 'absolute')),
            )

        raw_assets = data.get('assets', [])
        if not raw_assets:
            return JsonResponse({'error': 'Add at least one asset to your plan.'}, status=400)

        assets = []
        for ra in raw_assets:
            rules = [_parse_rule(r) for r in ra.get('rules', [])]
            assets.append(AssetV2(
                label=str(ra.get('label', ra.get('source_id', 'Asset'))),
                source_type=str(ra.get('source_type', 'scheme')),
                source_id=str(ra.get('source_id', '')),
                rules=rules,
                exit_load=_parse_exit_load(ra.get('exit_load')),
            ))

        if not assets:
            return JsonResponse({'error': 'No valid assets found.'}, status=400)

        raw_settings = data.get('settings', {})
        settings = SimSettingsV2(
            start_date=_pd(raw_settings.get('start_date')),
            end_date=_pd(raw_settings.get('end_date')),
            benchmark_type=str(raw_settings.get('benchmark_type', 'index')),
            benchmark_id=str(raw_settings.get('benchmark_id', '')),
            synthetic_debt_rate=float(raw_settings.get('synthetic_debt_rate', 7.0)),
            transaction_cost=float(raw_settings.get('transaction_cost', 0)),
            exit_load_enabled=bool(raw_settings.get('exit_load_enabled', False)),
            # Tax (Phase 4)
            tax_enabled=bool(raw_settings.get('tax_enabled', False)),
            tax_equity_stcg=float(raw_settings.get('tax_equity_stcg', 20.0)),
            tax_equity_ltcg=float(raw_settings.get('tax_equity_ltcg', 12.5)),
            tax_ltcg_exemption=float(raw_settings.get('tax_ltcg_exemption', 125000.0)),
            tax_debt_rate=float(raw_settings.get('tax_debt_rate', 30.0)),
            # Inflation (Phase 4)
            inflation_enabled=bool(raw_settings.get('inflation_enabled', False)),
            inflation_mode=str(raw_settings.get('inflation_mode', 'manual')),
            inflation_rate=float(raw_settings.get('inflation_rate', 5.0)),
            # Monte Carlo (Phase 5)
            mc_enabled=bool(raw_settings.get('mc_enabled', False)),
            mc_simulations=int(raw_settings.get('mc_simulations', 500)),
            mc_horizon_years=int(raw_settings.get('mc_horizon_years', 10)),
        )

        rebalance = _parse_rebalance(data.get('rebalance'))
        plan = PortfolioPlanV2(assets=assets, settings=settings, rebalance=rebalance)
        result = run_backtest_v2(plan)

        def _pa_dict(pa):
            return {
                'label': pa.label,
                'source_id': pa.source_id,
                'total_invested': pa.total_invested,
                'total_redeemed': pa.total_redeemed,
                'current_value': pa.current_value,
                'xirr': pa.xirr,
                'contribution_pct': pa.contribution_pct,
            }

        return JsonResponse({
            'status': 'success',
            # Tab 1
            'total_invested': result.total_invested,
            'total_redeemed': result.total_redeemed,
            'final_value': result.final_value,
            'absolute_gain': result.absolute_gain,
            'xirr': result.xirr,
            'cagr': result.cagr,
            'benchmark_cagr': result.benchmark_cagr,
            'per_asset': [_pa_dict(pa) for pa in result.per_asset],
            # Tab 2 — Risk
            'max_drawdown': result.max_drawdown,
            'max_dd_start': result.max_dd_start,
            'max_dd_trough': result.max_dd_trough,
            'max_dd_recovery': result.max_dd_recovery,
            'max_dd_days': result.max_dd_days,
            'recovery_days': result.recovery_days,
            'volatility': result.volatility,
            'downside_deviation': result.downside_deviation,
            'worst_month': result.worst_month,
            'worst_quarter': result.worst_quarter,
            'var_95': result.var_95,
            'cvar_95': result.cvar_95,
            'sharpe': result.sharpe,
            'sortino': result.sortino,
            'calmar': result.calmar,
            'romad': result.romad,
            # Tab 3 — Charts
            'dates': result.dates,
            'portfolio_values': result.portfolio_values,
            'invested_cumulative': result.invested_cumulative,
            'benchmark_values': result.benchmark_values,
            'drawdown_series': result.drawdown_series,
            'daily_returns': result.daily_returns,
            'calendar_returns': result.calendar_returns,
            'monthly_returns': result.monthly_returns,
            'event_markers': result.event_markers,
            # Tab 3 — Rolling returns (box plots)
            'rolling_1y': result.rolling_1y,
            'rolling_3y': result.rolling_3y,
            'rolling_5y': result.rolling_5y,
            'rolling_7y': result.rolling_7y,
            # Tab 3 extra — PE overlay (Phase 3)
            'pe_chart_series': result.pe_chart_series,
            'pe_index_name': result.pe_index_name,
            # Tab 4 — Attribution
            'rule_attribution': result.rule_attribution,
            # Tab 5 — Adjusted Returns (Phase 4)
            'tax_enabled': result.tax_enabled,
            'stcg_paid': result.stcg_paid,
            'ltcg_paid': result.ltcg_paid,
            'tax_drag': result.tax_drag,
            'post_tax_xirr': result.post_tax_xirr,
            'inflation_enabled': result.inflation_enabled,
            'inflation_rate_used': result.inflation_rate_used,
            'real_xirr': result.real_xirr,
            'real_final_value': result.real_final_value,
            # Tab 6 — Ledger
            'transactions': result.transactions,
            # Tab 7 — Monte Carlo (Phase 5)
            'mc_enabled': result.mc_enabled,
            'mc_dates': result.mc_dates,
            'mc_p10': result.mc_p10,
            'mc_p25': result.mc_p25,
            'mc_p50': result.mc_p50,
            'mc_p75': result.mc_p75,
            'mc_p90': result.mc_p90,
            'mc_final_p10': result.mc_final_p10,
            'mc_final_p50': result.mc_final_p50,
            'mc_final_p90': result.mc_final_p90,
            'mc_prob_double': result.mc_prob_double,
            'mc_prob_loss': result.mc_prob_loss,
            'mc_simulations_run': result.mc_simulations_run,
            # Meta
            'start_date': result.start_date,
            'end_date': result.end_date,
            'data_warnings': result.data_warnings,
            'plan_summary': result.plan_summary,
        })

    except Exception as exc:
        logger.exception('Backtester v2 API error')
        return JsonResponse({'error': str(exc)}, status=400)


@json_login_required
def backtester_pe_api(request):
    """
    GET /portfolio/backtester/pe-data/?index=NIFTY+50&from=2015-01-01&to=2024-12-31
    Returns PE ratio series for a NSE index.
    """
    index_name = request.GET.get('index', 'NIFTY 50').strip()
    from_str = request.GET.get('from', '')
    to_str = request.GET.get('to', '')

    try:
        from_date = date.fromisoformat(from_str) if from_str else date(2010, 1, 1)
        to_date = date.fromisoformat(to_str) if to_str else date.today()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

    try:
        from apps.portfolio.services.pe_adapter import get_pe_series, PEDataUnavailableError
        series = get_pe_series(index_name, from_date, to_date)
        data_out = [
            {'date': str(ts.date()), 'pe': round(float(v), 2)}
            for ts, v in series.items()
            if not pd.isna(v)
        ]
        return JsonResponse({'status': 'ok', 'index': index_name, 'data': data_out})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ══════════════════════════════════════════════════════════════════════════════
# STRATEGY SAVE / LOAD (Phase 6 — Issue 14)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def strategies_page(request):
    """Render the saved strategies library page."""
    strategies = request.user.saved_strategies.all().order_by('-updated_at')
    return render(request, 'portfolio/strategies.html', {'strategies': strategies})


@login_required
def strategy_compare_page(request):
    """Render side-by-side comparison for selected saved strategies."""
    ids_raw = request.GET.get('ids', '')
    selected_ids = [int(s) for s in ids_raw.split(',') if s.strip().isdigit()][:4]
    strategies = SavedStrategy.objects.filter(user=request.user, id__in=selected_ids)
    by_id = {s.id: s for s in strategies}
    ordered = [by_id[sid] for sid in selected_ids if sid in by_id]
    return render(request, 'portfolio/strategy_compare.html', {
        'strategies': ordered,
        'strategy_ids': ','.join(str(s.id) for s in ordered),
    })


@json_login_required
def strategy_list_api(request):
    """
    GET  /portfolio/strategies/api/         → list user's saved strategies
    POST /portfolio/strategies/api/         → save a new strategy (or update by name)
    """
    from apps.portfolio.models import SavedStrategy

    if request.method == 'GET':
        strategies = SavedStrategy.objects.filter(user=request.user).order_by('-updated_at')
        return JsonResponse({'strategies': [
            {
                'id': str(s.id),
                'name': s.name,
                'description': s.description,
                'updated_at': s.updated_at.isoformat(),
                'plan_json': s.plan_json,
                # Don't send full result JSON in list view (too large)
                'has_result': s.last_result_json is not None,
            }
            for s in strategies
        ]})

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        name = (body.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Strategy name is required.'}, status=400)

        description = (body.get('description') or '').strip()
        plan_json = body.get('plan_json')
        if not plan_json:
            return JsonResponse({'error': 'plan_json is required.'}, status=400)

        last_result_json = body.get('last_result_json')  # optional

        # Upsert by (user, name) to avoid accidental duplicates
        strategy, created = SavedStrategy.objects.update_or_create(
            user=request.user,
            name=name,
            defaults={
                'description': description,
                'plan_json': plan_json,
                'last_result_json': last_result_json,
            },
        )
        return JsonResponse({
            'status': 'created' if created else 'updated',
            'id': str(strategy.id),
            'name': strategy.name,
        })

    return JsonResponse({'error': 'Method not allowed.'}, status=405)


@json_login_required
def strategy_detail_api(request, strategy_id: int):
    """
    DELETE /portfolio/strategies/api/<id>/   → delete strategy
    PATCH  /portfolio/strategies/api/<id>/   → update last_result_json after a run
    """
    from apps.portfolio.models import SavedStrategy

    try:
        strategy = SavedStrategy.objects.get(id=strategy_id, user=request.user)
    except SavedStrategy.DoesNotExist:
        return JsonResponse({'error': 'Strategy not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'id': str(strategy.id),
            'name': strategy.name,
            'description': strategy.description,
            'updated_at': strategy.updated_at.isoformat(),
            'plan_json': strategy.plan_json,
            'last_result_json': strategy.last_result_json,
            'has_result': strategy.last_result_json is not None,
        })

    if request.method == 'DELETE':
        strategy.delete()
        return JsonResponse({'status': 'deleted'})

    if request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)
        if 'last_result_json' in body:
            strategy.last_result_json = body['last_result_json']
            strategy.save(update_fields=['last_result_json', 'updated_at'])
        return JsonResponse({'status': 'updated', 'id': str(strategy.id)})

    return JsonResponse({'error': 'Method not allowed.'}, status=405)
