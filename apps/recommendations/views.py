"""apps/recommendations/views.py — Draft implementation"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import RecommendationProfile

@login_required
def engine_view(request):
    if request.method == 'POST':
        risk = request.POST.get('risk_level', 'moderate')
        horizon = request.POST.get('horizon', '3_5y')
        income = request.POST.get('monthly_income') or 0
        
        profile, _ = RecommendationProfile.objects.update_or_create(
            user=request.user,
            defaults={
                'risk_level': risk,
                'horizon': horizon,
                'monthly_income': income,
            }
        )
        # Generate recommendations
        from .engine import generate_recommendations
        generate_recommendations(profile)
        
        return redirect('recommendations:result')
    return render(request, 'recommendations/questionnaire.html')


@login_required
def result_view(request):
    profile = getattr(request.user, 'rec_profile', None)
    recommendations = []
    allocation = {}
    if profile:
        recommendations = profile.recommendations.select_related('scheme').all()
        from .engine import get_asset_allocation
        allocation = get_asset_allocation(profile.risk_level, profile.horizon)
    return render(request, 'recommendations/result.html', {
        'profile': profile,
        'recommendations': recommendations,
        'allocation': allocation
    })


@login_required
def backtest_view(request):
    profile = getattr(request.user, 'rec_profile', None)
    if not profile or not profile.recommendations.exists():
        return redirect('recommendations:engine')
        
    # Simulate SIP across all recommended funds
    recommendations = list(profile.recommendations.select_related('scheme').all())
    monthly_sip = 10000
    sip_per_fund = monthly_sip / len(recommendations)
    
    total_invested = 0
    current_value = 0
    from apps.analytics.engine import simulate_sip, _load_nav_series
    
    results = []
    for rec in recommendations:
        try:
            nav = _load_nav_series(rec.scheme)
            # 5 years backtest
            import pandas as pd
            start_date = nav.index[-1] - pd.Timedelta(days=5*365)
            sim = simulate_sip(nav, monthly_amount=sip_per_fund, start_date=start_date)
            if sim:
                total_invested += sim['total_invested']
                current_value += sim['current_value']
                sim['scheme_name'] = rec.scheme.scheme_name
                results.append(sim)
        except Exception:
            pass
            
    abs_gain = current_value - total_invested
    abs_pct = (abs_gain / total_invested * 100) if total_invested > 0 else 0
    
    return render(request, 'recommendations/backtest.html', {
        'profile': profile,
        'results': results,
        'total_invested': total_invested,
        'current_value': current_value,
        'abs_gain': abs_gain,
        'abs_pct': abs_pct,
        'monthly_sip': monthly_sip
    })
