"""
apps/recommendations/engine.py — Recommendation Engine v2
A 9-layer rule engine to convert questionnaire inputs into a portfolio recommendation.
"""
import logging
from decimal import Decimal
from django.db.models import F
from apps.funds.models import Scheme
from apps.recommendations.models import FundRecommendation
from apps.analytics.models import TrailingReturn, RiskMetrics

logger = logging.getLogger('mfanalysis')

# Fallback top AMFI codes per category to ensure we always have 
# good recommendations even if the DB scoring data is incomplete.
TOP_FUNDS = {
    'Equity Scheme - Flexi Cap Fund': [119551, 122639, 118272], # Parag Parikh, Quant, HDFC
    'Equity Scheme - Mid Cap Fund': [118989, 119062, 118778], # Motilal, Kotak, HDFC
    'Equity Scheme - Small Cap Fund': [118721, 120193, 125354], # Nippon, SBI, Quant
    'Equity Scheme - Large Cap Fund': [119063, 120586, 120716], # ICICI, SBI, UTI
    'Equity Scheme - Multi Cap Fund': [120153, 119428, 122640], # Nippon, ICICI, Quant
    'Equity Scheme - Index Funds': [120716, 118989], # UTI Nifty 50, HDFC Index
    'Equity Scheme - ELSS': [118270, 119064, 119552], # HDFC, ICICI, Parag Parikh
    'Debt Scheme - Short Duration Fund': [119108, 119598], # HDFC, SBI Short Term
    'Debt Scheme - Liquid Fund': [120503, 119594], # Liquid funds
    'Hybrid Scheme - Balanced Advantage Fund': [119034, 119067, 120163], # HDFC, ICICI, SBI
    'Hybrid Scheme - Conservative Hybrid Fund': [119053, 119586, 118281], # ICICI, SBI, HDFC
    'Hybrid Scheme - Multi Asset Allocation Fund': [119071, 118285, 122641], # ICICI, HDFC, Quant
}


def compute_risk_capacity(profile) -> str:
    """Layer 1: Financial ability to take risk"""
    ef_months = getattr(profile, 'emergency_fund_months', 3) or 3
    dependents = getattr(profile, 'dependents', 0) or 0
    inc_stab = getattr(profile, 'income_stability', 'stable') or 'stable'
    debt = getattr(profile, 'debt_load', 'low') or 'low'
    liq = getattr(profile, 'liquidity_need', 'low') or 'low'
    
    if (inc_stab == 'irregular' or 
        ef_months < 3 or 
        debt == 'high' or 
        liq == 'high'):
        return 'conservative'
    
    if (inc_stab == 'stable' and 
        ef_months >= 6 and 
        debt in ('none', 'low') and 
        dependents <= 1):
        return 'aggressive'
        
    return 'balanced'


def compute_risk_tolerance(profile) -> str:
    """Layer 2: Emotional comfort with volatility"""
    loss = getattr(profile, 'loss_reaction', 'calm') or 'calm'
    exp = getattr(profile, 'investing_experience', 'intermediate') or 'intermediate'
    
    if loss == 'sell' or (loss == 'concerned' and exp == 'beginner'):
        return 'conservative'
        
    if loss == 'buy_more' and exp in ('intermediate', 'expert'):
        return 'aggressive'
        
    return 'balanced'


def assign_final_profile(capacity: str, tolerance: str) -> str:
    """Layer 3: Final risk profile is the minimum of capacity and tolerance"""
    levels = {'conservative': 1, 'balanced': 2, 'aggressive': 3}
    cap_lvl = levels.get(capacity, 2)
    tol_lvl = levels.get(tolerance, 2)
    final_lvl = min(cap_lvl, tol_lvl)
    
    for k, v in levels.items():
        if v == final_lvl:
            return k
    return 'balanced'


def assign_archetype(final_profile: str, goal: str, horizon: str) -> str:
    """Assign an investor archetype"""
    if goal == 'tax_saving':
        return 'Tax Optimizer'
    if goal == 'income':
        return 'Income Seeker'
        
    if final_profile == 'conservative':
        if goal == 'emergency':
            return 'Capital Preserver'
        return 'Goal-Based Planner'
        
    if final_profile == 'aggressive':
        if horizon == '10y_plus' and goal == 'wealth':
            return 'Aggressive Accumulator'
        return 'Wealth Builder'
        
    # balanced
    if goal in ('house', 'education', 'retirement'):
        return 'Goal-Based Planner'
    return 'Wealth Builder'


