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

from apps.funds.models import (
    CategorySnapshot, FundModelScore, FundScreenerSnapshot,
    NAVHistory, Scheme, SchemeMeta,
)
from apps.funds.screener import benchmark_options, TOP_FUND_BASKETS
from apps.funds.screener_reports import render_fund_report_html

logger = logging.getLogger('mfanalysis')

NAV_RANGE_OPTIONS = [
    ('1M', 30), ('3M', 91), ('6M', 182),
    ('1Y', 365), ('3Y', 1095), ('5Y', 1826), ('MAX', None),
]

CATEGORY_GROUPS_ORDERED = ['Equity', 'Debt', 'Hybrid', 'Other', 'Solution Oriented']


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
            ctx['total_funds'] = None
            ctx['fund_houses'] = None
            ctx['last_nav_date'] = None
            ctx['categories'] = []

        # ── Section 1: Benchmark Returns Monitor ──────────────────────────────
        try:
            from apps.benchmarks.models import BenchmarkReturns
            bench_qs = (
                BenchmarkReturns.objects
                .select_related('index')
                .filter(index__is_active=True)
                .order_by('index__name')
            )
            ctx['benchmark_returns'] = list(bench_qs)
        except Exception:
            ctx['benchmark_returns'] = []

        # ── Section 2 + 4: Category Snapshots ────────────────────────────────
        try:
            snap_qs = CategorySnapshot.objects.order_by(
                'category_group', 'scheme_sub_category'
            )
            # Group by category_group for Section 4
            cat_groups: dict[str, list] = {}
            for snap in snap_qs:
                cat_groups.setdefault(snap.category_group, []).append(snap)
            # Ordered dict for template
            ctx['category_snapshots_by_group'] = [
                (grp, cat_groups[grp])
                for grp in CATEGORY_GROUPS_ORDERED
                if grp in cat_groups
            ]
            # Flat list for Section 2 (category return meter) as JSON
            ctx['category_snapshots_json'] = json.dumps([
                {
                    'group': s.category_group,
                    'name': s.scheme_sub_category,
                    'avg_1y': _flt(s.avg_return_1y),
                    'max_1y': _flt(s.max_return_1y),
                    'min_1y': _flt(s.min_return_1y),
                    'med_1y': _flt(s.median_return_1y),
                    'avg_3y': _flt(s.avg_return_3y),
                    'max_3y': _flt(s.max_return_3y),
                    'min_3y': _flt(s.min_return_3y),
                    'med_3y': _flt(s.median_return_3y),
                    'avg_5y': _flt(s.avg_return_5y),
                    'max_5y': _flt(s.max_return_5y),
                    'min_5y': _flt(s.min_return_5y),
                    'med_5y': _flt(s.median_return_5y),
                    'fund_count': s.fund_count,
                    'avg_score': _flt(s.avg_model_score),
                    'pct_strong': _flt(s.pct_strong),
                    'pct_good': _flt(s.pct_good),
                    'pct_fair': _flt(s.pct_fair),
                    'pct_weak': _flt(s.pct_weak),
                }
                for s in snap_qs
            ])
        except Exception as exc:
            logger.warning("HomeView: category snapshots failed: %s", exc)
            ctx['category_snapshots_by_group'] = []
            ctx['category_snapshots_json'] = '[]'

        # ── Section 3: Top Performing Funds (Extensible Baskets) ───────────────
        try:
            top_baskets = []
            for basket_name, basket_filter in TOP_FUND_BASKETS.items():
                funds = (
                    FundScreenerSnapshot.objects
                    .filter(is_direct=True, **basket_filter)
                    .exclude(returns_5y_pct=None)
                    .order_by('-returns_5y_pct')
                    .select_related('scheme')
                    .only(
                        'fund_name', 'fund_house', 'expense_ratio',
                        'returns_1y_pct', 'returns_3y_pct', 'returns_5y_pct',
                        'aum_cr', 'scheme_sub_category', 'scheme',
                    )[:8]
                )
                if funds:
                    top_baskets.append({
                        'name': basket_name,
                        'slug': basket_name.lower().replace(' ', '-'),
                        'funds': list(funds),
                        'filter': basket_filter,
                    })
            ctx['top_fund_baskets'] = top_baskets
        except Exception as exc:
            logger.warning("HomeView: top baskets failed: %s", exc)
            ctx['top_fund_baskets'] = []

        # ── Section 5: Browse counts per sub-category ─────────────────────────
        try:
            from apps.funds.screener import SUB_CATEGORY_PATTERNS
            sub_cat_counts = dict(
                FundScreenerSnapshot.objects
                .filter(is_direct=True)
                .values_list('scheme_sub_category')
                .annotate(cnt=Count('id'))
            )
            # Ordered sub-category list per group for browse grid
            browse_groups: dict[str, list] = {}
            for label, _, group in SUB_CATEGORY_PATTERNS:
                browse_groups.setdefault(group, []).append({
                    'name': label,
                    'count': sub_cat_counts.get(label, 0),
                })
            ctx['browse_groups'] = [
                (grp, browse_groups[grp])
                for grp in CATEGORY_GROUPS_ORDERED
                if grp in browse_groups
            ]
        except Exception as exc:
            logger.warning("HomeView: browse groups failed: %s", exc)
            ctx['browse_groups'] = []

        # ── Section 6: Quartile Rankings — default sub-category ──────────────
        # Pre-load the most popular sub-category to avoid JS needing an extra request
        try:
            sub_cats = list(
                FundScreenerSnapshot.objects
                .filter(is_direct=True)
                .exclude(scheme_sub_category='')
                .values('scheme_sub_category')
                .annotate(cnt=Count('id'))
                .order_by('-cnt')
                .values_list('scheme_sub_category', flat=True)[:1]
            )
            default_sub_cat = sub_cats[0] if sub_cats else ''
            ctx['default_sub_cat'] = default_sub_cat

            # All distinct sub-categories for the dropdown
            ctx['all_sub_categories'] = list(
                FundScreenerSnapshot.objects
                .filter(is_direct=True)
                .exclude(scheme_sub_category='')
                .values('scheme_sub_category')
                .annotate(cnt=Count('id'))
                .order_by('scheme_sub_category')
                .values_list('scheme_sub_category', flat=True)
            )
        except Exception:
            ctx['default_sub_cat'] = ''
            ctx['all_sub_categories'] = []

        return ctx


