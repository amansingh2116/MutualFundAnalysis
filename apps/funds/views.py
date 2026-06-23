"""
apps/funds/views.py — Core fund views
"""
import json
import logging
import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView

from apps.funds.models import FundScreenerSnapshot, NAVHistory, Scheme, SchemeMeta
from apps.funds.screener import benchmark_options
from apps.funds.screener_reports import render_fund_report_html

logger = logging.getLogger('mfanalysis')

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


class FundScreenerView(TemplateView):
    template_name = 'funds/screener.html'
    paginate_by = 50

    sort_options = {
        'name': 'fund_name',
        'aum': 'aum_cr',
        'expense': 'expense_ratio',
        'age': 'fund_age_years',
        'return_1y': 'returns_1y_pct',
        'cagr_3y': 'cagr_3y_pct',
        'return_5y': 'returns_5y_pct',
        'rolling_3y': 'rolling_return_3y_pct',
        'rolling_5y': 'rolling_return_5y_pct',
        'volatility_3y': 'volatility_3y_pct',
        'sharpe': 'sharpe_ratio',
        'sortino': 'sortino_ratio',
        'drawdown': 'max_drawdown',
        'excess_1y': 'excess_return_1y',
        'excess_3y': 'excess_return_3y',
        'updated': 'updated_at',
    }

    export_columns = [
        ('fund_name', 'Scheme Name'),
        ('fund_house', 'Fund House'),
        ('category_group', 'Scheme Category'),
        ('scheme_sub_category', 'Scheme Sub-category'),
        ('plan_type', 'Plan Type'),
        ('benchmark_type', 'Benchmark Type'),
        ('benchmark_name', 'Benchmark'),
        ('aum_cr', 'AUM (Cr)'),
        ('expense_ratio', 'Expense Ratio (%)'),
        ('fund_age_years', 'Fund Age (Years)'),
        ('returns_1y_pct', '1-Yr Return (%)'),
        ('cagr_3y_pct', '3-Yr CAGR (%)'),
        ('returns_5y_pct', '5-Yr Return (%)'),
        ('rolling_return_3y_pct', '3-Yr Rolling Return (%)'),
        ('rolling_return_5y_pct', '5-Yr Rolling Return (%)'),
        ('volatility_3y_pct', '3-Yr Volatility (%)'),
        ('sharpe_ratio', '3-Yr Sharpe'),
        ('sortino_ratio', '3-Yr Sortino'),
        ('max_drawdown', '3-Yr Max Drawdown (%)'),
        ('excess_return_1y', '1-Yr Excess Return (%)'),
        ('excess_return_3y', '3-Yr Excess Return (%)'),
        ('risk_label', 'Risk'),
        ('data_as_of', 'Data As Of'),
    ]

    def get(self, request, *args, **kwargs):
        qs = self.filtered_queryset()
        if request.GET.get('export') == 'csv':
            return self.export_csv(qs)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.filtered_queryset()
        paginator = Paginator(qs, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get('page'))

        ctx.update({
            'page_obj': page_obj,
            'snapshots': page_obj.object_list,
            'total_count': paginator.count,
            'filter_options': self.filter_options(),
            'selected': self.selected_filters(),
            'last_updated': (
                FundScreenerSnapshot.objects.order_by('-updated_at')
                .values_list('updated_at', flat=True)
                .first()
            ),
            'query_string': self.query_string_without('page', 'export'),
        })
        return ctx

    def filtered_queryset(self):
        request = self.request
        qs = FundScreenerSnapshot.objects.select_related('scheme').all()

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(fund_name__icontains=q)
                | Q(fund_house__icontains=q)
                | Q(scheme__amfi_code__icontains=q)
                | Q(benchmark_name__icontains=q)
            )

        list_filters = {
            'house': 'fund_house__in',
            'category': 'category_group__in',
            'sub_category': 'scheme_sub_category__in',
            'plan_type': 'plan_type__in',
            'income_type': 'income_type__in',
            'benchmark_type': 'benchmark_type__in',
            'benchmark': 'benchmark_name__in',
            'risk': 'risk_label__in',
        }
        for param, lookup in list_filters.items():
            values = [v for v in request.GET.getlist(param) if v]
            if values:
                qs = qs.filter(**{lookup: values})

        range_filters = {
            'aum': 'aum_cr',
            'expense': 'expense_ratio',
            'age': 'fund_age_years',
            'return_1y': 'returns_1y_pct',
            'cagr_3y': 'cagr_3y_pct',
            'return_5y': 'returns_5y_pct',
            'rolling_3y': 'rolling_return_3y_pct',
            'rolling_5y': 'rolling_return_5y_pct',
            'volatility_3y': 'volatility_3y_pct',
            'sharpe': 'sharpe_ratio',
            'sortino': 'sortino_ratio',
            'drawdown': 'max_drawdown',
            'excess_1y': 'excess_return_1y',
            'excess_3y': 'excess_return_3y',
        }
        for param, field in range_filters.items():
            min_value = self.decimal_param(f'{param}_min')
            max_value = self.decimal_param(f'{param}_max')
            if min_value is not None:
                qs = qs.filter(**{f'{field}__gte': min_value})
            if max_value is not None:
                qs = qs.filter(**{f'{field}__lte': max_value})

        sort = request.GET.get('sort', 'name')
        sort_field = self.sort_options.get(sort, 'fund_name')
        direction = request.GET.get('direction', 'asc')
        if direction == 'desc':
            sort_field = f'-{sort_field}'
        qs = qs.order_by(sort_field, 'fund_name')
        return qs

    def filter_options(self):
        base = FundScreenerSnapshot.objects.all()
        return {
            'houses': self.distinct_values(base, 'fund_house'),
            'categories': self.distinct_values(base, 'category_group'),
            'sub_categories': self.distinct_values(base, 'scheme_sub_category'),
            'plan_types': self.distinct_values(base, 'plan_type'),
            'benchmark_types': self.distinct_values(base, 'benchmark_type'),
            'benchmarks': self.distinct_values(base, 'benchmark_name') or benchmark_options(),
            'risks': self.distinct_values(base, 'risk_label'),
        }

    def selected_filters(self):
        request = self.request
        return {
            'q': request.GET.get('q', ''),
            'house': request.GET.getlist('house'),
            'category': request.GET.getlist('category'),
            'sub_category': request.GET.getlist('sub_category'),
            'plan_type': request.GET.getlist('plan_type'),
            'income_type': request.GET.getlist('income_type'),
            'benchmark_type': request.GET.getlist('benchmark_type'),
            'benchmark': request.GET.getlist('benchmark'),
            'risk': request.GET.getlist('risk'),
            'aum_min': request.GET.get('aum_min', ''),
            'aum_max': request.GET.get('aum_max', ''),
            'expense_min': request.GET.get('expense_min', ''),
            'expense_max': request.GET.get('expense_max', ''),
            'age_min': request.GET.get('age_min', ''),
            'age_max': request.GET.get('age_max', ''),
            'return_1y_min': request.GET.get('return_1y_min', ''),
            'return_1y_max': request.GET.get('return_1y_max', ''),
            'cagr_3y_min': request.GET.get('cagr_3y_min', ''),
            'cagr_3y_max': request.GET.get('cagr_3y_max', ''),
            'return_5y_min': request.GET.get('return_5y_min', ''),
            'return_5y_max': request.GET.get('return_5y_max', ''),
            'rolling_3y_min': request.GET.get('rolling_3y_min', ''),
            'rolling_3y_max': request.GET.get('rolling_3y_max', ''),
            'rolling_5y_min': request.GET.get('rolling_5y_min', ''),
            'rolling_5y_max': request.GET.get('rolling_5y_max', ''),
            'volatility_3y_min': request.GET.get('volatility_3y_min', ''),
            'volatility_3y_max': request.GET.get('volatility_3y_max', ''),
            'sharpe_min': request.GET.get('sharpe_min', ''),
            'sharpe_max': request.GET.get('sharpe_max', ''),
            'sortino_min': request.GET.get('sortino_min', ''),
            'sortino_max': request.GET.get('sortino_max', ''),
            'drawdown_min': request.GET.get('drawdown_min', ''),
            'drawdown_max': request.GET.get('drawdown_max', ''),
            'excess_1y_min': request.GET.get('excess_1y_min', ''),
            'excess_1y_max': request.GET.get('excess_1y_max', ''),
            'excess_3y_min': request.GET.get('excess_3y_min', ''),
            'excess_3y_max': request.GET.get('excess_3y_max', ''),
            'sort': request.GET.get('sort', 'name'),
            'direction': request.GET.get('direction', 'asc'),
        }

    def export_csv(self, qs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="fund-screener.csv"'
        writer = csv.writer(response)
        writer.writerow([label for _, label in self.export_columns])
        for row in qs[:5000]:
            writer.writerow([getattr(row, field) for field, _ in self.export_columns])
        return response

    def query_string_without(self, *keys):
        params = self.request.GET.copy()
        for key in keys:
            params.pop(key, None)
        return params.urlencode()

    def decimal_param(self, name):
        value = self.request.GET.get(name)
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def distinct_values(qs, field):
        return list(
            qs.exclude(**{field: ''})
            .order_by(field)
            .values_list(field, flat=True)
            .distinct()
        )


def screener_report_view(request, amfi_code):
    snapshot = get_object_or_404(
        FundScreenerSnapshot.objects.select_related('scheme'),
        scheme__amfi_code=amfi_code,
    )
    return HttpResponse(render_fund_report_html(snapshot), content_type='text/html; charset=utf-8')


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
            'rolling_returns': runtime.rolling_returns,
            'rolling_1y': runtime.rolling_returns.get('1Y'),
            'rolling_3y': runtime.rolling_returns.get('3Y'),
            'rolling_5y': runtime.rolling_returns.get('5Y'),
            'risk_3y': runtime.risk_3y,
            'risk_5y': runtime.risk_5y,
            'yearly_risk': runtime.yearly_risk,
            'quarterly_performance': getattr(runtime, 'quarterly_performance', None),
            'top_holdings': runtime.top_holdings,
            'sector_alloc': runtime.sector_alloc,
            'holdings_month': runtime.holdings_month.strftime('%b %Y') if runtime.holdings_month else None,
            'asset_alloc': runtime.asset_alloc,
            'top10_weight': runtime.top10_weight,
            'total_holdings_count': runtime.total_holdings_count,
            'portfolio_turnover': runtime.meta.portfolio_turnover,
            'benchmark_name': runtime.benchmark_name,
            'benchmark_display_name': runtime.benchmark_display_name,
            'benchmark_actual_name': runtime.benchmark_actual_name,
            'benchmark_ticker': runtime.benchmark_ticker,
            'benchmark_note': runtime.benchmark_note,
            'benchmark_fallback_used': runtime.benchmark_fallback_used,
            'managers': runtime.managers,
            'manager_cards': runtime.manager_cards,
            'manager_context': runtime.manager_context,
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
        Scheme.objects.filter(
            Q(scheme_name__icontains=q)
            | Q(fund_house__icontains=q)
            | Q(isin_growth__icontains=q)
            | Q(isin_idcw__icontains=q)
            | Q(amfi_code__icontains=q),
            is_active=True,
        )
        .order_by('-is_direct', 'scheme_name')[:limit]
    )
    if db_schemes.exists():
        results = []
        for s in db_schemes:
            inception = None
            try:
                # 1. Try SchemeMeta start_date
                if hasattr(s, 'meta') and s.meta and s.meta.start_date:
                    inception = s.meta.start_date.isoformat()
                else:
                    # 2. Fallback to the very first NAV record date
                    first_nav = s.nav_history.order_by('date').first()
                    if first_nav:
                        inception = first_nav.date.isoformat()
            except Exception:
                pass
            results.append({
                'amfi_code':       s.amfi_code,
                'scheme_name':     s.scheme_name,
                'fund_house':      s.fund_house,
                'scheme_category': s.scheme_category,
                'nav_latest':      str(s.nav_latest) if s.nav_latest else None,
                'inception_date':  inception,
                'source':          'db',
            })
        return JsonResponse({'results': results})

    # Fallback: AMFI cache (works with empty DB)
    cache_results = search_amfi_cache(q, limit=limit)
    results = [
        {
            'amfi_code':       r['amfi_code'],
            'scheme_name':     r['scheme_name'],
            'fund_house':      r['amc_name'],
            'scheme_category': '',
            'nav_latest':      r.get('nav') or None,
            'inception_date':  None,  # not available in AMFI cache
            'source':          'cache',
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