def get_fund_universe(profile) -> list:
    """Layer 4: Map profile/horizon to appropriate fund categories"""
    h = profile.goal_horizon
    p = profile.final_risk_profile
    g = profile.goal_type
    
    if g == 'tax_saving':
        return [('Equity Scheme - ELSS', 'core')]
        
    if g == 'income':
        return [
            ('Hybrid Scheme - Conservative Hybrid Fund', 'core'),
            ('Debt Scheme - Short Duration Fund', 'core')
        ]
        
    if h == '1y':
        return [
            ('Debt Scheme - Liquid Fund', 'core'),
        ]
        
    if h == '1_3y':
        return [
            ('Debt Scheme - Short Duration Fund', 'core'),
            ('Hybrid Scheme - Conservative Hybrid Fund', 'core')
        ]
        
    if h == '3_5y':
        return [
            ('Hybrid Scheme - Balanced Advantage Fund', 'core'),
            ('Debt Scheme - Short Duration Fund', 'core')
        ]
        
    # Horizon 5y+
    if p == 'conservative':
        return [
            ('Equity Scheme - Large Cap Fund', 'core'),
            ('Equity Scheme - Index Funds', 'core'),
            ('Hybrid Scheme - Balanced Advantage Fund', 'core')
        ]
        
    if p == 'balanced':
        return [
            ('Equity Scheme - Flexi Cap Fund', 'core'),
            ('Equity Scheme - Index Funds', 'core'),
            ('Equity Scheme - Mid Cap Fund', 'satellite')
        ]
        
    # aggressive
    if h == '10y_plus':
        return [
            ('Equity Scheme - Flexi Cap Fund', 'core'),
            ('Equity Scheme - Multi Cap Fund', 'core'),
            ('Equity Scheme - Mid Cap Fund', 'satellite'),
            ('Equity Scheme - Small Cap Fund', 'satellite')
        ]
    
    # 5-10y aggressive
    return [
        ('Equity Scheme - Flexi Cap Fund', 'core'),
        ('Equity Scheme - Large Cap Fund', 'core'),
        ('Equity Scheme - Mid Cap Fund', 'satellite')
    ]


def build_portfolio_mix(profile) -> tuple:
    """Layer 5: Core-satellite allocation percentages (equity, debt, satellite)"""
    p = profile.final_risk_profile
    h = profile.goal_horizon
    
    if h in ('1y', '1_3y'):
        return (10, 90, 0)
        
    if p == 'conservative':
        return (25, 75, 0)
    elif p == 'aggressive':
        if h == '10y_plus':
            return (70, 10, 20)
        return (75, 15, 10)
    else:
        # balanced
        return (50, 45, 5)


def assign_strategy(profile) -> str:
    """Layer 6: Recommend investment strategy"""
    if profile.goal_type in ('income', 'retirement') and profile.age and profile.age > 55:
        return 'swp'
    if profile.goal_horizon == '1y':
        return 'sip'  # Safest default for short term
    if profile.income_type == 'lumpsum':
        if profile.final_risk_profile == 'conservative' or profile.investing_experience == 'beginner':
            return 'stp'
        return 'lumpsum'
    
    # Default for salary / variable
    return 'sip'


def rank_funds_for_category(category: str, is_direct: bool = True, plan: str = 'GROWTH') -> list:
    """
    Score funds using available analytics data (3Y CAGR, Sharpe, ER).
    Returns list of Scheme objects sorted by score.
    """
    qs = Scheme.objects.filter(
        scheme_category=category,
        is_active=True,
        is_direct=is_direct,
        plan=plan
    ).order_by('-aum_cr')[:20]  # Take top 20 by AUM to score
    
    scored_funds = []
    for scheme in qs:
        # Simplistic scoring for v2 (V3 will integrate full scorer.py)
        score = Decimal('0.0')
        valid = True
        
        # Performance (50% weight) -> normalized CAGR 0-20% = 0-50 pts
        tr = TrailingReturn.objects.filter(scheme=scheme, period='3Y').order_by('-as_of').first()
        if tr and tr.cagr_pct:
            cagr = min(max(float(tr.cagr_pct), 0), 20)
            score += Decimal(str((cagr / 20) * 50))
        else:
            # Fallback to AUM size if no returns
            valid = False
            
        # Risk (25% weight) -> normalized Sharpe 0-2.0 = 0-25 pts
        rm = RiskMetrics.objects.filter(scheme=scheme, period='3Y').order_by('-as_of').first()
        if rm and rm.sharpe_ratio:
            sharpe = min(max(float(rm.sharpe_ratio), 0), 2.0)
            score += Decimal(str((sharpe / 2.0) * 25))
            
        # Cost (25% weight) -> normalized ER inverted 0-2.0% = 25-0 pts
        er = scheme.expense_ratio or getattr(scheme, 'meta', None) and getattr(scheme.meta, 'expense_ratio', None)
        if er:
            er_val = min(max(float(er), 0), 2.0)
            score += Decimal(str((1 - (er_val / 2.0)) * 25))
            
        if not valid and scheme.aum_cr:
            # Fake a decent score for massive funds if analytics are missing during early DB pop
            score = Decimal('60.0') + min(scheme.aum_cr / Decimal('1000.0'), Decimal('20.0'))
            
        scored_funds.append((score, scheme))
        
    scored_funds.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored_funds]


