"""apps/recommendations/views.py — Recommendation Engine Views"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import RecommendationProfile

@login_required
def engine_view(request):
    profile = getattr(request.user, 'rec_profile', None)
    if request.method == 'POST':
        # Step 1
        age = request.POST.get('age')
        dependents = request.POST.get('dependents', 0)
        income_stability = request.POST.get('income_stability', 'stable')
        monthly_income = request.POST.get('monthly_income') or 0
        emergency_fund_months = request.POST.get('emergency_fund_months', 3)
        debt_load = request.POST.get('debt_load', 'low')
        
        # Step 2
        goal_type = request.POST.get('goal_type', 'wealth')
        goal_horizon = request.POST.get('goal_horizon', '5_10y')
        liquidity_need = request.POST.get('liquidity_need', 'low')
        tax_sensitivity = request.POST.get('tax_sensitivity', 'medium')
        
        # Step 3
        loss_reaction = request.POST.get('loss_reaction', 'calm')
        investing_experience = request.POST.get('investing_experience', 'intermediate')
        income_type = request.POST.get('income_type', 'salary')
        payout_preference = request.POST.get('payout_preference', 'growth')
        hands_on = request.POST.get('hands_on', 'simple')
        
        profile, _ = RecommendationProfile.objects.update_or_create(
            user=request.user,
            defaults={
                'age': int(age) if age else None,
                'dependents': int(dependents),
                'income_stability': income_stability,
                'monthly_income': monthly_income,
                'emergency_fund_months': int(emergency_fund_months),
                'debt_load': debt_load,
                
                'goal_type': goal_type,
                'goal_horizon': goal_horizon,
                'liquidity_need': liquidity_need,
                'tax_sensitivity': tax_sensitivity,
                
                'loss_reaction': loss_reaction,
                'investing_experience': investing_experience,
                'income_type': income_type,
                'payout_preference': payout_preference,
                'hands_on': hands_on,
            }
        )
        # Generate recommendations using the new 9-layer engine
        from .engine import generate_recommendations
        generate_recommendations(profile)
        
        return redirect('recommendations:result')
        
    # GET Request
    if profile and profile.investor_archetype and not request.GET.get('edit'):
        return redirect('recommendations:result')
        
    return render(request, 'recommendations/questionnaire.html', {'profile': profile})


@login_required
def result_view(request):
    profile = getattr(request.user, 'rec_profile', None)
    if not profile or not profile.investor_archetype:
        return redirect('recommendations:engine')
        
    recommendations = profile.recommendations.select_related('scheme').all()
    
    # Check if there are any red flags based on profile
    red_flags = []
    if profile.emergency_fund_months < 3:
        red_flags.append("You have less than 3 months of emergency funds. Please build this before investing heavily in equity.")
    if profile.debt_load == 'high':
        red_flags.append("High debt burden detected. Prioritize paying off high-interest debt before aggressive investing.")
    if profile.liquidity_need == 'high' and profile.core_equity_pct > 30:
        red_flags.append("High liquidity need but high equity allocation. Equity investments should have a lock-in mindset.")
        
    warnings = []
    if profile.payout_preference == 'idcw':
        warnings.append("You selected IDCW. Note that dividends are taxed at your marginal rate, which may reduce compounding compared to Growth options.")
    if profile.tax_sensitivity == 'high' and profile.goal_type != 'tax_saving':
        warnings.append("Consider maximizing ELSS (Section 80C) before other equity funds if tax saving is highly important.")
        
    return render(request, 'recommendations/result.html', {
        'profile': profile,
        'recommendations': recommendations,
        'red_flags': red_flags,
        'warnings': warnings
    })


@login_required
def backtest_view(request):
    """
    Redirect to the Portfolio Backtester with recommended funds pre-populated.
    Encodes the recommended fund plan as URL query params so the backtester
    can render the plan builder pre-filled and ready to run.
    """
    profile = getattr(request.user, 'rec_profile', None)
    if not profile or not profile.recommendations.exists():
        return redirect('recommendations:engine')

    recommendations = list(profile.recommendations.select_related('scheme').all())

    # Determine SIP amount per fund
    monthly_sip = 10000
    if profile.monthly_income and profile.monthly_income > 0:
        monthly_sip = float(profile.monthly_income) * 0.20

    sip_per_fund = round(monthly_sip / len(recommendations), 0) if recommendations else monthly_sip

    # Build pre-population params for the backtester
    import json as _json
    from datetime import date, timedelta
    five_years_ago = (date.today() - timedelta(days=5*365)).strftime('%Y-%m-%d')

    prefill_funds = []
    for rec in recommendations:
        if not rec.scheme or not rec.scheme.amfi_code:
            continue
        prefill_funds.append({
            'label': rec.scheme.scheme_name[:40],
            'source_type': 'scheme',
            'source_id': rec.scheme.amfi_code,
            'rules': [{
                'rule_type': 'sip',
                'amount': sip_per_fund,
                'frequency': 'monthly',
                'start_date': five_years_ago,
                'end_date': None,
                'step_up_pct': 0,
            }]
        })

    # Pass as GET param to backtester
    import urllib.parse
    prefill_json = urllib.parse.quote(_json.dumps(prefill_funds))
    backtester_url = f"{redirect('portfolio:backtester').url}?prefill={prefill_json}&rebalance_mode=annual&debt_park_id=NIFTY+LIQUID+INDEX"
    return redirect(backtester_url)

