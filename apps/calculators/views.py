"""apps/calculators/views.py — All 10 calculators"""
import json
import logging
import re
from datetime import date

import numpy as np
import pandas as pd
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger('mfanalysis')

RF_ANNUAL = 0.065


def hub_view(request):
    return render(request, 'calculators/hub.html')


def rolling_view(request):
    return render(request, 'calculators/rolling.html')


def sip_view(request):
    return render(request, 'calculators/sip.html')


def lumpsum_view(request):
    return render(request, 'calculators/lumpsum.html')


def xirr_view(request):
    return render(request, 'calculators/xirr.html')


def swp_view(request):
    return render(request, 'calculators/swp.html')


def goal_view(request):
    return render(request, 'calculators/goal.html')


def tax_view(request):
    return render(request, 'calculators/tax.html')


def overlap_view(request):
    return render(request, 'calculators/overlap.html')


def step_sip_view(request):
    return render(request, 'calculators/step_sip.html')


def stp_view(request):
    return render(request, 'calculators/stp.html')


def compare_view(request):
    """
    Side-by-side fund comparison view.
    Accepts ?funds=120503,118285 (up to 4 funds).
    """
    from apps.funds.runtime import get_runtime_snapshot
    from apps.funds.services import get_or_fetch_scheme
    
    funds_param = request.GET.get('funds', '')
    amfi_codes = [c.strip() for c in funds_param.split(',') if c.strip()][:4]
    
    compare_data = []
    
    for code in amfi_codes:
        scheme = get_or_fetch_scheme(code)
        if not scheme:
            continue
            
        snap = get_runtime_snapshot(scheme)
        
        # Calculate some PE ratio if holding data has forward_pe
        pe_ratios = [h.forward_pe for h in snap.top_holdings if getattr(h, 'forward_pe', None)]
        avg_pe = sum(pe_ratios)/len(pe_ratios) if pe_ratios else None
        
        fund_data = {
            'amfi_code': scheme.amfi_code,
            'scheme_name': scheme.scheme_name,
            'fund_house': scheme.fund_house,
            'category': getattr(snap, 'category', None),
            'aum': getattr(snap.meta, 'aum', None),
            'expense_ratio': getattr(snap.meta, 'expense_ratio', None),
            'exit_load': 'See KIM', # Not explicitly in meta model easily available
            'lock_in_period': getattr(snap.meta, 'lock_in_period', None),
            'tax_period': getattr(snap.meta, 'tax_period', None),
            'min_lumpsum': getattr(snap.meta, 'lump_min', None),
            'min_sip': getattr(snap.meta, 'sip_min', None),
            'inception_date': getattr(snap.meta, 'start_date', None),
            'objective': getattr(snap.meta, 'investment_objective', None),
            'crisil_rating': getattr(snap.meta, 'crisil_rating', None),
            'ms_rating': getattr(snap.meta, 'ms_rating', None),
            'pe_ratio': avg_pe,
            'trailing': {r.period: r.cagr_pct for r in snap.trailing_returns} if snap.trailing_returns else {},
            'rolling': snap.rolling_returns.get('3Y') if snap.rolling_returns else None,
            'risk': snap.risk_3y, # Default to 3Y risk metrics
        }
        compare_data.append(fund_data)
        
    return render(request, 'calculators/compare.html', {'compare_data': compare_data, 'amfi_codes_str': ','.join(amfi_codes)})


# ── Calculator API Endpoints ──────────────────────────────────

def _parse_body(request):
    try:
        return json.loads(request.body)
    except Exception:
        return request.POST.dict()


