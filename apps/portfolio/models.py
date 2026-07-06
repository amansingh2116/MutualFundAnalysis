"""
Portfolio app models — user-owned transaction data from CAS PDF imports.

Privacy: All portfolio data is user-owned and private.
"""
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class Portfolio(BaseModel):
    """A user's mutual fund portfolio (may have multiple)."""
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='portfolios')
    name       = models.CharField(max_length=100, default='My Portfolio')
    is_private = models.BooleanField(default=True, help_text="Always True for CAS data")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.name}"


class Transaction(BaseModel):
    """Individual buy/sell/SIP/redeem transaction parsed from CAS PDF."""
    TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('SIP', 'SIP'),
        ('REDEEM', 'Redeem'),
        ('SWITCH_IN', 'Switch In'),
        ('SWITCH_OUT', 'Switch Out'),
        ('DIV_PAYOUT', 'Dividend Payout'),
        ('DIV_REINV', 'Dividend Reinvestment'),
    ]
    portfolio   = models.ForeignKey(Portfolio, on_delete=models.CASCADE,
                                    related_name='transactions')
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    help_text="Linked after fuzzy matching CAS name to DB")
    scheme_name = models.CharField(max_length=300,
                                   help_text="Raw name from CAS PDF before matching")
    amfi_code   = models.CharField(max_length=10, blank=True)
    tx_type     = models.CharField(max_length=15, choices=TYPES)
    tx_date     = models.DateField()
    units       = models.DecimalField(max_digits=15, decimal_places=4)
    nav         = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    amount      = models.DecimalField(max_digits=15, decimal_places=2)
    folio       = models.CharField(max_length=30, blank=True)
    stamp_duty  = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=['portfolio', 'tx_date']),
            models.Index(fields=['scheme', 'tx_date']),
        ]
        ordering = ['-tx_date']

    def __str__(self):
        return f"{self.tx_type} | {self.scheme_name[:40]} | {self.tx_date} | ₹{self.amount}"


class SavedStrategy(BaseModel):
    """
    A user-saved backtester strategy plan.

    Stores the full plan JSON (assets + settings + rebalance) so users can
    load it back into the backtester at any time.
    The optional last_result_json caches the most recent simulation result
    for display on the strategies compare page.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_strategies',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    plan_json = models.JSONField(
        help_text="Serialised PortfolioPlanV2 payload (assets + settings + rebalance)"
    )
    last_result_json = models.JSONField(
        null=True, blank=True,
        help_text="Cached result from last backtest run (optional, used for compare page)"
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Saved Strategy'
        verbose_name_plural = 'Saved Strategies'

    def __str__(self):
        return f"{self.user.username} — {self.name}"
