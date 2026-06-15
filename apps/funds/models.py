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
    volatility_3y_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

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
            models.Index(fields=['rolling_return_3y_pct']),
            models.Index(fields=['volatility_3y_pct']),
            models.Index(fields=['data_as_of']),
        ]

    def __str__(self):
        return f"Screener: {self.fund_name}"
