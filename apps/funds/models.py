"""
Funds app models — master scheme registry, NAV history, enrichment metadata.

All other apps FK to Scheme (the central model).
Fields, naming, and constraints are exactly as defined in roadmap.md §5.
"""
from django.db import models
from apps.core.models import BaseModel


class Scheme(BaseModel):
    """
    Master record for every AMFI-registered mutual fund scheme.
    Populated by: management command build_scheme_master (AMFI NAVAll.txt)
    Enriched by:  ingest_metadata (captnemo.in)
    Updated by:   ingest_nav (daily)
    """

    # ── Primary identifiers ───────────────────────────────────────────────────
    amfi_code    = models.CharField(max_length=10, unique=True, db_index=True,
                                    help_text="AMFI scheme code (e.g. '120503')")
    isin_growth  = models.CharField(max_length=15, null=True, blank=True, db_index=True,
                                    help_text="ISIN for Growth plan")
    isin_idcw    = models.CharField(max_length=15, null=True, blank=True,
                                    help_text="ISIN for IDCW plan")

    # ── Core metadata (from AMFI NAVAll.txt + mfapi.in meta) ─────────────────
    scheme_name     = models.CharField(max_length=300)
    fund_house      = models.CharField(max_length=200, db_index=True)
    scheme_type     = models.CharField(max_length=100,
                                       help_text="'Open Ended' / 'Close Ended' / 'Interval'")
    scheme_category = models.CharField(max_length=200, db_index=True,
                                       help_text="Full SEBI category string")
    plan            = models.CharField(max_length=10, db_index=True,
                                       choices=[('GROWTH', 'Growth'), ('IDCW', 'IDCW')],
                                       default='GROWTH')
    is_direct       = models.BooleanField(default=False, db_index=True)
    is_active       = models.BooleanField(default=True, db_index=True)

    # ── Cross-source identifiers (populated by mapping commands) ──────────────
    morningstar_id = models.CharField(max_length=20, null=True, blank=True,
                                      help_text="Morningstar SecId e.g. 'F00000PDX2'")
    yahoo_ticker   = models.CharField(max_length=30, null=True, blank=True,
                                      help_text="Yahoo Finance ticker e.g. '0P000PDX2.BO'")
    kuvera_code    = models.CharField(max_length=30, null=True, blank=True,
                                      help_text="Kuvera/captnemo 'code' field")

    # Denormalized cached fields used by browse/search and fund detail pages.
    expense_ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    aum_cr        = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                        help_text="AUM in crores")
    nav_latest    = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    nav_date      = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['scheme_name']
        indexes = [
            models.Index(fields=['scheme_category', 'is_direct', 'plan']),
            models.Index(fields=['fund_house', 'is_active']),
            models.Index(fields=['is_direct', 'plan', 'is_active']),
        ]

    def __str__(self):
        return f"[{self.amfi_code}] {self.scheme_name}"

    @property
    def short_name(self) -> str:
        """Fund house name without 'Mutual Fund' suffix."""
        return self.fund_house.replace('Mutual Fund', '').strip()

    @property
    def plan_label(self) -> str:
        return 'Direct' if self.is_direct else 'Regular'


