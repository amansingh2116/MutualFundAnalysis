"""
Recommendations app models — rule-based fund suggestions.
Phase 2: Formal decision engine models.
"""
from django.db import models
from apps.core.models import BaseModel

class RecommendationProfile(BaseModel):
    """
    User risk profile → drives which funds get recommended.
    Populated from a multi-step questionnaire form.
    """
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='rec_profile')

    # ── Step 1: About You ──────────────────────────────────────────────────
    age = models.IntegerField(null=True, blank=True)
    dependents = models.IntegerField(default=0)
    income_stability = models.CharField(max_length=20, choices=[
        ('stable', 'Stable Salary'),
        ('variable', 'Variable/Business'),
        ('irregular', 'Irregular/Freelance')
    ], default='stable')
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    emergency_fund_months = models.IntegerField(default=3, help_text="Months of expenses saved")
    debt_load = models.CharField(max_length=20, choices=[
        ('none', 'No Debt'),
        ('low', 'Low (e.g. standard EMI)'),
        ('moderate', 'Moderate'),
        ('high', 'High Burden')
    ], default='low')

    # ── Step 2: Your Goal ──────────────────────────────────────────────────
    goal_type = models.CharField(max_length=20, choices=[
        ('emergency', 'Emergency Fund'),
        ('house', 'Buying a House'),
        ('education', 'Child Education'),
        ('retirement', 'Retirement'),
        ('wealth', 'Wealth Creation'),
        ('tax_saving', 'Tax Saving'),
        ('income', 'Regular Income')
    ], default='wealth')
    goal_horizon = models.CharField(max_length=20, choices=[
        ('1y', '< 1 Year'),
        ('1_3y', '1-3 Years'),
        ('3_5y', '3-5 Years'),
        ('5_10y', '5-10 Years'),
        ('10y_plus', '10+ Years'),
    ], default='5_10y')
    liquidity_need = models.CharField(max_length=20, choices=[
        ('low', 'Low (Locked in is fine)'),
        ('medium', 'Medium'),
        ('high', 'High (Might need anytime)')
    ], default='low')
    tax_sensitivity = models.CharField(max_length=20, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High (Tax efficiency critical)')
    ], default='medium')

    # ── Step 3: Your Style ──────────────────────────────────────────────────
    loss_reaction = models.CharField(max_length=20, choices=[
        ('sell', 'Panic and Sell'),
        ('concerned', 'Concerned but Hold'),
        ('calm', 'Stay Calm'),
        ('buy_more', 'Buy More at Discount')
    ], default='calm')
    investing_experience = models.CharField(max_length=20, choices=[
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert')
    ], default='intermediate')
    income_type = models.CharField(max_length=20, choices=[
        ('salary', 'Monthly Salary'),
        ('variable', 'Variable Income'),
        ('lumpsum', 'Lump Sum Capital')
    ], default='salary')
    payout_preference = models.CharField(max_length=20, choices=[
        ('growth', 'Growth (Compounding)'),
        ('idcw', 'IDCW (Periodic Payouts)')
    ], default='growth')
    hands_on = models.CharField(max_length=20, choices=[
        ('simple', 'Keep it Simple'),
        ('active', 'Active/Thematic is fine')
    ], default='simple')

    # ── Derived Decision Variables (Computed by Engine) ─────────────────────
    risk_capacity = models.CharField(max_length=20, null=True, blank=True)
    risk_tolerance = models.CharField(max_length=20, null=True, blank=True)
    final_risk_profile = models.CharField(max_length=20, null=True, blank=True)
    investor_archetype = models.CharField(max_length=50, null=True, blank=True)
    
    recommended_strategy = models.CharField(max_length=20, null=True, blank=True)
    plan_style = models.CharField(max_length=20, null=True, blank=True)
    option_style = models.CharField(max_length=20, null=True, blank=True)
    rebalance_frequency = models.CharField(max_length=20, null=True, blank=True)

    core_equity_pct = models.IntegerField(default=0)
    core_debt_pct = models.IntegerField(default=0)
    satellite_pct = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} — {self.investor_archetype or 'Incomplete'}"


class FundRecommendation(BaseModel):
    """
    A recommended fund for a given profile.
    Computed by the decision engine using scoring logic.
    """
    profile   = models.ForeignKey(RecommendationProfile, on_delete=models.CASCADE,
                                  related_name='recommendations', null=True, blank=True)
    scheme    = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE)
    score     = models.DecimalField(max_digits=6, decimal_places=2, default=0,
                                    help_text="Composite score (3Y CAGR + Sharpe + ER)")
    rank      = models.IntegerField(default=0)
    role      = models.CharField(max_length=20, choices=[('core', 'Core'), ('satellite', 'Satellite')], default='core')
    reason    = models.TextField(blank=True, help_text="Human-readable explanation")
    category  = models.CharField(max_length=200, blank=True,
                                 help_text="SEBI category for grouping")

    class Meta:
        ordering = ['role', 'rank']

    def __str__(self):
        return f"#{self.rank} {self.scheme.scheme_name[:50]} ({self.role})"

