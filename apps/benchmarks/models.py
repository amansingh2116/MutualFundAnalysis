"""
Benchmarks app models — NSE/global index registry and daily close history.

Primary data source: NSE Direct API
Fallback: yfinance

See roadmap.md §3.3 for BENCHMARK_TICKERS and CATEGORY_BENCHMARK_MAP.
"""
from django.db import models
from apps.core.models import BaseModel


class BenchmarkIndex(BaseModel):
    """
    Registry of benchmark indices (NSE + international).
    Seeded once by management command; grows as new indices are added.
    """
    name         = models.CharField(max_length=100, unique=True,
                                    help_text="Canonical name e.g. 'NIFTY 50'")
    nse_type_str = models.CharField(max_length=100, blank=True,
                                    help_text="NSE API indexType param (plain text, not URL-encoded)")
    yahoo_ticker = models.CharField(max_length=20, blank=True,
                                    help_text="Yahoo Finance ticker e.g. '^NSEI'")
    description  = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Benchmark Index'
        verbose_name_plural = 'Benchmark Indices'
        ordering = ['name']

    def __str__(self):
        return self.name


class BenchmarkNAV(BaseModel):
    """
    Daily closing value for a benchmark index.
    Equivalent to NAVHistory but for indices, not funds.
    Populated by: ingest_benchmarks (daily).
    """
    index  = models.ForeignKey(BenchmarkIndex, on_delete=models.CASCADE,
                               related_name='nav_history')
    date   = models.DateField(db_index=True)
    close  = models.DecimalField(max_digits=14, decimal_places=4)
    source = models.CharField(max_length=20, default='nse',
                               help_text="'nse' or 'yfinance'")

    class Meta:
        unique_together = ('index', 'date')
        indexes = [
            models.Index(fields=['index', 'date']),
            models.Index(fields=['date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.index.name} | {self.date} | {self.close}"


class BenchmarkReturns(BaseModel):
    """
    Pre-computed return snapshot for each BenchmarkIndex.
    Populated by: python manage.py populate_benchmark_returns

    Since-launch return uses the earliest BenchmarkNAV date as proxy for
    the index launch date (dynamic — no hardcoded map needed).
    """
    index    = models.OneToOneField(
        BenchmarkIndex, on_delete=models.CASCADE, related_name='returns',
    )

    # ── Period returns (CAGR %) ───────────────────────────────────────────────
    ret_1w           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1-week simple return %")
    ret_1m           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1-month simple return %")
    ret_3m           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3-month simple return %")
    ret_6m           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="6-month simple return %")
    ret_ytd          = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Year-to-date return % (Jan 1 to today)")
    ret_1y           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1-year CAGR %")
    ret_3y           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3-year CAGR %")
    ret_5y           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="5-year CAGR %")
    ret_10y          = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="10-year CAGR %")
    ret_since_launch = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="CAGR from first BenchmarkNAV date to today")

    # ── Risk metrics (annualised) ─────────────────────────────────────────────
    volatility_1y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1Y annualised volatility %")
    volatility_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3Y annualised volatility %")
    volatility_5y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="5Y annualised volatility %")
    sharpe_1y        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1Y Sharpe ratio")
    sharpe_3y        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3Y Sharpe ratio")
    sharpe_5y        = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="5Y Sharpe ratio")
    max_drawdown_1y  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1Y max drawdown %")
    max_drawdown_3y  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3Y max drawdown %")
    max_drawdown_5y  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="5Y max drawdown %")

    # ── Time-series returns ───────────────────────────────────────────────────
    calendar_returns_json = models.JSONField(default=dict, blank=True,
                                             help_text="Calendar year returns for the index")
    rolling_returns_json = models.JSONField(default=dict, blank=True,
                                            help_text="Rolling return stats (1Y/3Y/5Y) for the index")

    # ── Metadata ──────────────────────────────────────────────────────────────
    launch_date  = models.DateField(null=True, blank=True,
                                    help_text="Earliest BenchmarkNAV date (proxy for index launch)")
    data_as_of   = models.DateField(null=True, blank=True,
                                    help_text="Date of most recent BenchmarkNAV used")
    nav_count    = models.IntegerField(default=0,
                                       help_text="Number of BenchmarkNAV rows used")

    class Meta:
        verbose_name = 'Benchmark Returns'
        verbose_name_plural = 'Benchmark Returns'

    def __str__(self):
        return f"Returns: {self.index.name} | as_of={self.data_as_of}"


class UserBenchmarkProfile(BaseModel):
    """
    Stores a user's personalized list of benchmark indices to display
    on the Research > Benchmarks page.
    Each user gets one row; the watchlist is a JSON list of BenchmarkIndex IDs.
    """
    user         = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='benchmark_profile',
    )
    watchlist    = models.JSONField(
        default=list, blank=True,
        help_text="Ordered list of BenchmarkIndex PKs the user has selected.",
    )

    class Meta:
        verbose_name = 'User Benchmark Profile'

    def __str__(self):
        return f"BenchmarkProfile: {self.user.username} ({len(self.watchlist)} indices)"


class UserMarketStripProfile(BaseModel):
    """
    Stores a logged-in user's preferred metrics to display in the scrolling
    market strip at the top of every page.

    ``metrics`` is an ordered list of metric *keys* matching MARKET_INDICES
    in apps.benchmarks.registry (e.g. ["nifty50", "sensex", "midcap"]).
    An empty list means "show the site defaults".
    """
    user    = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='market_strip_profile',
    )
    metrics = models.JSONField(
        default=list, blank=True,
        help_text="Ordered list of market-strip metric keys the user has chosen.",
    )

    class Meta:
        verbose_name = 'User Market Strip Profile'

    def __str__(self):
        return f"MarketStripProfile: {self.user.username} ({len(self.metrics)} metrics)"
