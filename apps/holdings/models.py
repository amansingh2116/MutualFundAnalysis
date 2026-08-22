"""
Holdings app models — individual fund holdings, sector allocation, market cap blend.

Primary data source: mstarpy (monthly)
Fallback: yahooquery fund_top_holdings / fund_sector_weightings
"""
from django.db import models
from apps.core.models import BaseModel


class Holding(BaseModel):
    """Individual security held by a mutual fund (from mstarpy monthly)."""
    scheme        = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                     related_name='holdings')
    as_of_month   = models.DateField(help_text="YYYY-MM-01 — month of portfolio snapshot")
    security_name = models.CharField(max_length=300)
    isin          = models.CharField(max_length=15, blank=True)
    ticker        = models.CharField(max_length=20, blank=True)
    weight_pct    = models.DecimalField(max_digits=7, decimal_places=4,
                                       help_text="Weight in portfolio (%)")
    market_value  = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    sector        = models.CharField(max_length=100, blank=True)
    country       = models.CharField(max_length=50, default='IN')
    forward_pe    = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    holding_type  = models.CharField(max_length=20, default='equity',
                                     help_text="equity / debt / cash / other")
    source        = models.CharField(max_length=20, default='mstarpy')

    class Meta:
        unique_together = ('scheme', 'as_of_month', 'security_name')
        indexes = [
            models.Index(fields=['scheme', 'as_of_month']),
            models.Index(fields=['security_name']),
        ]
        ordering = ['-weight_pct']

    def __str__(self):
        return f"{self.security_name} ({self.weight_pct}%)"


class SectorAllocation(BaseModel):
    """Aggregated sector allocation for a scheme (from mstarpy or yahooquery)."""
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                    related_name='sector_allocations')
    as_of_month = models.DateField()
    sector      = models.CharField(max_length=100)
    weight_pct  = models.DecimalField(max_digits=7, decimal_places=4)
    source      = models.CharField(max_length=20, default='mstarpy')

    class Meta:
        unique_together = ('scheme', 'as_of_month', 'sector')
        ordering = ['-weight_pct']

    def __str__(self):
        return f"{self.sector}: {self.weight_pct}%"


class MarketCapAllocation(BaseModel):
    """Market cap breakdown: large/mid/small/other (from mstarpy or yahooquery).

    large_pct / mid_pct / small_pct are computed from equity holdings via
    CapClassifier (apps.holdings.cap_classifier) against the SEBI cap list.

    equity_pct / debt_pct / cash_pct / other_pct reflect the overall fund
    asset-class allocation (from mstarpy allocationMap or yahooquery).

    cap_method:
        'caplist'  — computed by mapping holdings against nifty_caplist.json
        'mstarpy'  — taken directly from mstarpy's native large/mid/small split
        'yahoo'    — taken from yahooquery priceToBook large/mid/small split
        'unknown'  — source unclear
    """
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                    related_name='mcap_allocations')
    as_of_month = models.DateField()
    large_pct   = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    mid_pct     = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    small_pct   = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    other_pct   = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True,
                                      help_text="Non-equity residual not classified as L/M/S")
    # Overall asset-class split
    equity_pct  = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True,
                                      help_text="% of portfolio in equities")
    debt_pct    = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True,
                                      help_text="% of portfolio in debt instruments")
    cash_pct    = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True,
                                      help_text="% of portfolio in cash & equivalents")
    # Method used for cap classification
    cap_method  = models.CharField(
        max_length=10, default='unknown',
        help_text="caplist | mstarpy | yahoo | unknown"
    )
    source      = models.CharField(max_length=20, default='mstarpy')

    class Meta:
        unique_together = ('scheme', 'as_of_month')

    def __str__(self):
        return f"Large {self.large_pct}% | Mid {self.mid_pct}% | Small {self.small_pct}%"
