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

from apps.analytics.models import RiskMetrics, TrailingReturn
from apps.funds.models import NAVHistory, Scheme, SchemeMeta
from apps.holdings.models import Holding, SectorAllocation

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
        """Auto-fetch scheme from mfapi.in if not in DB yet."""
        from apps.funds.services import prepare_fund_for_display
        amfi_code = self.kwargs['amfi_code']
        scheme, has_nav, has_meta = prepare_fund_for_display(amfi_code)
        if not scheme:
            raise Http404(f"Fund {amfi_code} not found and could not be fetched.")
        # Attach flags so get_context_data can use them
        scheme._has_nav  = has_nav
        scheme._has_meta = has_meta
        return scheme

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scheme = self.object
        today = date.today()
        latest_month = date(today.year, today.month, 1)

        meta = getattr(scheme, 'meta', None)
        ms_data = getattr(scheme, 'ms_data', None)

        trailing = list(
            scheme.trailing_returns.filter(as_of=today).order_by('years')
        )
        if not trailing:
            # Use most recent available
            last_tr = scheme.trailing_returns.order_by('-as_of').values('as_of').first()
            if last_tr:
                trailing = list(scheme.trailing_returns.filter(as_of=last_tr['as_of']).order_by('years'))

        risk_3y = scheme.risk_metrics.filter(period='3Y').order_by('-as_of').first()
        risk_5y = scheme.risk_metrics.filter(period='5Y').order_by('-as_of').first()

        top_holdings = Holding.objects.filter(
            scheme=scheme, as_of_month=latest_month
        ).order_by('-weight_pct')[:20]
        if not top_holdings.exists():
            last_holding = Holding.objects.filter(scheme=scheme).order_by('-as_of_month').first()
            if last_holding:
                top_holdings = Holding.objects.filter(
                    scheme=scheme, as_of_month=last_holding.as_of_month
                ).order_by('-weight_pct')[:20]
                latest_month = last_holding.as_of_month

        sector_alloc = SectorAllocation.objects.filter(
            scheme=scheme, as_of_month=latest_month
        ).order_by('-weight_pct')

        managers = []
        if meta and meta.fund_manager:
            managers = [m.strip() for m in meta.fund_manager.split(';') if m.strip()]

        rolling_1y = scheme.rolling_returns.filter(window='1Y').order_by('-as_of').first()
        rolling_3y = scheme.rolling_returns.filter(window='3Y').order_by('-as_of').first()
        rolling_5y = scheme.rolling_returns.filter(window='5Y').order_by('-as_of').first()

        ctx.update({
            'meta': meta,
            'ms_data': ms_data,
            'trailing_returns': trailing,
            'calendar_returns': scheme.calendar_returns.order_by('-year')[:10],
            'rolling_1y': rolling_1y,
            'rolling_3y': rolling_3y,
            'rolling_5y': rolling_5y,
            'risk_3y': risk_3y,
            'risk_5y': risk_5y,
            'top_holdings': top_holdings,
            'sector_alloc': sector_alloc,
            'holdings_month': latest_month.strftime('%b %Y') if top_holdings.exists() else None,
            'cap_alloc': None,  # Will populate when mstarpy data available
            'benchmark_name': CATEGORY_BENCHMARK_MAP.get(scheme.scheme_category),
            'managers': managers,
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