def _flt(val) -> float | None:
    """Convert Decimal/None to float for JSON serialisation."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def home_category_funds(request):
    """
    AJAX endpoint for Section 6 — Quartile Rankings.
    GET /home/category-funds/?sub_category=Mid+Cap+Fund
    Returns JSON list of fund rows with quartile fields.
    """
    sub_category = request.GET.get('sub_category', '').strip()
    if not sub_category:
        return JsonResponse({'error': 'sub_category required'}, status=400)

    try:
        funds = list(
            FundScreenerSnapshot.objects
            .filter(scheme_sub_category=sub_category, is_direct=True)
            .select_related('scheme')
            .order_by('rank_return_1y', 'fund_name')
            .only(
                'fund_name', 'fund_house', 'scheme_sub_category',
                'returns_1y_pct', 'returns_3y_pct', 'returns_5y_pct',
                'quartile_return_1y', 'quartile_return_3y', 'quartile_return_5y',
                'quartile_volatility', 'quartile_sharpe', 'quartile_sortino',
                'quartile_model_score',
                'rank_return_1y', 'rank_return_3y', 'rank_return_5y',
                'rank_count_in_cat',
                'scheme',
            )
        )

        # Attach model score badge from FundModelScore
        scheme_ids = [f.scheme_id for f in funds]
        score_map = dict(
            FundModelScore.objects
            .filter(scheme_id__in=scheme_ids)
            .values_list('scheme_id', 'final_score')
        )

        data = []
        for f in funds:
            data.append({
                'name': f.fund_name,
                'house': f.fund_house,
                'amfi': f.scheme.amfi_code,
                'ret_1y': _flt(f.returns_1y_pct),
                'ret_3y': _flt(f.returns_3y_pct),
                'ret_5y': _flt(f.returns_5y_pct),
                'q_ret_1y': f.quartile_return_1y,
                'q_ret_3y': f.quartile_return_3y,
                'q_ret_5y': f.quartile_return_5y,
                'q_vol': f.quartile_volatility,
                'q_sharpe': f.quartile_sharpe,
                'q_sortino': f.quartile_sortino,
                'q_score': f.quartile_model_score,
                'rank_1y': f.rank_return_1y,
                'rank_3y': f.rank_return_3y,
                'rank_5y': f.rank_return_5y,
                'total': f.rank_count_in_cat,
                'score': _flt(score_map.get(f.scheme_id)),
            })

        return JsonResponse({'sub_category': sub_category, 'funds': data})

    except Exception as exc:
        logger.error("home_category_funds error: %s", exc)
        return JsonResponse({'error': 'server error'}, status=500)


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

        # ── Category Average lookup ────────────────────────────────────────────
        try:
            sub_cat = (
                FundScreenerSnapshot.objects
                .filter(scheme=scheme)
                .values_list('scheme_sub_category', flat=True)
                .first()
            ) or scheme.scheme_category or ''
            cat_snap = None
            if sub_cat:
                cat_snap = CategorySnapshot.objects.filter(
                    scheme_sub_category__iexact=sub_cat
                ).first()
            ctx['category_snap'] = cat_snap
            ctx['category_name'] = sub_cat
            # Pre-serialize rolling_returns_json and calendar_returns_json for template use
            ctx['cat_rolling_json'] = json.dumps(cat_snap.rolling_returns_json or {}) if cat_snap else '{}'
            ctx['cat_calendar_json'] = json.dumps(cat_snap.calendar_returns_json or {}) if cat_snap else '{}'
            ctx['cat_trailing_json'] = json.dumps(cat_snap.quarterly_returns_json or {}) if cat_snap else '{}'
        except Exception:
            ctx['category_snap'] = None
            ctx['category_name'] = ''
            ctx['cat_rolling_json'] = '{}'
            ctx['cat_calendar_json'] = '{}'
            ctx['cat_trailing_json'] = '{}'

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


# ════════════════════════════════════════════════════════════════════════════
# RESEARCH HUB VIEWS
# ════════════════════════════════════════════════════════════════════════════

class ResearchBenchmarksView(TemplateView):
    """
    Research > Benchmarks: Full benchmark monitor with risk metrics.
    User's benchmark watchlist (personalized selection) is loaded from
    UserBenchmarkProfile; unauthenticated users see all active benchmarks.
    """
    template_name = 'research/benchmarks.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.benchmarks.models import BenchmarkIndex, BenchmarkReturns, UserBenchmarkProfile
        try:
            # All active indices with returns data
            all_returns = list(
                BenchmarkReturns.objects
                .select_related('index')
                .filter(index__is_active=True)
                .order_by('index__name')
            )
            ctx['all_benchmark_returns'] = all_returns

            # User watchlist
            watchlist_ids = []
            if self.request.user.is_authenticated:
                profile = UserBenchmarkProfile.objects.filter(user=self.request.user).first()
                if profile and profile.watchlist:
                    watchlist_ids = profile.watchlist

            # If user has a watchlist, filter to those; else default to all with data
            if watchlist_ids:
                ctx['selected_returns'] = [
                    r for r in all_returns if r.index_id in watchlist_ids
                ]
            else:
                ctx['selected_returns'] = all_returns
                
            # Serialize for JS heatmap rendering
            benchmarks_js = []
            for r in ctx['selected_returns']:
                benchmarks_js.append({
                    'id': r.index_id,
                    'name': r.index.name,
                    'calendar': r.calendar_returns_json or {},
                    'rolling': r.rolling_returns_json or {},
                })
            ctx['benchmarks_json'] = json.dumps(benchmarks_js)

            ctx['watchlist_ids'] = json.dumps(watchlist_ids)
            ctx['all_index_names'] = [
                {'id': r.index_id, 'name': r.index.name} for r in all_returns
            ]
        except Exception as exc:
            logger.warning('ResearchBenchmarksView error: %s', exc)
            ctx['all_benchmark_returns'] = []
            ctx['selected_returns'] = []
            ctx['watchlist_ids'] = '[]'
            ctx['all_index_names'] = []
        return ctx


def benchmark_watchlist_api(request):
    """
    POST /research/benchmarks/watchlist/ — Save user's benchmark watchlist.
    Expects JSON body: {"watchlist": [id1, id2, ...]}
    Requires authentication.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        from apps.benchmarks.models import BenchmarkIndex, UserBenchmarkProfile
        data = json.loads(request.body)
        watchlist = data.get('watchlist', [])
        # Validate: only store valid BenchmarkIndex PKs
        valid_ids = list(
            BenchmarkIndex.objects.filter(pk__in=watchlist, is_active=True)
            .values_list('pk', flat=True)
        )
        profile, _ = UserBenchmarkProfile.objects.get_or_create(user=request.user)
        profile.watchlist = valid_ids
        profile.save()
        return JsonResponse({'saved': True, 'count': len(valid_ids)})
    except Exception as exc:
        logger.error('benchmark_watchlist_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


class ResearchCategoryMeterView(TemplateView):
    """
    Research > Category Returns: Full tabular heatmap of category returns.
    Supports trailing / annual / quarterly tabs.
    """
    template_name = 'research/category_meter.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            snap_qs = CategorySnapshot.objects.order_by('category_group', 'scheme_sub_category')
            ctx['category_snapshots_json'] = json.dumps([
                {
                    'group': s.category_group,
                    'name': s.scheme_sub_category,
                    'fund_count': s.fund_count,
                    'avg_1y': _flt(s.avg_return_1y),
                    'avg_3y': _flt(s.avg_return_3y),
                    'avg_5y': _flt(s.avg_return_5y),
                    'med_1y': _flt(s.median_return_1y),
                    'med_3y': _flt(s.median_return_3y),
                    'med_5y': _flt(s.median_return_5y),
                    'min_1y': _flt(s.min_return_1y),
                    'max_1y': _flt(s.max_return_1y),
                    'min_3y': _flt(s.min_return_3y),
                    'max_3y': _flt(s.max_return_3y),
                    'min_5y': _flt(s.min_return_5y),
                    'max_5y': _flt(s.max_return_5y),
                    'avg_vol': _flt(s.avg_volatility),
                    'avg_sharpe': _flt(s.avg_sharpe),
                    'avg_drawdown': _flt(s.avg_max_drawdown),
                    'calendar': s.calendar_returns_json or {},
                    'trailing': s.quarterly_returns_json or {},
                    'rolling': s.rolling_returns_json or {},
                    'slug': _make_slug(s.scheme_sub_category),
                }
                for s in snap_qs
            ])
            ctx['groups'] = CATEGORY_GROUPS_ORDERED
        except Exception as exc:
            logger.warning('ResearchCategoryMeterView error: %s', exc)
            ctx['category_snapshots_json'] = '[]'
            ctx['groups'] = []
        return ctx


class ResearchCategoriesView(TemplateView):
    """
    Research > Category Analysis: Browse all categories with search.
    """
    template_name = 'research/categories.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            snap_qs = CategorySnapshot.objects.order_by('category_group', 'scheme_sub_category')
            cat_groups: dict[str, list] = {}
            for snap in snap_qs:
                slug = _make_slug(snap.scheme_sub_category)
                cat_groups.setdefault(snap.category_group, []).append({
                    'snap': snap,
                    'slug': slug,
                })
            ctx['category_groups'] = [
                (grp, cat_groups[grp])
                for grp in CATEGORY_GROUPS_ORDERED
                if grp in cat_groups
            ]
        except Exception as exc:
            logger.warning('ResearchCategoriesView error: %s', exc)
            ctx['category_groups'] = []
        return ctx


def _make_slug(name: str) -> str:
    """Convert a sub-category name to a safe URL slug."""
    return (
        name.lower()
        .replace("'", '')   # strip apostrophes before replacing spaces
        .replace(' ', '-')
        .replace('/', '-')
        .replace('&', 'and')
        .replace('--', '-')
        .strip('-')
    )


def _slug_to_sub_category(slug: str) -> str:
    """Reverse a slug back to a scheme_sub_category name."""
    # Fuzzy: find closest match using _make_slug
    all_cats = list(CategorySnapshot.objects.values_list('scheme_sub_category', flat=True))
    for cat in all_cats:
        if _make_slug(cat) == slug:
            return cat
    # Fallback: iexact on normalized slug (handles simple cases)
    normalized = slug.replace('-', ' ')
    qs = CategorySnapshot.objects.filter(scheme_sub_category__iexact=normalized)
    if qs.exists():
        return qs.first().scheme_sub_category
    return ''


class ResearchCategoryDetailView(TemplateView):
    """
    Research > Category Deep Dive: Full tabbed analysis for a specific category.
    Tabs: Snapshot (all funds), Returns, Risk, Portfolio (composition), Fees.
    """
    template_name = 'research/category_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = kwargs.get('slug', '')
        sub_category = _slug_to_sub_category(slug)
        if not sub_category:
            ctx['error'] = 'Category not found'
            return ctx

        ctx['sub_category'] = sub_category
        ctx['slug'] = slug

        try:
            snap = CategorySnapshot.objects.filter(scheme_sub_category=sub_category).first()
            ctx['category_snap'] = snap
        except Exception:
            ctx['category_snap'] = None

        try:
            funds = list(
                FundScreenerSnapshot.objects
                .filter(scheme_sub_category=sub_category, is_direct=True)
                .select_related('scheme')
                .order_by('rank_return_1y', 'fund_name')
            )
            ctx['funds'] = funds
            ctx['funds_count'] = len(funds)

            # Attach model scores
            scheme_ids = [f.scheme_id for f in funds]
            score_map = dict(
                FundModelScore.objects
                .filter(scheme_id__in=scheme_ids)
                .values_list('scheme_id', 'final_score')
            )
            badge_map = dict(
                FundModelScore.objects
                .filter(scheme_id__in=scheme_ids)
                .values_list('scheme_id', 'score_badge')
            )
            ctx['score_map'] = score_map
            ctx['badge_map'] = badge_map

            # All sub-categories for the same group (for navigation)
            if snap:
                ctx['peer_categories'] = list(
                    CategorySnapshot.objects
                    .filter(category_group=snap.category_group)
                    .exclude(scheme_sub_category=sub_category)
                    .order_by('scheme_sub_category')
                    .values('scheme_sub_category', 'fund_count')
                )
        except Exception as exc:
            logger.warning('ResearchCategoryDetailView error: %s', exc)
            ctx['funds'] = []
            ctx['funds_count'] = 0
        return ctx


def category_detail_funds_api(request, slug):
    """
    AJAX: GET /research/categories/<slug>/funds/?tab=returns
    Returns JSON of all funds in the category, filtered by tab type.
    """
    sub_category = _slug_to_sub_category(slug)
    if not sub_category:
        return JsonResponse({'error': 'not found'}, status=404)
    tab = request.GET.get('tab', 'snapshot')
    try:
        funds = list(
            FundScreenerSnapshot.objects
            .filter(scheme_sub_category=sub_category, is_direct=True)
            .select_related('scheme')
            .order_by('rank_return_1y', 'fund_name')
        )
        scheme_ids = [f.scheme_id for f in funds]
        score_map = dict(
            FundModelScore.objects
            .filter(scheme_id__in=scheme_ids)
            .values_list('scheme_id', 'final_score')
        )
        badge_map = dict(
            FundModelScore.objects
            .filter(scheme_id__in=scheme_ids)
            .values_list('scheme_id', 'score_badge')
        )

        alloc_map = {}
        if tab == 'portfolio':
            from apps.holdings.models import SectorAllocation
            allocs = SectorAllocation.objects.filter(scheme_id__in=scheme_ids)
            for a in allocs:
                alloc_map.setdefault(a.scheme_id, {})[a.sector] = float(a.weight_pct) if a.weight_pct else 0.0

        data = []
        for f in funds:
            base = {
                'name': f.fund_name,
                'house': f.fund_house,
                'amfi': f.scheme.amfi_code,
                'score': _flt(score_map.get(f.scheme_id)),
                'badge': badge_map.get(f.scheme_id, ''),
                'rank_1y': f.rank_return_1y,
                'total': f.rank_count_in_cat,
                'aum': _flt(f.aum_cr),
                'expense': _flt(f.expense_ratio),
                'age': _flt(f.fund_age_years),
                'risk_label': f.risk_label,
            }
            if tab == 'returns':
                base.update({
                    'ret_1w': _flt(f.returns_1w_pct),
                    'ret_1m': _flt(f.returns_1m_pct),
                    'ret_3m': _flt(f.returns_3m_pct),
                    'ret_6m': _flt(f.returns_6m_pct),
                    'ret_1y': _flt(f.returns_1y_pct),
                    'ret_3y': _flt(f.returns_3y_pct),
                    'ret_5y': _flt(f.returns_5y_pct),
                    'rank_1y': f.rank_return_1y,
                    'rank_3y': f.rank_return_3y,
                    'rank_5y': f.rank_return_5y,
                    'q_ret_1y': f.quartile_return_1y,
                    'q_ret_3y': f.quartile_return_3y,
                    'q_ret_5y': f.quartile_return_5y,
                    'rolling': f.rolling_returns_json,
                    'calendar': f.calendar_returns_json,
                })
            elif tab == 'risk':
                base.update({
                    'volatility': _flt(f.volatility_3y_pct),
                    'sharpe': _flt(f.sharpe_ratio),
                    'sortino': _flt(f.sortino_ratio),
                    'max_drawdown': _flt(f.max_drawdown),
                    'alpha': _flt(f.excess_return_3y),
                    'q_vol': f.quartile_volatility,
                    'q_sharpe': f.quartile_sharpe,
                    'q_sortino': f.quartile_sortino,
                })
            elif tab == 'fees':
                base.update({
                    'expense': _flt(f.expense_ratio),
                    'aum': _flt(f.aum_cr),
                    'age': _flt(f.fund_age_years),
                    'benchmark': f.benchmark_name,
                })
            elif tab == 'portfolio':
                base.update({
                    'sectors': alloc_map.get(f.scheme_id, {})
                })
            data.append(base)

        return JsonResponse({'sub_category': sub_category, 'tab': tab, 'funds': data})
    except Exception as exc:
        logger.error('category_detail_funds_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


class ResearchQuartilesView(TemplateView):
    """
    Research > Quartile Rankings: Full standalone page with category filter.
    """
    template_name = 'research/quartile_rankings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx['all_sub_categories'] = list(
                FundScreenerSnapshot.objects
                .filter(is_direct=True)
                .exclude(scheme_sub_category='')
                .values('scheme_sub_category')
                .annotate(cnt=Count('id'))
                .order_by('scheme_sub_category')
                .values_list('scheme_sub_category', flat=True)
            )
            ctx['default_sub_cat'] = self.request.GET.get('cat', '')
            if not ctx['default_sub_cat'] and ctx['all_sub_categories']:
                ctx['default_sub_cat'] = ctx['all_sub_categories'][0]
        except Exception as exc:
            logger.warning('ResearchQuartilesView error: %s', exc)
            ctx['all_sub_categories'] = []
            ctx['default_sub_cat'] = ''
        return ctx


class ResearchTopFundsView(TemplateView):
    """
    Research > Top Performing Funds: Full basket tabs page.
    """
    template_name = 'research/top_funds.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from apps.funds.screener import TOP_FUND_BASKETS
            top_baskets = []
            for basket_name, basket_filter in TOP_FUND_BASKETS.items():
                funds = (
                    FundScreenerSnapshot.objects
                    .filter(is_direct=True, **basket_filter)
                    .exclude(returns_5y_pct=None)
                    .order_by('-returns_5y_pct')
                    .select_related('scheme')
                    [:20]  # Full page shows 20 vs 8 on home
                )
                if funds:
                    top_baskets.append({
                        'name': basket_name,
                        'slug': basket_name.lower().replace(' ', '-'),
                        'funds': list(funds),
                    })
            ctx['top_fund_baskets'] = top_baskets
        except Exception as exc:
            logger.warning('ResearchTopFundsView error: %s', exc)
            ctx['top_fund_baskets'] = []
        return ctx
