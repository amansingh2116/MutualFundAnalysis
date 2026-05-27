"""
Analytics app models — pre-computed metrics stored per scheme.

All values are recomputed nightly by apps/analytics/engine.py.
Stored so the web app never runs heavy pandas operations on user requests.

Field naming follows the roadmap exactly.
"""
from django.db import models
from apps.core.models import BaseModel


PERIOD_CHOICES = [
    ('1M', '1 Month'), ('3M', '3 Months'), ('6M', '6 Months'),
    ('1Y', '1 Year'),  ('2Y', '2 Years'),  ('3Y', '3 Years'),
    ('5Y', '5 Years'), ('7Y', '7 Years'),  ('10Y', '10 Years'),
    ('SI', 'Since Inception'),
]

WINDOW_CHOICES = [
    ('1Y', '1 Year'),
    ('3Y', '3 Years'),
    ('5Y', '5 Years'),
]


class TrailingReturn(BaseModel):
    """
    Pre-computed trailing CAGR for standard periods.
    Recomputed nightly. Also stores benchmark CAGR for the same period.
    """
    scheme   = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                 related_name='trailing_returns')
    period   = models.CharField(max_length=5, choices=PERIOD_CHOICES)
    years    = models.DecimalField(max_digits=5, decimal_places=2)
    cagr_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                   help_text="Fund CAGR in %")
    bm_cagr  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                   help_text="Benchmark CAGR for same period in %")
    excess   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                   help_text="fund_cagr - bm_cagr (alpha proxy)")
    as_of    = models.DateField(help_text="Date of last NAV used for computation")

    class Meta:
        unique_together = ('scheme', 'period', 'as_of')
        indexes = [models.Index(fields=['scheme', 'as_of'])]
        ordering = ['years']

    def __str__(self):
        return f"{self.scheme.amfi_code} | {self.period} | {self.cagr_pct}%"


class CalendarReturn(BaseModel):
    """Annual return per calendar year vs benchmark."""
    scheme       = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                     related_name='calendar_returns')
    year         = models.IntegerField()
    return_pct   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    bm_return    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    outperformed = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ('scheme', 'year')
        ordering = ['-year']

    def __str__(self):
        return f"{self.scheme.amfi_code} | {self.year} | {self.return_pct}%"


class RollingReturn(BaseModel):
    """
    Rolling return statistics for 1Y, 3Y, 5Y windows.
    Computed over the full NAV history — provides min/max/mean/std and win rates.
    """
    scheme      = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                    related_name='rolling_returns')
    window      = models.CharField(max_length=5, choices=WINDOW_CHOICES)
    window_days = models.IntegerField(help_text="252 for 1Y, 756 for 3Y, 1260 for 5Y")
    min_pct     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_pct     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    mean_pct    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    std_dev     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    win_rate_0  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                      help_text="% of rolling periods with return > 0%")
    win_rate_12 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                      help_text="% of rolling periods with return > 12%")
    as_of       = models.DateField()

    class Meta:
        unique_together = ('scheme', 'window', 'as_of')
        ordering = ['window']

    def __str__(self):
        return f"{self.scheme.amfi_code} | Rolling {self.window} | mean={self.mean_pct}%"


class RiskMetrics(BaseModel):
    """
    Risk-adjusted performance metrics for 3Y and 5Y periods.
    Computed nightly from NAV history; supplemented by mstarpy data where available.

    All percentage values stored as raw % (e.g. 15.23 means 15.23%).
    Ratios stored as raw ratio (e.g. Sharpe 1.23).
    """
    scheme           = models.ForeignKey('funds.Scheme', on_delete=models.CASCADE,
                                         related_name='risk_metrics')
    period           = models.CharField(max_length=5, choices=[('3Y','3 Years'), ('5Y','5 Years')])
    period_days      = models.IntegerField()

    # ── Volatility ─────────────────────────────────────────────────────────────
    std_dev_ann      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Annualised std dev of daily returns (%)")

    # ── Risk-adjusted return ratios ────────────────────────────────────────────
    sharpe_ratio     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    sortino_ratio    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_drawdown     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Maximum peak-to-trough decline (%)")

    # ── Benchmark-relative metrics ─────────────────────────────────────────────
    beta             = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    alpha_ann        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Annualised Jensen's alpha (%)")
    r_squared        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="R² vs benchmark (%)")
    upside_capture   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Upside capture ratio (%)")
    downside_capture = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Downside capture ratio (%)")
    tracking_error   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Annualised tracking error (%)")
    info_ratio       = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Information ratio")

    # ── Computation parameters ─────────────────────────────────────────────────
    rf_rate_used     = models.DecimalField(max_digits=5, decimal_places=3, default=0.065,
                                           help_text="Risk-free rate used (e.g. 0.065 = 6.5%)")
    benchmark        = models.ForeignKey('benchmarks.BenchmarkIndex',
                                         on_delete=models.SET_NULL, null=True, blank=True)
    as_of            = models.DateField()

    # ── Morningstar supplement (if mstarpy data available) ─────────────────────
    ms_std_dev_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    ms_sharpe_3y     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    ms_beta_3y       = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    ms_alpha_3y      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    class Meta:
        unique_together = ('scheme', 'period', 'as_of')
        indexes = [models.Index(fields=['scheme', 'period', 'as_of'])]

    def __str__(self):
        return f"{self.scheme.amfi_code} | {self.period} | Sharpe={self.sharpe_ratio}"