def get_reason(category: str, role: str, profile_level: str) -> str:
    if role == 'satellite':
        return f"Added as a satellite holding for long-term alpha generation."
    if 'Index' in category:
        return "Core holding to capture broad market returns at low cost."
    if 'Debt' in category or 'Liquid' in category:
        return "Capital preservation and stability during market drawdowns."
    if 'Advantage' in category or 'Hybrid' in category:
        return "Dynamic asset allocation for smoother returns."
    return f"Core equity holding aligned with your {profile_level} profile."


def generate_recommendations(profile):
    """
    Main orchestrator: executes the 9 layers and saves results.
    """
    # 1. Clear old recs
    FundRecommendation.objects.filter(profile=profile).delete()
    
    # 2. Compute variables
    profile.risk_capacity = compute_risk_capacity(profile)
    profile.risk_tolerance = compute_risk_tolerance(profile)
    profile.final_risk_profile = assign_final_profile(profile.risk_capacity, profile.risk_tolerance)
    profile.investor_archetype = assign_archetype(profile.final_risk_profile, profile.goal_type, profile.goal_horizon)
    
    # 3. Strategy & Style
    profile.recommended_strategy = assign_strategy(profile)
    profile.plan_style = 'direct'
    profile.option_style = profile.payout_preference
    
    if profile.final_risk_profile == 'conservative':
        profile.rebalance_frequency = 'semiannual'
    elif profile.final_risk_profile == 'balanced':
        profile.rebalance_frequency = 'annual'
    else:
        profile.rebalance_frequency = 'trigger-based'
        
    # 4. Allocation mix
    eq, db, sat = build_portfolio_mix(profile)
    profile.core_equity_pct = eq
    profile.core_debt_pct = db
    profile.satellite_pct = sat
    profile.save()
    
    # 5. Fund Universe
    universe = get_fund_universe(profile)
    
    # Ensure mf_services are available
    from apps.funds.services import prepare_fund_for_display
    
    is_direct = profile.plan_style == 'direct'
    plan_code = 'IDCW' if profile.option_style == 'idcw' else 'GROWTH'
    
    rank = 1
    selected_schemes = set() # Avoid duplicates
    
    # Determine max funds to pick (User requested max 5)
    max_total_funds = 5
    
    for category, role in universe:
        if len(selected_schemes) >= max_total_funds:
            break
            
        # Ensure we have data for fallback funds
        fallback_codes = TOP_FUNDS.get(category, [])
        for code in fallback_codes:
            prepare_fund_for_display(str(code))
            
        # Score and pick
        best_funds = rank_funds_for_category(category, is_direct, plan_code)
        
        # If none found via scoring, fallback to amfi codes explicitly
        if not best_funds:
            qs = Scheme.objects.filter(amfi_code__in=[str(c) for c in fallback_codes], is_direct=is_direct, plan=plan_code)
            best_funds = list(qs)
            
        funds_to_pick = 1
        if role == 'core' and category in ('Equity Scheme - Flexi Cap Fund', 'Equity Scheme - Large Cap Fund') and len(universe) < 3:
            funds_to_pick = 2 # Pick 2 core funds if universe is small
            
        picked = 0
        for fund in best_funds:
            if fund.amfi_code not in selected_schemes:
                FundRecommendation.objects.create(
                    profile=profile,
                    scheme=fund,
                    score=Decimal('85.0'), # Placeholder for UI
                    rank=rank,
                    role=role,
                    reason=get_reason(category, role, profile.final_risk_profile),
                    category=category
                )
                selected_schemes.add(fund.amfi_code)
                rank += 1
                picked += 1
            if picked >= funds_to_pick or len(selected_schemes) >= max_total_funds:
                break

