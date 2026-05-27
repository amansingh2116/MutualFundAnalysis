"""
apps/funds/views.py — Core fund views
"""
import json
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView

from apps.funds.models import NAVHistory, Scheme, SchemeMeta

logger = logging.getLogger('mfanalysis')

CATEGORY_BENCHMARK_MAP = {
    'Equity Scheme - Large Cap Fund':         'NIFTY 100',
    'Equity Scheme - Mid Cap Fund':           'NIFTY MIDCAP 150',
    'Equity Scheme - Small Cap Fund':         'NIFTY SMALLCAP 250',
    'Equity Scheme - Flexi Cap Fund':         'NIFTY 500',
    'Equity Scheme - Multi Cap Fund':         'NIFTY 500',
    'Equity Scheme - ELSS':                   'NIFTY 500',
    'Equity Scheme - Large & Mid Cap Fund':   'NIFTY 200',
    'Equity Scheme - Value Fund':             'NIFTY 500',
    'Equity Scheme - Focused Fund':           'NIFTY 500',
    'Equity Scheme - Index Funds':            'NIFTY 50',
    'Hybrid Scheme - Aggressive Hybrid Fund': 'NIFTY 500',
    'Hybrid Scheme - Balanced Hybrid Fund':   'NIFTY 500',
    'Debt Scheme - Liquid Fund':              None,
    'Debt Scheme - Short Duration Fund':      None,
}

NAV_RANGE_OPTIONS = [
    ('1M', 30), ('3M', 91), ('6M', 182),
    ('1Y', 365), ('3Y', 1095), ('5Y', 1826), ('MAX', None),
]


class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx['total_funds'] = Scheme.objects.count() or None
            ctx['fund_houses'] = Scheme.objects.values('fund_house').distinct().count() or None
            latest_nav = NAVHistory.objects.order_by('-date').first()
            ctx['last_nav_date'] = latest_nav.date.strftime('%d %b %Y') if latest_nav else None
            ctx['categories'] = (
                Scheme.objects.filter(is_active=True, is_direct=True, plan='GROWTH')
                .values('scheme_category')
                .annotate(count=Count('id'))
                .order_by('-count')[:18]
            )
        except Exception:
            # App works fine even if DB is empty on first run
            ctx['total_funds'] = None
            ctx['fund_houses'] = None
            ctx['last_nav_date'] = None
            ctx['categories'] = []
        return ctx


class CategoryListView(TemplateView):
    template_name = 'funds/category_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        category = self.request.GET.get('category', '')
        qs = Scheme.objects.filter(is_active=True, is_direct=True, plan='GROWTH')
        if category:
            qs = qs.filter(scheme_category=category)
            ctx['current_category'] = category
        ctx['schemes'] = qs.order_by('scheme_name')[:200]
        ctx['categories'] = (
            Scheme.objects.filter(is_active=True).values('scheme_category')
            .annotate(count=Count('id')).order_by('-count')
        )
        return ctx


class FundDetailView(DetailView):
    model = Scheme
    template_name = 'funds/detail.html'
    slug_field = 'amfi_code'
    slug_url_kwarg = 'amfi_code'

    def get_object(self, queryset=None):
        """Auto-fetch only the lightweight scheme record if it is missing."""
        from apps.funds.services import get_or_fetch_scheme
        amfi_code = self.kwargs['amfi_code']
        scheme = get_or_fetch_scheme(amfi_code)
        if not scheme:
            raise Http404(f"Fund {amfi_code} not found and could not be fetched.")
        return scheme

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scheme = self.object
        from apps.funds.runtime import get_runtime_snapshot

        runtime = get_runtime_snapshot(scheme)

        # Keep existing templates simple without persisting these enriched values.
        if runtime.nav_latest:
            scheme.nav_latest = runtime.nav_latest
        if runtime.nav_date:
            scheme.nav_date = runtime.nav_date
        if runtime.category:
            scheme.scheme_category = runtime.category
        if runtime.meta.expense_ratio:
            scheme.expense_ratio = runtime.meta.expense_ratio
        if runtime.meta.aum:
            scheme.aum_cr = runtime.meta.aum

        ctx.update({
            'runtime': runtime,
            'meta': runtime.meta,
            'ms_data': None,
            'trailing_returns': runtime.trailing_returns,
            'calendar_returns': runtime.calendar_returns[:10],
            'rolling_1y': runtime.rolling_returns.get('1Y'),
            'rolling_3y': runtime.rolling_returns.get('3Y'),
            'rolling_5y': runtime.rolling_returns.get('5Y'),
            'risk_3y': runtime.risk_3y,
            'risk_5y': runtime.risk_5y,
            'top_holdings': runtime.top_holdings,
            'sector_alloc': runtime.sector_alloc,
            'holdings_month': runtime.holdings_month.strftime('%b %Y') if runtime.holdings_month else None,
            'asset_alloc': runtime.asset_alloc,
            'benchmark_name': runtime.benchmark_name,
            'managers': runtime.managers,
            'nav_range_options': NAV_RANGE_OPTIONS,
        })
        return ctx


def fund_search_api(request):
    """
    AJAX search endpoint for the topbar search box.
    Strategy:
      1. Search DB (fast, works after scheme list loaded)
      2. Search AMFI in-memory cache (works even with empty DB)
      3. Search mfapi.in live (last resort)
    """
    from apps.funds.services import search_amfi_cache
    q = request.GET.get('q', '').strip()
    limit = min(int(request.GET.get('limit', 8)), 20)
    if len(q) < 2:
        return JsonResponse({'results': []})

    # Try DB first (fast when populated)
    db_schemes = (
        Scheme.objects.filter(scheme_name__icontains=q, is_active=True)
        .order_by('is_direct', 'scheme_name')[:limit]
    )
    if db_schemes.exists():
        results = [
            {
                'amfi_code':      s.amfi_code,
                'scheme_name':    s.scheme_name,
                'fund_house':     s.fund_house,
                'scheme_category': s.scheme_category,
                'nav_latest':     str(s.nav_latest) if s.nav_latest else None,
                'source':         'db',
            }
            for s in db_schemes
        ]
        return JsonResponse({'results': results})

    # Fallback: AMFI cache (works with empty DB)
    cache_results = search_amfi_cache(q, limit=limit)
    results = [
        {
            'amfi_code':      r['amfi_code'],
            'scheme_name':    r['scheme_name'],
            'fund_house':     r['amc_name'],
            'scheme_category': '',
            'nav_latest':     r.get('nav') or None,
            'source':         'cache',
        }
        for r in cache_results
    ]
    return JsonResponse({'results': results})


def export_pdf_view(request, amfi_code):
    """Generate WeasyPrint PDF fund report."""
    from apps.funds.report import generate_fund_report_response
    scheme = get_object_or_404(Scheme, amfi_code=amfi_code)
    try:
        return generate_fund_report_response(request, scheme)
    except Exception as e:
        logger.error(f"PDF export failed for {amfi_code}: {e}")
        messages.error(request, f'PDF generation failed: {e}')
        return redirect('funds:detail', amfi_code=amfi_code)
