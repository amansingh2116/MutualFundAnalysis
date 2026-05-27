"""apps/calculators/views.py — All 10 calculators"""
import json
import logging
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


# ── Calculator API Endpoints ──────────────────────────────────

def _parse_body(request):
    try:
        return json.loads(request.body)
    except Exception:
        return request.POST.dict()


@require_http_methods(["POST"])
def calc_sip_api(request):
    """SIP Calculator: monthly_amount, years, expected_rate (%) → results."""
    d = _parse_body(request)
    try:
        monthly = float(d.get('monthly_amount', 10000))
        years = float(d.get('years', 10))
        rate = float(d.get('expected_rate', 12)) / 100 / 12  # monthly rate
        n = int(years * 12)
        if rate == 0:
            future_value = monthly * n
        else:
            future_value = monthly * ((((1 + rate) ** n) - 1) / rate) * (1 + rate)
        invested = monthly * n
        gain = future_value - invested
        return JsonResponse({
            'total_invested': round(invested, 2),
            'future_value': round(future_value, 2),
            'gain': round(gain, 2),
            'return_pct': round((gain / invested) * 100, 2),
            'monthly_amount': monthly,
            'years': years,
            'n_instalments': n,
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
        future_value = principal * ((1 + rate) ** years)
        gain = future_value - principal
        return JsonResponse({
            'principal': principal,
            'future_value': round(future_value, 2),
            'gain': round(gain, 2),
            'return_pct': round((gain / principal) * 100, 2),
            'years': years,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["POST"])
def calc_swp_api(request):
    """SWP: corpus, monthly_withdrawal, expected_rate → months until exhausted."""
    d = _parse_body(request)
    try:
        corpus = float(d.get('corpus', 1000000))
        withdrawal = float(d.get('monthly_withdrawal', 10000))
        rate = float(d.get('expected_rate', 8)) / 100 / 12
        balance = corpus
        months = 0
        history = []
        while balance > 0 and months < 600:
            balance = balance * (1 + rate) - withdrawal
            months += 1
            if months % 12 == 0:
                history.append({'month': months, 'balance': max(0, round(balance, 2))})
        total_withdrawn = withdrawal * months
        return JsonResponse({
            'months_sustained': months,
            'years_sustained': round(months / 12, 1),
            'total_withdrawn': round(total_withdrawn, 2),
            'corpus': corpus,
            'monthly_withdrawal': withdrawal,
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


@require_http_methods(["POST"])
def calc_overlap_api(request):
    """Fund Overlap: two AMFI codes → overlapping holdings list."""
    from apps.holdings.models import Holding
    d = _parse_body(request)
    try:
        code1 = d.get('fund1')
        code2 = d.get('fund2')
        from apps.funds.models import Scheme
        s1 = Scheme.objects.get(amfi_code=code1)
        s2 = Scheme.objects.get(amfi_code=code2)

        last1 = Holding.objects.filter(scheme=s1).order_by('-as_of_month').values('as_of_month').first()
        last2 = Holding.objects.filter(scheme=s2).order_by('-as_of_month').values('as_of_month').first()

        if not last1 or not last2:
            return JsonResponse({'error': 'Holdings data not available for one or both funds. Run ingest_holdings.'})

        h1 = {h['security_name']: h['weight_pct'] for h in Holding.objects.filter(scheme=s1, as_of_month=last1['as_of_month']).values('security_name', 'weight_pct')}
        h2 = {h['security_name']: h['weight_pct'] for h in Holding.objects.filter(scheme=s2, as_of_month=last2['as_of_month']).values('security_name', 'weight_pct')}

        common = set(h1.keys()) & set(h2.keys())
        overlap = [{
            'security_name': name,
            'weight_fund1': float(h1[name]),
            'weight_fund2': float(h2[name]),
        } for name in sorted(common, key=lambda x: -h1[x])]

        # Overlap score: sum of min(w1, w2) for common stocks
        overlap_score = sum(min(float(h1[n]), float(h2[n])) for n in common)

        return JsonResponse({
            'fund1_name': s1.scheme_name,
            'fund2_name': s2.scheme_name,
            'common_holdings': len(common),
            'fund1_total_holdings': len(h1),
            'fund2_total_holdings': len(h2),
            'overlap_score': round(overlap_score, 2),
            'overlap': overlap[:30],
        })
    except Scheme.DoesNotExist:
        return JsonResponse({'error': 'One or both AMFI codes not found.'}, status=404)
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
