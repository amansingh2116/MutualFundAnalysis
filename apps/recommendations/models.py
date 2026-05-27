"""
Recommendations app models — rule-based fund suggestions.
Phase 1: stub models. Phase 2: scoring logic in engine.
"""
from django.db import models
from apps.core.models import BaseModel


class RecommendationProfile(BaseModel):
    """
    User risk profile → drives which funds get recommended.
    Phase 2: populated from a questionnaire form.
    """
    RISK_LEVELS = [
        ('conservative', 'Conservative'),
        ('moderate', 'Moderate'),
        ('aggressive', 'Aggressive'),
    ]
    HORIZONS = [
        ('1y', '< 1 Year'),
        ('1_3y', '1-3 Years'),
        ('3_5y', '3-5 Years'),
        ('5_10y', '5-10 Years'),
        ('10y_plus', '10+ Years'),
    ]
    user          = models.OneToOneField('auth.User', on_delete=models.CASCADE,
                                         related_name='rec_profile')
    risk_level    = models.CharField(max_length=20, choices=RISK_LEVELS, default='moderate')
    horizon       = models.CharField(max_length=20, choices=HORIZONS, default='3_5y')
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} — {self.risk_level} / {self.horizon}"


class FundRecommendation(BaseModel):
    """
    A recommended fund for a given profile/category.
    Phase 2: computed by a scoring engine based on risk metrics + trailing returns.
    """
    profile   = models.ForeignKey(RecommendationProfile, on_delete=models.CASCADE,
                                  related_name='recommendations', null=True, blank=True)
    scheme    = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE)
    score     = models.DecimalField(max_digits=6, decimal_places=2, default=0,
                                    help_text="Composite score (higher = better fit)")
    rank      = models.IntegerField(default=0)
    reason    = models.TextField(blank=True, help_text="Human-readable explanation")
    category  = models.CharField(max_length=200, blank=True,
                                 help_text="SEBI category for grouping")

    class Meta:
        ordering = ['category', 'rank']

    def __str__(self):
        return f"#{self.rank} {self.scheme.scheme_name[:50]} (score={self.score})"