class NAVHistory(BaseModel):
    """
    Daily NAV for a scheme.
    The single most critical table — everything joins here.
    Populated by: ingest_nav (daily, via mfapi.in → mftool fallback).
    """
    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE,
                               related_name='nav_history', db_index=True)
    date   = models.DateField(db_index=True)
    nav    = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ('scheme', 'date')
        indexes = [
            models.Index(fields=['scheme', 'date']),
            models.Index(fields=['date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.scheme.amfi_code} | {self.date} | ₹{self.nav}"


class SchemeMeta(BaseModel):
    """
    Rich metadata from captnemo.in (62 fields confirmed in exploration notebook).
    One-to-one with Scheme. Populated by: ingest_metadata (weekly).
    Morningstar supplements stored here too (from mstarpy).

    Field naming exactly matches captnemo.in response keys wherever possible.
    """
    scheme = models.OneToOneField(Scheme, on_delete=models.CASCADE,
                                  related_name='meta', primary_key=False)

    # ── Investment rules ──────────────────────────────────────────────────────
    lump_available      = models.BooleanField(default=True)
    lump_min            = models.DecimalField(max_digits=12, decimal_places=2,
                                              null=True, blank=True)
    lump_min_additional = models.DecimalField(max_digits=12, decimal_places=2,
                                              null=True, blank=True)
    sip_available       = models.BooleanField(default=True)
    sip_min             = models.DecimalField(max_digits=12, decimal_places=2,
                                              null=True, blank=True)
    sip_dates           = models.JSONField(default=list, blank=True,
                                           help_text="List of valid SIP date strings")
    sip_multiplier      = models.DecimalField(max_digits=10, decimal_places=2,
                                              null=True, blank=True)
    redemption_allowed  = models.BooleanField(default=True)
    switch_allowed      = models.BooleanField(default=True)
    stp_flag            = models.BooleanField(default=False)
    swp_flag            = models.BooleanField(default=False)
    lock_in_period      = models.IntegerField(default=0,
                                              help_text="Lock-in period in days")
    tax_period          = models.IntegerField(default=0,
                                              help_text="Tax lock-in period in days")

    # ── Cost metrics (snapshotted weekly from captnemo) ───────────────────────
    expense_ratio      = models.DecimalField(max_digits=5, decimal_places=2,
                                             null=True, blank=True)
    expense_ratio_date = models.DateField(null=True, blank=True)
    aum                = models.BigIntegerField(null=True, blank=True,
                                                help_text="AUM in crores")
    fund_rating        = models.IntegerField(null=True, blank=True,
                                             help_text="Kuvera rating 1-5")
    fund_rating_date   = models.DateField(null=True, blank=True)
    volatility         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)

    # ── Pre-computed returns from captnemo (snapshotted; backup when NAV unavail) ──
    returns_1w         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_1m         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_3m         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_1y         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_3y         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_5y         = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)
    returns_inception  = models.DecimalField(max_digits=8, decimal_places=4,
                                             null=True, blank=True)

    # ── Textual / qualitative info ────────────────────────────────────────────
    fund_manager        = models.TextField(blank=True,
                                           help_text="Semicolon-separated manager names")
    crisil_rating       = models.CharField(max_length=100, blank=True)
    investment_objective= models.TextField(blank=True)
    portfolio_turnover  = models.DecimalField(max_digits=8, decimal_places=4,
                                              null=True, blank=True)
    start_date          = models.DateField(null=True, blank=True,
                                           help_text="Fund inception date")
    detail_info_url     = models.URLField(blank=True,
                                          help_text="Link to SID/KIM document")

    # ── Morningstar supplement (from mstarpy, fetched weekly) ─────────────────
    ms_rating          = models.IntegerField(null=True, blank=True,
                                             help_text="Morningstar star rating 1-5")
    ms_category        = models.CharField(max_length=150, blank=True)
    ms_category_rank   = models.IntegerField(null=True, blank=True)

    # ── Peer data ─────────────────────────────────────────────────────────────
    comparison_peers   = models.JSONField(default=list, blank=True,
                                          help_text="Raw comparison list from captnemo")

    # ── Provenance ────────────────────────────────────────────────────────────
    last_fetched  = models.DateTimeField(auto_now=True)
    fetch_source  = models.CharField(max_length=50, default='captnemo')

    class Meta:
        verbose_name = 'Scheme Metadata'
        verbose_name_plural = 'Scheme Metadata'

    def __str__(self):
        return f"Meta: {self.scheme.scheme_name}"

    @property
    def managers_list(self) -> list:
        """Return fund managers as a list."""
        return [m.strip() for m in self.fund_manager.split(';') if m.strip()]

    @property
    def is_elss(self) -> bool:
        return self.lock_in_period >= 1095  # 3 years


class FundScreenerSnapshot(BaseModel):
    """
    Denormalized, manually refreshable fund screener row.

    The refresh_screener_data management command derives this from Scheme,
    SchemeMeta, NAVHistory, and analytics tables so the screener UI can filter
    and sort without doing heavy joins for every request.
    """
    scheme = models.OneToOneField(
        Scheme,
        on_delete=models.CASCADE,
        related_name='screener_snapshot',
    )

    fund_name = models.CharField(max_length=300)
    fund_house = models.CharField(max_length=200, db_index=True)
    category_group = models.CharField(max_length=40, db_index=True)
    scheme_sub_category = models.CharField(max_length=120, blank=True, db_index=True)
    income_type = models.CharField(max_length=30, blank=True, db_index=True)
    plan_type = models.CharField(max_length=30, blank=True, db_index=True)
    is_direct = models.BooleanField(default=False, db_index=True)
    is_etf = models.BooleanField(default=False, db_index=True)

    benchmark_type = models.CharField(max_length=40, blank=True, db_index=True)
    benchmark_name = models.CharField(max_length=160, blank=True, db_index=True)
    risk_label = models.CharField(max_length=30, blank=True, db_index=True)

    aum_cr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expense_ratio = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fund_age_years = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    returns_1y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    returns_3y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    returns_5y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    cagr_3y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    rolling_return_3y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    rolling_return_5y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    volatility_3y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    volatility_5y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Risk-adjusted metrics (from RiskMetrics 3Y)
    sharpe_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                       help_text="3Y Sharpe ratio")
    sortino_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                        help_text="3Y Sortino ratio")
    max_drawdown = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                       help_text="3Y max drawdown %")

    # 5Y Risk metrics
    sharpe_ratio_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                          help_text="5Y Sharpe ratio")
    sortino_ratio_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="5Y Sortino ratio")
    max_drawdown_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                          help_text="5Y max drawdown %")

    # Excess return vs benchmark (fund return - benchmark return)
    excess_return_1y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="1Y fund CAGR minus benchmark CAGR")
    excess_return_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="3Y fund CAGR minus benchmark CAGR")

    # ── Short-period returns (from SchemeMeta captnemo data) ─────────────────
    returns_1w_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                         help_text="1-week return %")
    returns_1m_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                         help_text="1-month return %")
    returns_3m_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                         help_text="3-month return %")
    returns_6m_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                         help_text="6-month return %")

    # ── Extended CAGR periods (from TrailingReturn) ───────────────────────────
    cagr_7y_pct  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                       help_text="7Y trailing CAGR %")
    cagr_10y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                       help_text="10Y trailing CAGR %")
    cagr_si_pct  = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                       help_text="Since-inception CAGR %")

    # ── Benchmark-relative risk metrics (from RiskMetrics 3Y / 5Y) ───────────
    alpha_3y          = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="3Y annualised Jensen's alpha %")
    alpha_5y          = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="5Y annualised Jensen's alpha %")
    beta_3y           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="3Y Beta vs benchmark")
    beta_5y           = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="5Y Beta vs benchmark")
    r_squared_3y      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="3Y R-squared vs benchmark (%)")
    r_squared_5y      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="5Y R-squared vs benchmark (%)")
    tracking_error_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="3Y annualised tracking error %")
    tracking_error_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="5Y annualised tracking error %")
    info_ratio_3y     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="3Y information ratio")
    info_ratio_5y     = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                            help_text="5Y information ratio")
    upside_capture_3y   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                              help_text="3Y upside capture ratio %")
    downside_capture_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                              help_text="3Y downside capture ratio %")

    # ── Composite risk metrics ────────────────────────────────────────────────
    current_drawdown = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Current drawdown from 1Y peak (%)")
    romad_3y         = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                           help_text="Return over Max Drawdown: 3Y CAGR / |3Y Max DD|")

    # ── Fund details from SchemeMeta ─────────────────────────────────────────
    fund_manager      = models.TextField(blank=True, help_text="Semicolon-separated manager names")
    crisil_rating     = models.CharField(max_length=100, blank=True, help_text="CRISIL fund rating")
    lock_in_days      = models.IntegerField(null=True, blank=True, help_text="Lock-in period in days")
    sip_min           = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                            help_text="Minimum SIP amount")
    lump_min          = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                            help_text="Minimum lumpsum amount")
    portfolio_turnover = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True,
                                             help_text="Portfolio turnover ratio")
    sip_available     = models.BooleanField(null=True, blank=True, help_text="SIP investment available")
    nav_latest        = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True,
                                            help_text="Latest NAV value")

    # ── Model score (denormalized from FundModelScore) ────────────────────────
    model_score       = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                            db_index=True, help_text="Our composite model score 0–100")
    model_score_badge = models.CharField(max_length=20, blank=True,
                                         help_text="Score badge: Strong/Good/Fair/Weak/Poor")

    # ── Quartile ranks within scheme_sub_category (1=top, 4=bottom) ──────────
    quartile_return_1y   = models.IntegerField(null=True, blank=True, db_index=True,
                                               help_text="Q1–Q4 rank for 1Y return within sub-category")
    quartile_return_3y   = models.IntegerField(null=True, blank=True, db_index=True,
                                               help_text="Q1–Q4 rank for 3Y return within sub-category")
    quartile_return_5y   = models.IntegerField(null=True, blank=True, db_index=True,
                                               help_text="Q1–Q4 rank for 5Y return within sub-category")
    quartile_volatility  = models.IntegerField(null=True, blank=True,
                                               help_text="Q1–Q4 rank for volatility (lower vol = Q1)")
    rolling_returns_json = models.JSONField(default=dict, blank=True,
                                            help_text="Avg rolling return stats (1Y/3Y/5Y) for the scheme")
    calendar_returns_json = models.JSONField(default=dict, blank=True,
                                             help_text="Calendar year returns for the scheme")
    quartile_sharpe      = models.IntegerField(null=True, blank=True,
                                               help_text="Q1–Q4 rank for Sharpe ratio (higher = Q1)")
    quartile_sortino     = models.IntegerField(null=True, blank=True,
                                               help_text="Q1–Q4 rank for Sortino ratio (higher = Q1)")
    quartile_model_score = models.IntegerField(null=True, blank=True, db_index=True,
                                               help_text="Q1–Q4 rank for model score (higher = Q1)")

    # ── Numeric rank for display (e.g. '12/97') ───────────────────────────────
    rank_return_1y    = models.IntegerField(null=True, blank=True,
                                            help_text="Numeric rank within sub-category for 1Y return")
    rank_return_3y    = models.IntegerField(null=True, blank=True)
    rank_return_5y    = models.IntegerField(null=True, blank=True)
    rank_count_in_cat = models.IntegerField(null=True, blank=True,
                                            help_text="Total peers in this sub-category at rank time")

    data_as_of = models.DateField(null=True, blank=True, db_index=True)
    nav_as_of = models.DateField(null=True, blank=True)
    analytics_as_of = models.DateField(null=True, blank=True)
    metadata_as_of = models.DateTimeField(null=True, blank=True)
    source_notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['fund_name']
        indexes = [
            models.Index(fields=['category_group', 'scheme_sub_category']),
            models.Index(fields=['fund_house', 'category_group']),
            models.Index(fields=['plan_type', 'is_direct']),
            models.Index(fields=['benchmark_type', 'benchmark_name']),
            models.Index(fields=['cagr_3y_pct']),
            models.Index(fields=['cagr_7y_pct']),
            models.Index(fields=['cagr_10y_pct']),
            models.Index(fields=['rolling_return_3y_pct']),
            models.Index(fields=['volatility_3y_pct']),
            models.Index(fields=['sharpe_ratio']),
            models.Index(fields=['excess_return_1y']),
            models.Index(fields=['excess_return_3y']),
            models.Index(fields=['data_as_of']),
            models.Index(fields=['quartile_return_1y']),
            models.Index(fields=['quartile_return_3y']),
            models.Index(fields=['quartile_return_5y']),
            models.Index(fields=['quartile_model_score']),
            models.Index(fields=['model_score']),
            models.Index(fields=['alpha_3y']),
            models.Index(fields=['current_drawdown']),
        ]

    def __str__(self):
        return f"Screener: {self.fund_name}"


