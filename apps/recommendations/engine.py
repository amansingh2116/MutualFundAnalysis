"""
apps/recommendations/engine.py — Recommendation Engine
"""
import logging
from decimal import Decimal
from django.db.models import F
from apps.funds.models import Scheme
from apps.recommendations.models import FundRecommendation

logger = logging.getLogger('mfanalysis')

# Hardcoded top AMFI codes per category to ensure we always have 
# good recommendations even if the DB is mostly empty.
# These will be lazy-loaded on-demand.
TOP_FUNDS = {
    'Equity Scheme - Flexi Cap Fund': [119551, 122639, 118272], # Parag Parikh, Quant, HDFC
    'Equity Scheme - Mid Cap Fund': [118989, 119062, 118778], # Motilal, Kotak, HDFC
    'Equity Scheme - Small Cap Fund': [118721, 120193, 125354], # Nippon, SBI, Quant
    'Equity Scheme - Index Funds': [120716, 118989], # UTI Nifty 50, HDFC Index
    'Debt Scheme - Short Duration Fund': [119108, 119598], # HDFC, SBI Short Term
    'Debt Scheme - Liquid Fund': [120503, 119594], # Liquid funds
}

def get_asset_allocation(risk_level: str, horizon: str) -> dict:
    """Return recommended asset allocation percentages."""
    if horizon in ('1y', '1_3y'):
        # Short horizon -> heavy debt regardless of risk
        return {'equity': 10, 'debt': 90, 'gold': 0}
    
    if risk_level == 'conservative':
        return {'equity': 30, 'debt': 60, 'gold': 10}
    elif risk_level == 'aggressive':
        return {'equity': 80, 'debt': 10, 'gold': 10}
    else: # moderate
        return {'equity': 60, 'debt': 30, 'gold': 10}

def generate_recommendations(profile):
    """
    Generate fund recommendations for a given profile.
    Saves to FundRecommendation.
    """
    FundRecommendation.objects.filter(profile=profile).delete()
    alloc = get_asset_allocation(profile.risk_level, profile.horizon)
    
    from apps.funds.services import prepare_fund_for_display
    
    categories_to_pick = []
    if alloc['equity'] > 0:
        if profile.risk_level == 'aggressive':
            categories_to_pick.extend(['Equity Scheme - Small Cap Fund', 'Equity Scheme - Mid Cap Fund', 'Equity Scheme - Flexi Cap Fund'])
        elif profile.risk_level == 'moderate':
            categories_to_pick.extend(['Equity Scheme - Flexi Cap Fund', 'Equity Scheme - Mid Cap Fund'])
        else:
            categories_to_pick.extend(['Equity Scheme - Index Funds', 'Equity Scheme - Flexi Cap Fund'])
            
    if alloc['debt'] > 0:
        if profile.horizon in ('1y', '1_3y'):
            categories_to_pick.append('Debt Scheme - Liquid Fund')
        else:
            categories_to_pick.append('Debt Scheme - Short Duration Fund')

    rank = 1
    for cat in categories_to_pick:
        # Pre-load known top funds for this category if needed
        codes = TOP_FUNDS.get(cat, [])
        for code in codes:
            prepare_fund_for_display(str(code))
            
        # Pick the best active direct growth fund in this category based on AUM or Name (fallback)
        qs = Scheme.objects.filter(
            scheme_category=cat, 
            is_active=True, 
            is_direct=True, 
            plan='GROWTH'
        ).order_by('-aum_cr')
        
        best_fund = qs.first()
        if best_fund:
            FundRecommendation.objects.create(
                profile=profile,
                scheme=best_fund,
                score=Decimal('90.0'),
                rank=rank,
                reason=f"Selected for {cat} exposure based on your {profile.risk_level} profile.",
                category=cat
            )
            rank += 1