@require_http_methods(["POST"])
def calc_sip_api(request):
    """SIP Calculator: monthly_amount, years, expected_rate (%) → results + year-by-year history."""
    d = _parse_body(request)
    try:
        monthly = float(d.get('monthly_amount', 10000))
        years = float(d.get('years', 10))
        annual_rate = float(d.get('expected_rate', 12))
        rate = annual_rate / 100 / 12  # monthly rate
        n = int(years * 12)

        # Build year-by-year history for the growth chart
        history = []
        total_value = 0
        total_invested_running = 0
        for yr in range(1, int(years) + 1):
            for _ in range(12):
                total_invested_running += monthly
                if rate == 0:
                    total_value += monthly
                else:
                    total_value = (total_value + monthly) * (1 + rate)
            gain_yr = total_value - total_invested_running
            history.append({
                'year': yr,
                'invested': round(total_invested_running, 2),
                'value': round(total_value, 2),
                'gain': round(gain_yr, 2),
            })

        invested = monthly * n
        future_value = total_value
        gain = future_value - invested
        cagr = ((future_value / invested) ** (1 / years) - 1) * 100 if invested > 0 and years > 0 else 0
        return JsonResponse({
            'total_invested': round(invested, 2),
            'future_value': round(future_value, 2),
            'gain': round(gain, 2),
            'return_pct': round((gain / invested) * 100, 2) if invested else 0,
            'cagr': round(cagr, 2),
            'monthly_amount': monthly,
            'years': years,
            'n_instalments': n,
            'history': history,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_lumpsum_api(request):
    d = _parse_body(request)
    try:
        principal = float(d.get('principal', 100000))
        years = float(d.get('years', 10))
        rate = float(d.get('expected_rate', 12)) / 100
        # Year-by-year history
        history = []
        for yr in range(1, int(years) + 1):
            val = principal * ((1 + rate) ** yr)
            history.append({
                'year': yr,
                'invested': round(principal, 2),
                'value': round(val, 2),
                'gain': round(val - principal, 2),
            })
        future_value = principal * ((1 + rate) ** years)
        gain = future_value - principal
        return JsonResponse({
            'principal': principal,
            'future_value': round(future_value, 2),
            'gain': round(gain, 2),
            'return_pct': round((gain / principal) * 100, 2),
            'cagr': round(rate * 100, 2),
            'years': years,
            'history': history,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_swp_api(request):
    """SWP: corpus, monthly_withdrawal, expected_rate → months until exhausted + full monthly history."""
    d = _parse_body(request)
    try:
        corpus = float(d.get('corpus', 1000000))
        withdrawal = float(d.get('monthly_withdrawal', 10000))
        rate = float(d.get('expected_rate', 8)) / 100 / 12
        balance = corpus
        months = 0
        history = []
        total_interest_earned = 0

        # Record initial state
        history.append({'month': 0, 'balance': round(corpus, 2), 'withdrawn_cumulative': 0, 'interest_cumulative': 0})

        while balance > 0 and months < 600:
            interest = balance * rate
            total_interest_earned += interest
            balance = balance + interest - withdrawal
            months += 1
            # Record every month for smooth charts (cap at 600 points)
            history.append({
                'month': months,
                'balance': max(0, round(balance, 2)),
                'withdrawn_cumulative': round(withdrawal * months, 2),
                'interest_cumulative': round(total_interest_earned, 2),
            })
            if balance <= 0:
                break

        total_withdrawn = withdrawal * months
        remaining = max(0, balance)
        gain_from_corpus = total_withdrawn + remaining - corpus

        return JsonResponse({
            'months_sustained': months,
            'years_sustained': round(months / 12, 1),
            'total_withdrawn': round(total_withdrawn, 2),
            'corpus': corpus,
            'monthly_withdrawal': withdrawal,
            'remaining_corpus': round(remaining, 2),
            'total_interest_earned': round(total_interest_earned, 2),
            'gain_from_corpus': round(gain_from_corpus, 2),
            'history': history,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_goal_api(request):
    """Goal Planner: target_amount, years, expected_rate → required monthly SIP."""
    d = _parse_body(request)
    try:
        target = float(d.get('target_amount', 5000000))
        years = float(d.get('years', 15))
        rate = float(d.get('expected_rate', 12)) / 100 / 12
        n = int(years * 12)
        inflation = float(d.get('inflation', 6)) / 100
        # Inflation-adjusted target
        real_target = target * ((1 + inflation) ** years)
        if rate == 0:
            monthly_sip = real_target / n
        else:
            monthly_sip = real_target * rate / (((1 + rate) ** n - 1) * (1 + rate))
        lumpsum_needed = real_target / ((1 + rate * 12) ** years)
        return JsonResponse({
            'target_amount': target,
            'inflation_adjusted_target': round(real_target, 2),
            'monthly_sip_required': round(monthly_sip, 2),
            'lumpsum_now': round(lumpsum_needed, 2),
            'years': years,
            'n_instalments': n,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_tax_api(request):
    """Tax Calculator: investment_amount, current_value, holding_days, fund_type."""
    d = _parse_body(request)
    try:
        invested = float(d.get('invested', 100000))
        current = float(d.get('current_value', 150000))
        holding_days = int(d.get('holding_days', 400))
        fund_type = d.get('fund_type', 'equity').lower()
        gain = current - invested

        if fund_type == 'equity':
            is_ltcg = holding_days >= 365
            if is_ltcg:
                exempt = 125000  # ₹1.25L exempt
                taxable_gain = max(0, gain - exempt)
                tax = taxable_gain * 0.125  # 12.5% LTCG
                tax_type = 'LTCG (12.5% above ₹1.25L)'
            else:
                taxable_gain = gain
                tax = gain * 0.20  # 20% STCG
                tax_type = 'STCG (20%)'
        else:
            # Debt/Hybrid: slab rate
            taxable_gain = gain
            tax = gain * 0.30  # Assume highest slab
            tax_type = 'Debt — Added to income (highest slab 30%)'
            is_ltcg = holding_days >= 365

        return JsonResponse({
            'invested': invested,
            'current_value': current,
            'gain': round(gain, 2),
            'taxable_gain': round(taxable_gain, 2),
            'estimated_tax': round(tax, 2),
            'post_tax_gain': round(gain - tax, 2),
            'post_tax_value': round(current - tax, 2),
            'tax_type': tax_type,
            'holding_years': round(holding_days / 365, 1),
            'is_ltcg': is_ltcg,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def holding_key(holding) -> str:
    isin = str(getattr(holding, 'isin', '') or '').strip().upper()
    if isin and isin not in ('-', 'NA', '0', 'NONE', 'N/A', 'NULL'):
        return f'isin:{isin}'
    name = normalise_holding_name(getattr(holding, 'security_name', '') or '')
    if not name:
        return ''
    return 'name:' + name


def normalise_holding_name(value) -> str:
    name = str(value or '').strip().lower()
    if not name:
        return ''
    name = name.replace('&', ' and ')
    name = re.sub(r'[^a-z0-9]+', ' ', name)
    suffixes = {
        'ltd', 'limited', 'equity', 'equities', 'share', 'shares', 'ordinary',
        'ord', 'class', 'company', 'co', 'private', 'pvt', 'inc', 'plc',
    }
    tokens = [token for token in name.split() if token not in suffixes]
    return ' '.join(tokens)


@require_http_methods(["POST"])
def calc_overlap_api(request):
    """Fund Overlap: two AMFI codes -> weighted shared holdings."""
    d = _parse_body(request)
    from apps.funds.models import Scheme
    try:
        raw_codes = d.get('funds') or [d.get('fund1'), d.get('fund2')]
        codes = list(dict.fromkeys(str(code).strip() for code in raw_codes if str(code or '').strip()))
        if len(codes) != 2:
            return JsonResponse({'error': 'Select exactly two funds to compare overlap.'}, status=400)

        from apps.funds.runtime import get_runtime_snapshot
        from apps.funds.services import get_or_fetch_scheme

        fund_rows = []
        holding_maps = []
        for code in codes:
            scheme = get_or_fetch_scheme(code)
            if not scheme:
                return JsonResponse({'error': f'AMFI code {code} was not found.'}, status=404)
            snap = get_runtime_snapshot(scheme)
            holdings = {
                holding_key(h): h
                for h in snap.top_holdings
                if holding_key(h) and h.weight_pct is not None
            }
            if not holdings:
                return JsonResponse({'error': f'Holdings data is not available for {scheme.scheme_name} from the on-demand providers.'})
            fund_rows.append({
                'code': scheme.amfi_code,
                'name': scheme.scheme_name,
                'short_name': scheme.scheme_name[:55],
                'total_holdings': len(holdings),
                'source': snap.sources.portfolio,
            })
            holding_maps.append(holdings)

        pairs = []
        for i in range(len(holding_maps)):
            for j in range(i + 1, len(holding_maps)):
                common = set(holding_maps[i]) & set(holding_maps[j])
                overlap_score = sum(
                    min(float(holding_maps[i][key].weight_pct), float(holding_maps[j][key].weight_pct))
                    for key in common
                )
                pairs.append({
                    'i': i,
                    'j': j,
                    'fund1_code': fund_rows[i]['code'],
                    'fund2_code': fund_rows[j]['code'],
                    'fund1_name': fund_rows[i]['name'],
                    'fund2_name': fund_rows[j]['name'],
                    'common_holdings': len(common),
                    'overlap_score': round(overlap_score, 2),
                })

        all_keys = set().union(*(set(hmap) for hmap in holding_maps))
        overlap = []
        for key in all_keys:
            weights = []
            names = []
            present_count = 0
            for hmap in holding_maps:
                holding = hmap.get(key)
                if holding:
                    present_count += 1
                    names.append(holding.security_name)
                    weights.append(round(float(holding.weight_pct), 2))
                else:
                    weights.append(None)
            if present_count >= 2:
                overlap.append({
                    'security_name': names[0],
                    'weights': weights,
                    'present_count': present_count,
                    'shared_weight': round(sum(w for w in weights if w is not None), 2),
                })
        overlap.sort(key=lambda row: (-row['present_count'], -row['shared_weight'], row['security_name']))

        return JsonResponse({
            'funds': fund_rows,
            'pairs': pairs,
            'all_common_holdings': len([row for row in overlap if row['present_count'] == len(fund_rows)]),
            'overlap': overlap,
        })
    except Scheme.DoesNotExist:
        return JsonResponse({'error': 'One or more AMFI codes were not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_step_sip_api(request):
    """Step-up SIP: start amount, annual step-up %, years, rate → future value."""
    d = _parse_body(request)
    try:
        start_amount = float(d.get('start_amount', 5000))
        step_up_pct = float(d.get('step_up_pct', 10)) / 100  # annual step-up
        years = int(d.get('years', 10))
        rate = float(d.get('expected_rate', 12)) / 100 / 12
        history = []
        total_invested = 0
        total_value = 0
        monthly_sip = start_amount
        for yr in range(years):
            for mo in range(12):
                total_value = (total_value + monthly_sip) * (1 + rate)
                total_invested += monthly_sip
            history.append({
                'year': yr + 1, 'monthly_sip': round(monthly_sip, 2),
                'invested_to_date': round(total_invested, 2), 'value_to_date': round(total_value, 2),
            })
            monthly_sip *= (1 + step_up_pct)
        return JsonResponse({
            'total_invested': round(total_invested, 2),
            'future_value': round(total_value, 2),
            'gain': round(total_value - total_invested, 2),
            'history': history,
            'final_monthly_sip': round(monthly_sip / (1 + step_up_pct), 2),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_stp_api(request):
    """Generic STP Calculator: corpus, transfer_amount, rates → history of source/target values."""
    d = _parse_body(request)
    try:
        corpus = float(d.get('corpus', 1000000))
        transfer = float(d.get('transfer_amount', 10000))
        rate_source = float(d.get('expected_rate_source', 6)) / 100 / 12
        rate_target = float(d.get('expected_rate_target', 12)) / 100 / 12
        
        balance_source = corpus
        balance_target = 0.0
        months = 0
        history = []
        total_transferred = 0.0

        history.append({
            'month': 0,
            'source_balance': round(corpus, 2),
            'target_balance': 0.0,
            'transferred_cumulative': 0.0,
            'combined_value': round(corpus, 2)
        })

        while balance_source > 0 and months < 600:
            # Grow source by 1 month
            balance_source += balance_source * rate_source
            
            # Determine actual transfer amount (can't transfer more than balance)
            actual_transfer = min(transfer, balance_source)
            balance_source -= actual_transfer
            
            # Target receives transfer, then grows? Or grows then receives?
            # Standard: Target grows, then receives new transfer
            balance_target += balance_target * rate_target
            balance_target += actual_transfer
            
            total_transferred += actual_transfer
            months += 1
            
            history.append({
                'month': months,
                'source_balance': round(balance_source, 2),
                'target_balance': round(balance_target, 2),
                'transferred_cumulative': round(total_transferred, 2),
                'combined_value': round(balance_source + balance_target, 2)
            })

            if balance_source <= 0.01:
                break

        return JsonResponse({
            'months_sustained': months,
            'years_sustained': round(months / 12, 1),
            'total_transferred': round(total_transferred, 2),
            'corpus': corpus,
            'transfer_amount': transfer,
            'source_remaining': round(balance_source, 2),
            'target_accumulated': round(balance_target, 2),
            'combined_value': round(balance_source + balance_target, 2),
            'total_profit': round((balance_source + balance_target) - corpus, 2),
            'history': history,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_xirr_api(request):
    """XIRR: cashflows[] + dates[] → annualised IRR."""
    d = _parse_body(request)
    try:
        from apps.analytics.engine import _compute_xirr
        from datetime import datetime
        cashflows = [float(x) for x in d.get('cashflows', [])]
        raw_dates = d.get('dates', [])
        dates = [datetime.strptime(dt, '%Y-%m-%d') for dt in raw_dates]
        if len(cashflows) < 2 or len(cashflows) != len(dates):
            return JsonResponse({'error': 'Need at least 2 matching cashflows and dates.'}, status=400)
        xirr = _compute_xirr(cashflows, dates)
        if xirr is None:
            return JsonResponse({'error': 'Could not converge on XIRR. Check cashflows include both negative (invest) and positive (redeem) values.'})
        return JsonResponse({'xirr_pct': round(xirr * 100, 4)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ── NAV-based Historical Calculator Endpoints ─────────────────────────────────
# These use *actual* daily NAV data to simulate real investments and compute
# accurate XIRR / cash-flow tables.

def _get_nav_series(amfi_code: str):
    """Return (nav_series, inception_date_str, latest_nav, latest_date) for a fund."""
    from apps.funds.runtime import fetch_nav_and_meta, nav_rows_to_series
    nav_rows, meta = fetch_nav_and_meta(amfi_code)
    if not nav_rows:
        return None, None, None, None
    series = nav_rows_to_series(nav_rows)
    if series.empty:
        return None, None, None, None
    inception = series.index[0].date().isoformat()
    latest_nav = float(series.iloc[-1])
    latest_date = series.index[-1].date().isoformat()
    return series, inception, latest_nav, latest_date


def _sip_dates_in_range(start: pd.Timestamp, end: pd.Timestamp, frequency: str, day: int = 1) -> list:
    """Generate SIP/STP instalment dates within [start, end].
    If `day` is provided, sets the instalment to that day of the month.
    Handles month-end boundaries (e.g. Feb 30 -> Feb 28)."""
    import calendar
    dates = []
    months_step = 3 if frequency == 'quarterly' else 1
    
    # Set to the requested day, clamped to the valid days of the current month
    max_day = calendar.monthrange(start.year, start.month)[1]
    safe_day = min(day, max_day)
    current = start.replace(day=safe_day)
    
    # If the adjusted start is before the actual start, bump to the next period
    if current < start:
        month = current.month + months_step
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        max_day = calendar.monthrange(year, month)[1]
        safe_day = min(day, max_day)
        current = current.replace(year=year, month=month, day=safe_day)

    while current <= end:
        dates.append(current)
        month = current.month + months_step
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        max_day = calendar.monthrange(year, month)[1]
        safe_day = min(day, max_day)
        current = current.replace(year=year, month=month, day=safe_day)
    return dates


def _compute_xirr_safe(cashflows, dates):
    """Compute XIRR; return None on failure."""
    try:
        from apps.analytics.engine import _compute_xirr
        xirr = _compute_xirr(cashflows, dates)
        return round(xirr * 100, 2) if xirr is not None else None
    except Exception:
        return None


@require_http_methods(["POST"])
def calc_nav_sip_api(request):
    """Historical SIP: buy units at actual NAV on each instalment date."""
    d = _parse_body(request)
    try:
        amfi_code   = str(d.get('amfi_code', '')).strip()
        start_str   = d.get('start_date', '')
        end_str     = d.get('end_date', '')
        amount      = float(d.get('amount', 1000))
        frequency   = d.get('frequency', 'monthly').lower()
        step_up_pct = float(d.get('step_up_pct', 0)) / 100

        if not amfi_code:
            return JsonResponse({'error': 'amfi_code is required.'}, status=400)

        nav_series, inception, latest_nav, latest_date = _get_nav_series(amfi_code)
        if nav_series is None:
            return JsonResponse({'error': 'NAV data not available for this fund.'}, status=404)

        start_ts = pd.Timestamp(start_str) if start_str else nav_series.index[0]
        end_ts   = pd.Timestamp(end_str)   if end_str   else nav_series.index[-1]

        if start_ts < nav_series.index[0]:
            start_ts = nav_series.index[0]
        if end_ts > nav_series.index[-1]:
            end_ts = nav_series.index[-1]

        instalment_dates = _sip_dates_in_range(start_ts, end_ts, frequency)
        if not instalment_dates:
            return JsonResponse({'error': 'No valid instalment dates in the selected range.'}, status=400)

        cashflows = []
        cf_dates  = []
        cashflow_table    = []
        cumulative_units  = 0.0
        cumulative_invested = 0.0
        current_amount    = amount
        last_step_year    = start_ts.year

        for i, sip_date in enumerate(instalment_dates):
            if step_up_pct > 0 and i > 0 and sip_date.year > last_step_year:
                current_amount *= (1 + step_up_pct)
                last_step_year  = sip_date.year

            nav_val = nav_series.asof(sip_date)
            if pd.isna(nav_val) or nav_val <= 0:
                continue

            units_bought = current_amount / float(nav_val)
            cumulative_units    += units_bought
            cumulative_invested += current_amount
            market_value = cumulative_units * float(nav_val)

            cashflows.append(-current_amount)
            cf_dates.append(sip_date.to_pydatetime())

            cashflow_table.append({
                'nav_date':            sip_date.date().isoformat(),
                'nav':                 round(float(nav_val), 4),
                'units_bought':        round(units_bought, 4),
                'cumulative_units':    round(cumulative_units, 4),
                'cumulative_invested': round(cumulative_invested, 2),
                'market_value':        round(market_value, 2),
                'sip_amount':          round(current_amount, 2),
            })

        if not cashflow_table:
            return JsonResponse({'error': 'Could not match any NAV data for the selected dates.'}, status=400)

        final_nav     = float(nav_series.asof(end_ts))
        current_value = cumulative_units * final_nav
        cashflows.append(current_value)
        cf_dates.append(end_ts.to_pydatetime())

        absolute_gain       = current_value - cumulative_invested
        absolute_return_pct = (absolute_gain / cumulative_invested * 100) if cumulative_invested > 0 else 0
        xirr_pct = _compute_xirr_safe(cashflows, cf_dates)

        from apps.funds.services import get_or_fetch_scheme
        scheme = get_or_fetch_scheme(amfi_code)

        return JsonResponse({
            'scheme_name':         scheme.scheme_name if scheme else amfi_code,
            'fund_house':          scheme.fund_house  if scheme else '',
            'amfi_code':           amfi_code,
            'inception_date':      inception,
            'nav_date':            latest_date,
            'nav':                 round(latest_nav, 4),
            'current_value':       round(current_value, 2),
            'total_invested':      round(cumulative_invested, 2),
            'absolute_gain':       round(absolute_gain, 2),
            'absolute_return_pct': round(absolute_return_pct, 2),
            'xirr_pct':            xirr_pct,
            'total_units':         round(cumulative_units, 4),
            'sip_instalments':     len(cashflow_table),
            'start_date':          start_ts.date().isoformat(),
            'end_date':            end_ts.date().isoformat(),
            'cashflow_table':      cashflow_table,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_nav_swp_api(request):
    """Historical SWP: redeem fixed amount each period at actual NAV."""
    d = _parse_body(request)
    try:
        amfi_code        = str(d.get('amfi_code', '')).strip()
        lumpsum_amount   = float(d.get('lumpsum_amount', 1000000))
        lumpsum_date_str = d.get('lumpsum_date', '')
        withdrawal       = float(d.get('withdrawal_amount', 10000))
        frequency        = d.get('frequency', 'monthly').lower()
        start_str        = d.get('start_date', lumpsum_date_str)
        end_str          = d.get('end_date', '')

        if not amfi_code:
            return JsonResponse({'error': 'amfi_code is required.'}, status=400)

        nav_series, inception, latest_nav, latest_date = _get_nav_series(amfi_code)
        if nav_series is None:
            return JsonResponse({'error': 'NAV data not available for this fund.'}, status=404)

        lumpsum_ts = pd.Timestamp(lumpsum_date_str) if lumpsum_date_str else nav_series.index[0]
        start_ts   = pd.Timestamp(start_str) if start_str else (lumpsum_ts + pd.DateOffset(months=1))
        end_ts     = pd.Timestamp(end_str)   if end_str   else nav_series.index[-1]

        if lumpsum_ts < nav_series.index[0]:
            lumpsum_ts = nav_series.index[0]
        if end_ts > nav_series.index[-1]:
            end_ts = nav_series.index[-1]

        entry_nav   = float(nav_series.asof(lumpsum_ts))
        if entry_nav <= 0:
            return JsonResponse({'error': 'No valid NAV on lumpsum investment date.'}, status=400)
        total_units = lumpsum_amount / entry_nav

        cashflows = [lumpsum_amount]
        cf_dates  = [lumpsum_ts.to_pydatetime()]
        swp_table = []
        total_withdrawn = 0.0
        exhausted_date  = None

        for swp_date in _sip_dates_in_range(start_ts, end_ts, frequency):
            nav_val = nav_series.asof(swp_date)
            if pd.isna(nav_val) or nav_val <= 0 or total_units <= 0:
                break

            units_redeemed    = min(withdrawal / float(nav_val), total_units)
            actual_withdrawal = units_redeemed * float(nav_val)
            total_units      -= units_redeemed
            total_withdrawn  += actual_withdrawal
            portfolio_value   = total_units * float(nav_val)

            cashflows.append(-actual_withdrawal)
            cf_dates.append(swp_date.to_pydatetime())

            swp_table.append({
                'date':              swp_date.date().isoformat(),
                'nav':               round(float(nav_val), 4),
                'units_redeemed':    round(units_redeemed, 4),
                'remaining_units':   round(total_units, 4),
                'withdrawal_amount': round(actual_withdrawal, 2),
                'portfolio_value':   round(portfolio_value, 2),
            })

            if total_units <= 0.001:
                exhausted_date = swp_date.date().isoformat()
                break

        final_nav     = float(nav_series.asof(end_ts))
        current_value = total_units * final_nav
        if current_value > 0:
            cashflows.append(-current_value)
            cf_dates.append(end_ts.to_pydatetime())

        total_return_pct = ((total_withdrawn + current_value - lumpsum_amount) / lumpsum_amount * 100) if lumpsum_amount > 0 else 0
        xirr_pct = _compute_xirr_safe(cashflows, cf_dates)

        from apps.funds.services import get_or_fetch_scheme
        scheme = get_or_fetch_scheme(amfi_code)

        return JsonResponse({
            'scheme_name':       scheme.scheme_name if scheme else amfi_code,
            'fund_house':        scheme.fund_house  if scheme else '',
            'amfi_code':         amfi_code,
            'inception_date':    inception,
            'lumpsum_amount':    lumpsum_amount,
            'lumpsum_date':      lumpsum_ts.date().isoformat(),
            'withdrawal_amount': withdrawal,
            'withdrawal_count':  len(swp_table),
            'total_withdrawn':   round(total_withdrawn, 2),
            'current_value':     round(current_value, 2),
            'remaining_units':   round(total_units, 4),
            'total_return_pct':  round(total_return_pct, 2),
            'xirr_pct':          xirr_pct,
            'start_date':        start_ts.date().isoformat(),
            'end_date':          end_ts.date().isoformat(),
            'exhausted_date':    exhausted_date,
            'swp_table':         swp_table,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_nav_lumpsum_api(request):
    """Historical Lumpsum: invest once at start NAV, redeem at end NAV (up to 4 funds)."""
    d = _parse_body(request)
    try:
        amfi_codes_raw = d.get('amfi_codes', [])
        if isinstance(amfi_codes_raw, str):
            amfi_codes_raw = [c.strip() for c in amfi_codes_raw.split(',') if c.strip()]
        amfi_codes = list(dict.fromkeys(str(c).strip() for c in amfi_codes_raw if c))[:4]

        if not amfi_codes:
            return JsonResponse({'error': 'At least one amfi_code is required.'}, status=400)

        amount    = float(d.get('amount', 100000))
        start_str = d.get('start_date', '')
        end_str   = d.get('end_date', '')

        results      = []
        chart_series = []

        from apps.funds.services import get_or_fetch_scheme
        from apps.funds.runtime import fetch_nav_and_meta, nav_rows_to_series

        for code in amfi_codes:
            nav_rows, _ = fetch_nav_and_meta(code)
            if not nav_rows:
                results.append({'amfi_code': code, 'error': 'NAV data not available'})
                continue
            nav_series = nav_rows_to_series(nav_rows)
            if nav_series.empty:
                results.append({'amfi_code': code, 'error': 'Empty NAV series'})
                continue

            scheme       = get_or_fetch_scheme(code)
            inception_ts = nav_series.index[0]

            start_ts = pd.Timestamp(start_str) if start_str else inception_ts
            end_ts   = pd.Timestamp(end_str)   if end_str   else nav_series.index[-1]

            if start_ts < inception_ts:
                start_ts = inception_ts
            if end_ts > nav_series.index[-1]:
                end_ts = nav_series.index[-1]

            entry_nav = float(nav_series.asof(start_ts))
            exit_nav  = float(nav_series.asof(end_ts))

            if entry_nav <= 0:
                results.append({'amfi_code': code, 'error': 'Invalid entry NAV'})
                continue

            units         = amount / entry_nav
            current_value = units * exit_nav
            profit        = current_value - amount
            abs_return    = (profit / amount * 100) if amount > 0 else 0
            years         = max((end_ts - start_ts).days / 365.25, 1 / 365.25)
            cagr_ret      = ((exit_nav / entry_nav) ** (1 / years) - 1) * 100
            xirr_pct      = _compute_xirr_safe(
                [-amount, current_value],
                [start_ts.to_pydatetime(), end_ts.to_pydatetime()]
            )

            # Build normalised chart (portfolio value over time)
            window      = nav_series[(nav_series.index >= start_ts) & (nav_series.index <= end_ts)]
            chart_dates  = [di.date().isoformat() for di in window.index]
            chart_values = [round(amount * (v / entry_nav), 2) for v in window.values]

            results.append({
                'amfi_code':       code,
                'scheme_name':     scheme.scheme_name if scheme else code,
                'fund_house':      scheme.fund_house  if scheme else '',
                'category':        scheme.scheme_category if scheme else '',
                'inception_date':  inception_ts.date().isoformat(),
                'start_date':      start_ts.date().isoformat(),
                'end_date':        end_ts.date().isoformat(),
                'entry_nav':       round(entry_nav, 4),
                'exit_nav':        round(exit_nav, 4),
                'amount_invested': amount,
                'current_value':   round(current_value, 2),
                'profit':          round(profit, 2),
                'absolute_return': round(abs_return, 2),
                'cagr':            round(cagr_ret, 2),
                'xirr_pct':        xirr_pct,
            })
            chart_series.append({
                'name':   scheme.scheme_name if scheme else code,
                'dates':  chart_dates,
                'values': chart_values,
            })

        return JsonResponse({'funds': results, 'chart_series': chart_series, 'amount': amount})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_nav_step_sip_api(request):
    """Historical Step-Up SIP: same as calc_nav_sip_api; step_up_pct applies each year."""
    return calc_nav_sip_api(request)


@require_http_methods(["POST"])
def calc_nav_stp_api(request):
    """Historical STP: Transfer fixed amount periodically from source fund to target fund."""
    d = _parse_body(request)
    try:
        amfi_source = str(d.get('amfi_code_source', '')).strip()
        amfi_target = str(d.get('amfi_code_target', '')).strip()
        lumpsum_amount = float(d.get('lumpsum_amount', 1000000))
        lumpsum_date_str = d.get('lumpsum_date', '')
        transfer_amount = float(d.get('transfer_amount', 10000))
        frequency = d.get('frequency', 'monthly').lower()
        stp_day = int(d.get('stp_day', 1))
        start_str = d.get('start_date', '')
        end_str = d.get('end_date', '')

        if not amfi_source or not amfi_target:
            return JsonResponse({'error': 'Source and Target fund AMFI codes are required.'}, status=400)
        if amfi_source == amfi_target:
            return JsonResponse({'error': 'Source and Target funds cannot be the same.'}, status=400)

        nav_src, inc_src, lat_nav_src, lat_date_src = _get_nav_series(amfi_source)
        nav_tgt, inc_tgt, lat_nav_tgt, lat_date_tgt = _get_nav_series(amfi_target)

        if nav_src is None or nav_tgt is None:
            return JsonResponse({'error': 'NAV data not available for one or both funds.'}, status=404)

        lumpsum_ts = pd.Timestamp(lumpsum_date_str) if lumpsum_date_str else nav_src.index[0]
        start_ts = pd.Timestamp(start_str) if start_str else (lumpsum_ts + pd.DateOffset(months=1))
        end_ts = pd.Timestamp(end_str) if end_str else min(nav_src.index[-1], nav_tgt.index[-1])

        # Clamp to valid NAV boundaries
        if lumpsum_ts < nav_src.index[0]: lumpsum_ts = nav_src.index[0]
        if end_ts > nav_src.index[-1]: end_ts = nav_src.index[-1]
        if end_ts > nav_tgt.index[-1]: end_ts = nav_tgt.index[-1]

        # Initial lumpsum in Source
        entry_nav_src = float(nav_src.asof(lumpsum_ts))
        if entry_nav_src <= 0:
            return JsonResponse({'error': 'Invalid entry NAV for source fund on lumpsum date.'}, status=400)
        
        src_units = lumpsum_amount / entry_nav_src
        tgt_units = 0.0

        stp_table = []
        total_transferred = 0.0
        exhausted_date = None

        # Cashflows for combined XIRR calculation: [-Lumpsum, Final_Value]
        # For Source XIRR: [-Lumpsum, +Transfers..., +Final_Source_Value]
        # For Target XIRR: [-Transfers..., +Final_Target_Value]
        cf_src = [-lumpsum_amount]
        dt_src = [lumpsum_ts.to_pydatetime()]
        cf_tgt = []
        dt_tgt = []

        for stp_date in _sip_dates_in_range(start_ts, end_ts, frequency, day=stp_day):
            val_src = nav_src.asof(stp_date)
            val_tgt = nav_tgt.asof(stp_date)
            
            if pd.isna(val_src) or pd.isna(val_tgt) or val_src <= 0 or val_tgt <= 0:
                continue
            
            if src_units <= 0:
                break

            # Cannot transfer more than the remaining balance in source
            max_transfer = src_units * float(val_src)
            actual_transfer = min(transfer_amount, max_transfer)
            
            units_redeemed = actual_transfer / float(val_src)
            units_bought = actual_transfer / float(val_tgt)
            
            src_units -= units_redeemed
            tgt_units += units_bought
            total_transferred += actual_transfer
            
            src_value = src_units * float(val_src)
            tgt_value = tgt_units * float(val_tgt)
            
            cf_src.append(actual_transfer)
            dt_src.append(stp_date.to_pydatetime())
            cf_tgt.append(-actual_transfer)
            dt_tgt.append(stp_date.to_pydatetime())
            
            stp_table.append({
                'date': stp_date.date().isoformat(),
                'src_nav': round(float(val_src), 4),
                'tgt_nav': round(float(val_tgt), 4),
                'transfer_amount': round(actual_transfer, 2),
                'src_units_remaining': round(src_units, 4),
                'tgt_units_accumulated': round(tgt_units, 4),
                'src_value': round(src_value, 2),
                'tgt_value': round(tgt_value, 2),
                'combined_value': round(src_value + tgt_value, 2)
            })

            if src_units <= 0.001:
                exhausted_date = stp_date.date().isoformat()
                break

        # Final values
        final_nav_src = float(nav_src.asof(end_ts))
        final_nav_tgt = float(nav_tgt.asof(end_ts))
        final_src_value = src_units * final_nav_src
        final_tgt_value = tgt_units * final_nav_tgt
        combined_final_value = final_src_value + final_tgt_value

        if final_src_value > 0:
            cf_src.append(final_src_value)
            dt_src.append(end_ts.to_pydatetime())
        if final_tgt_value > 0:
            cf_tgt.append(final_tgt_value)
            dt_tgt.append(end_ts.to_pydatetime())
            
        xirr_src = _compute_xirr_safe(cf_src, dt_src) if len(cf_src) > 1 else 0
        xirr_tgt = _compute_xirr_safe(cf_tgt, dt_tgt) if len(cf_tgt) > 1 else 0
        
        cf_combined = [-lumpsum_amount, combined_final_value]
        dt_combined = [lumpsum_ts.to_pydatetime(), end_ts.to_pydatetime()]
        xirr_combined = _compute_xirr_safe(cf_combined, dt_combined)

        from apps.funds.services import get_or_fetch_scheme
        scheme_src = get_or_fetch_scheme(amfi_source)
        scheme_tgt = get_or_fetch_scheme(amfi_target)

        return JsonResponse({
            'src_scheme_name': scheme_src.scheme_name if scheme_src else amfi_source,
            'tgt_scheme_name': scheme_tgt.scheme_name if scheme_tgt else amfi_target,
            'amfi_source': amfi_source,
            'amfi_target': amfi_target,
            'lumpsum_amount': lumpsum_amount,
            'lumpsum_date': lumpsum_ts.date().isoformat(),
            'transfer_amount': transfer_amount,
            'transfer_count': len(stp_table),
            'total_transferred': round(total_transferred, 2),
            
            'src_final_value': round(final_src_value, 2),
            'src_units_remaining': round(src_units, 4),
            'src_profit': round(final_src_value + total_transferred - lumpsum_amount, 2),
            'src_abs_return': round(((final_src_value + total_transferred - lumpsum_amount) / lumpsum_amount) * 100, 2) if lumpsum_amount else 0,
            'src_xirr': xirr_src,
            
            'tgt_final_value': round(final_tgt_value, 2),
            'tgt_units_accumulated': round(tgt_units, 4),
            'tgt_profit': round(final_tgt_value - total_transferred, 2),
            'tgt_abs_return': round(((final_tgt_value - total_transferred) / total_transferred) * 100, 2) if total_transferred else 0,
            'tgt_xirr': xirr_tgt,
            
            'combined_final_value': round(combined_final_value, 2),
            'combined_profit': round(combined_final_value - lumpsum_amount, 2),
            'combined_abs_return': round(((combined_final_value - lumpsum_amount) / lumpsum_amount) * 100, 2) if lumpsum_amount else 0,
            'combined_xirr': xirr_combined,
            
            'start_date': start_ts.date().isoformat(),
            'end_date': end_ts.date().isoformat(),
            'exhausted_date': exhausted_date,
            'stp_table': stp_table,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