class FundModelScore(BaseModel):
    """
    Full scorer output (from apps.analytics.scorer.score_fund) stored per scheme.

    Stored separately from FundScreenerSnapshot so the scorer can evolve
    independently — bump score_version and rerun populate_screener to refresh.

    Uses DB-only portfolio data (Option B): Composition pillar is UNRATED for
    funds whose holdings haven't been fetched into the Holding table yet.
    Performance + Risk + Cost pillars are always computed from analytics tables.
    """
    scheme        = models.OneToOneField(
        Scheme, on_delete=models.CASCADE, related_name='model_score',
    )
    score_version = models.CharField(max_length=10, default='2.0',
                                     help_text="scorer.MODEL_VERSION at compute time")
    final_score   = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                        help_text="Overall composite score 0–100")
    confidence    = models.CharField(max_length=20, blank=True,
                                     help_text="RATED / PROVISIONAL / UNRATED")
    score_badge   = models.CharField(max_length=20, blank=True,
                                     help_text="Strong / Good / Fair / Weak / Poor")

    # ── Pillar scores ─────────────────────────────────────────────────────────
    score_performance = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    score_risk        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    score_cost        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    score_composition = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    score_debt        = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    score_manager     = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    # ── Pillar status ─────────────────────────────────────────────────────────
    perf_status  = models.CharField(max_length=20, blank=True)
    risk_status  = models.CharField(max_length=20, blank=True)
    cost_status  = models.CharField(max_length=20, blank=True)
    comp_status  = models.CharField(max_length=20, blank=True)
    debt_status  = models.CharField(max_length=20, blank=True)
    manager_status = models.CharField(max_length=20, blank=True)

    # ── Red flags ─────────────────────────────────────────────────────────────
    red_flags_json  = models.JSONField(default=list, blank=True,
                                       help_text="List of red flag dicts from scorer")
    red_flag_penalty = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    overall_interpretation = models.TextField(blank=True)
    nav_days               = models.IntegerField(null=True, blank=True)
    computed_at            = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Fund Model Score'
        indexes = [
            models.Index(fields=['final_score']),
            models.Index(fields=['confidence']),
        ]

    def __str__(self):
        return f"Score: {self.scheme.amfi_code} | {self.final_score} ({self.confidence})"


