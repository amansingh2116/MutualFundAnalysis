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