class CategorySnapshot(BaseModel):
    """
    Pre-computed aggregate metrics per SEBI sub-category.
    Populated by: python manage.py populate_home_dashboard
    One row per scheme_sub_category (direct Growth plans only).
    """
    category_group      = models.CharField(max_length=40, db_index=True)
    scheme_sub_category = models.CharField(max_length=120, unique=True, db_index=True)
    benchmark_name      = models.CharField(max_length=160, blank=True)
    fund_count          = models.IntegerField(default=0)

    # ── Return statistics (1Y) ────────────────────────────────────────────────
    avg_return_1y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_return_1y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    min_return_1y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    median_return_1y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    excess_return_1y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # ── Return statistics (3Y) ────────────────────────────────────────────────
    avg_return_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_return_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    min_return_3y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    median_return_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    excess_return_3y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # ── Return statistics (5Y) ────────────────────────────────────────────────
    avg_return_5y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_return_5y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    min_return_5y    = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    median_return_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # ── Risk statistics ───────────────────────────────────────────────────────
    avg_volatility   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_sharpe       = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_sortino      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_max_drawdown = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    avg_volatility_5y   = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_sharpe_5y       = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_sortino_5y      = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    avg_max_drawdown_5y = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # ── Score distribution ────────────────────────────────────────────────────
    avg_model_score  = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    pct_strong       = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                           help_text="% funds with score >= 75")
    pct_good         = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                           help_text="% funds with score 55–75")
    pct_fair         = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                           help_text="% funds with score 40–55")
    pct_weak         = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                           help_text="% funds with score < 40")

    data_as_of = models.DateField(null=True, blank=True, db_index=True)

    # ── Pre-computed time-series returns (for tabular heatmap UI) ───────────────
    calendar_returns_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Avg category CAGR % by calendar year. "
            'Format: {"2018": 12.3, "2019": 8.1, ...}'
        ),
    )
    quarterly_returns_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Avg category trailing return % for standard periods. "
            'Format: {"1W": 0.5, "1M": 1.2, "3M": 4.5, "6M": 8.0, "1Y": 14.2, "3Y": 11.1, "5Y": 13.5}'
        ),
    )
    rolling_returns_json = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Avg category rolling return stats (1Y/3Y/5Y). "
            'Format: {"1Y": {"avg": 12.3, "max": 20.1, "min": -5.4, "pos_pct": 80.5}, ...}'
        ),
    )

    class Meta:
        verbose_name = 'Category Snapshot'
        verbose_name_plural = 'Category Snapshots'
        ordering = ['category_group', 'scheme_sub_category']
        indexes = [
            models.Index(fields=['category_group']),
            models.Index(fields=['data_as_of']),
        ]

    def __str__(self):
        return f"CategorySnapshot: {self.scheme_sub_category} ({self.fund_count} funds)"
