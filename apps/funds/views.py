"""
apps/funds/views.py — Core fund views
"""
import json
import logging
import csv
from datetime import date

from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Avg, Count, F, Q, Sum
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django_ratelimit.decorators import ratelimit


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
            dg_filter = Q(is_direct=True, plan='GROWTH') | Q(is_etf=True)
            total_dg = Scheme.objects.filter(dg_filter, is_active=True).count() or 1
            ctx['total_funds'] = total_dg or None
            ctx['fund_houses'] = Scheme.objects.values('fund_house').distinct().count() or None
            latest_nav = NAVHistory.objects.order_by('-date').first()
            ctx['last_nav_date'] = latest_nav.date.strftime('%d %b %Y') if latest_nav else None
            ctx['categories'] = (
                Scheme.objects.filter(dg_filter, is_active=True)
                .values('scheme_category')
                .annotate(count=Count('id'))
                .order_by('-count')[:18]
            )
            # ── Data status snapshot (for home page widget) ───────────────────
            try:
                from django.db.models import Max
                snap_count = FundScreenerSnapshot.objects.count()
                score_count = FundModelScore.objects.count()
                latest_snap_ts = FundScreenerSnapshot.objects.aggregate(m=Max('updated_at'))['m']
                ctx['data_status'] = {
                    'snap_count':    snap_count,
                    'snap_pct':      round(100 * snap_count / total_dg, 0),
                    'score_count':   score_count,
                    'score_pct':     round(100 * score_count / total_dg, 0),
                    'last_updated':  latest_snap_ts,
                }
            except Exception:
                ctx['data_status'] = None
        except Exception:
            ctx['total_funds'] = None
            ctx['fund_houses'] = None
            ctx['last_nav_date'] = None
            ctx['categories'] = []
            ctx['data_status'] = None

        # ── Section 1: Benchmark Returns Monitor ──────────────────────────────
        # Default 5 benchmarks for non-login & new users
        DEFAULT_BENCHMARK_NAMES = [
            'NIFTY 50', 'SENSEX', 'NIFTY MIDCAP 150',
            'NIFTY SMALLCAP 250', 'NIFTY SMLCAP 250', 'NIFTY 200',
        ]
        try:
            from apps.benchmarks.models import BenchmarkReturns, UserBenchmarkProfile
            all_bench = list(
                BenchmarkReturns.objects
                .select_related('index')
                .filter(index__is_active=True)
                .order_by('index__name')
            )
            ctx['all_benchmark_index_json'] = json.dumps([
                {'id': r.index_id, 'name': r.index.name} for r in all_bench
            ])
            default_set = [r for r in all_bench if r.index.name.upper() in DEFAULT_BENCHMARK_NAMES]
            if not default_set:
                default_set = all_bench[:5]

            if self.request.user.is_authenticated:
                profile = UserBenchmarkProfile.objects.filter(user=self.request.user).first()
                watchlist_ids = profile.watchlist if (profile and profile.watchlist) else []
                if watchlist_ids:
                    ctx['benchmark_returns'] = [r for r in all_bench if r.index_id in watchlist_ids]
                else:
                    ctx['benchmark_returns'] = default_set
                ctx['home_bench_watchlist_ids'] = json.dumps(watchlist_ids)
            else:
                ctx['benchmark_returns'] = default_set
                ctx['home_bench_watchlist_ids'] = '[]'
        except Exception as exc:
            logger.error("HomeView benchmark returns failed: %s", exc)
            ctx['benchmark_returns'] = []
            ctx['all_benchmark_index_json'] = '[]'
            ctx['home_bench_watchlist_ids'] = '[]'


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


        # ── Section 5: Browse counts per sub-category ─────────────────────────
        try:
            from apps.funds.screener import SUB_CATEGORY_PATTERNS
            sub_cat_counts = dict(
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True))
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
                .filter(Q(is_direct=True) | Q(is_etf=True))
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
                .filter(Q(is_direct=True) | Q(is_etf=True))
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
            .filter(Q(is_direct=True) | Q(is_etf=True), scheme_sub_category=sub_category)
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

    paginate_by = 100

    sort_options = {
        'name':      'fund_name',
        'aum':       'aum_cr',
        'expense':   'expense_ratio',
        'return_1y': 'returns_1y_pct',
        'cagr_3y':   'cagr_3y_pct',
        'volatility': 'volatility_3y_pct',
    }

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def filtered_queryset(self):
        request = self.request
        qs = FundScreenerSnapshot.objects.select_related('scheme').filter(Q(is_direct=True) | Q(is_etf=True))

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(fund_name__icontains=q)
                | Q(fund_house__icontains=q)
                | Q(scheme__amfi_code__icontains=q)
            )

        list_filters = {
            'house':          'fund_house__in',
            'category':       'category_group__in',
            'sub_category':   'scheme_sub_category__in',
            'risk':           'risk_label__in',
        }
        for param, lookup in list_filters.items():
            values = [v for v in request.GET.getlist(param) if v]
            if values:
                qs = qs.filter(**{lookup: values})

        range_filters = {
            'aum':       'aum_cr',
            'expense':   'expense_ratio',
            'return_1y': 'returns_1y_pct',
            'cagr_3y':   'cagr_3y_pct',
        }
        for param, field in range_filters.items():
            min_value = self.decimal_param(f'{param}_min')
            max_value = self.decimal_param(f'{param}_max')
            if min_value is not None:
                qs = qs.filter(**{f'{field}__gte': min_value})
            if max_value is not None:
                qs = qs.filter(**{f'{field}__lte': max_value})

        sort = request.GET.get('sort', 'aum')
        sort_field = self.sort_options.get(sort, 'aum_cr')
        direction = request.GET.get('direction', 'desc')
        if direction == 'desc':
            sort_field = f'-{sort_field}'
        
        return qs.order_by(sort_field, 'fund_name')

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

    def filter_options(self):
        base = FundScreenerSnapshot.objects.filter(Q(is_direct=True) | Q(is_etf=True))
        return {
            'houses':          self.distinct_values(base, 'fund_house'),
            'categories':      self.distinct_values(base, 'category_group'),
            'sub_categories':  self.distinct_values(base, 'scheme_sub_category'),
            'risks':           self.distinct_values(base, 'risk_label'),
        }

    def query_string_without(self, *keys):
        q = self.request.GET.copy()
        for k in keys:
            if k in q:
                del q[k]
        return q.urlencode()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.filtered_queryset()
        
        per_page = self.request.GET.get('per_page', str(self.paginate_by))
        if per_page == 'all':
            limit = max(qs.count(), 1)
        else:
            try:
                limit = int(per_page)
            except ValueError:
                limit = self.paginate_by
                
        paginator = Paginator(qs, limit)
        page_obj = paginator.get_page(self.request.GET.get('page'))

        selected = {
            'house': self.request.GET.getlist('house'),
            'category': self.request.GET.getlist('category'),
            'sub_category': self.request.GET.getlist('sub_category'),
            'risk': self.request.GET.getlist('risk'),
        }

        ctx.update({
            'page_obj':      page_obj,
            'snapshots':     page_obj.object_list,
            'total_count':   paginator.count,
            'filter_options': self.filter_options(),
            'selected':      selected,
            'last_updated':  (
                FundScreenerSnapshot.objects.order_by('-updated_at')
                .values_list('updated_at', flat=True)
                .first()
            ),
            'query_string':  self.query_string_without('page'),
        })
        return ctx


from django.contrib.auth.mixins import LoginRequiredMixin

class FundScreenerView(LoginRequiredMixin, TemplateView):
    template_name = 'funds/screener.html'
    paginate_by = 50

    sort_options = {
        # Scheme info
        'name':           'fund_name',
        'aum':            'aum_cr',
        'expense':        'expense_ratio',
        'age':            'fund_age_years',
        'nav':            'nav_latest',
        'model_score':    'model_score',
        # Returns
        'return_1m':      'returns_1m_pct',
        'return_3m':      'returns_3m_pct',
        'return_6m':      'returns_6m_pct',
        'return_1y':      'returns_1y_pct',
        'cagr_3y':        'cagr_3y_pct',
        'return_5y':      'returns_5y_pct',
        'cagr_7y':        'cagr_7y_pct',
        'cagr_10y':       'cagr_10y_pct',
        'cagr_si':        'cagr_si_pct',
        # Rolling returns
        'rolling_3y':     'rolling_return_3y_pct',
        'rolling_5y':     'rolling_return_5y_pct',
        # Risk
        'volatility_3y':  'volatility_3y_pct',
        'volatility_5y':  'volatility_5y_pct',
        'sharpe':         'sharpe_ratio',
        'sharpe_5y':      'sharpe_ratio_5y',
        'sortino':        'sortino_ratio',
        'sortino_5y':     'sortino_ratio_5y',
        'drawdown':       'max_drawdown',
        'drawdown_5y':    'max_drawdown_5y',
        'cur_drawdown':   'current_drawdown',
        'tracking_3y':    'tracking_error_3y',
        # Ratios
        'excess_1y':      'excess_return_1y',
        'excess_3y':      'excess_return_3y',
        'alpha_3y':       'alpha_3y',
        'alpha_5y':       'alpha_5y',
        'beta_3y':        'beta_3y',
        'info_ratio_3y':  'info_ratio_3y',
        'romad_3y':       'romad_3y',
        'upside_3y':      'upside_capture_3y',
        'downside_3y':    'downside_capture_3y',
        'volatility_1y':  'volatility_1y_pct',
        'volatility_7y':  'volatility_7y_pct',
        'volatility_si':  'volatility_si_pct',
        'drawdown_1y':    'max_drawdown_1y',
        'drawdown_si':    'max_drawdown_si',
        'sharpe_si':      'sharpe_ratio_si',
        'sortino_si':     'sortino_ratio_si',
        'romad_si':       'romad_si',
        'r_sq_si':        'r_squared_si',
        'alpha_si':       'alpha_si',
        'beta_si':        'beta_si',
        'upside_si':      'upside_capture_si',
        'downside_si':    'downside_capture_si',
        'info_ratio_si':  'info_ratio_si',
        'excess_cat_1y':  'excess_cat_1y',
        'excess_cat_3y':  'excess_cat_3y',
        'excess_cat_5y':  'excess_cat_5y',
        'excess_cat_7y':  'excess_cat_7y',
        'away_from_ath':  'away_from_ath_pct',
        'port_equity':    'port_equity_pct',
        'port_debt':      'port_debt_pct',
        'port_cash':      'port_cash_pct',
        'port_top3':      'port_top3_concentration',
        'port_top5':      'port_top5_concentration',
        'port_top10':     'port_top10_concentration',
        'cat_st_dev':     'category_st_dev',
        'updated':        'updated_at',
    }

    export_columns = [
        ('fund_name',            'Scheme Name'),
        ('fund_house',           'Fund House'),
        ('category_group',       'Scheme Category'),
        ('scheme_sub_category',  'Sub-category'),
        ('plan_type',            'Plan Type'),
        ('fund_manager',         'Fund Manager'),
        ('benchmark_name',       'Benchmark'),
        ('nav_latest',           'NAV'),
        ('aum_cr',               'AUM (Cr)'),
        ('expense_ratio',        'Expense Ratio (%)'),
        ('fund_age_years',       'Fund Age (Years)'),
        ('lock_in_days',         'Lock-in (Days)'),
        ('sip_min',              'Min SIP'),
        ('lump_min',             'Min Lumpsum'),
        ('sip_available',        'SIP Available'),
        ('crisil_rating',        'CRISIL Rating'),
        ('model_score',          'Model Score'),
        ('model_score_badge',    'Score Badge'),
        # Returns
        ('returns_1m_pct',       '1M Return (%)'),
        ('returns_3m_pct',       '3M Return (%)'),
        ('returns_6m_pct',       '6M Return (%)'),
        ('returns_1y_pct',       '1Y Return (%)'),
        ('cagr_3y_pct',          '3Y CAGR (%)'),
        ('returns_5y_pct',       '5Y Return (%)'),
        ('cagr_7y_pct',          '7Y CAGR (%)'),
        ('cagr_10y_pct',         '10Y CAGR (%)'),
        ('cagr_si_pct',          'Since-Inception CAGR (%)'),
        # Rolling
        ('rolling_return_3y_pct','3Y Avg Rolling Return (%)'),
        ('rolling_return_5y_pct','5Y Avg Rolling Return (%)'),
        # Risk
        ('volatility_3y_pct',    '3Y Volatility (%)'),
        ('volatility_5y_pct',    '5Y Volatility (%)'),
        ('sharpe_ratio',         '3Y Sharpe'),
        ('sharpe_ratio_5y',      '5Y Sharpe'),
        ('sortino_ratio',        '3Y Sortino'),
        ('sortino_ratio_5y',     '5Y Sortino'),
        ('max_drawdown',         '3Y Max Drawdown (%)'),
        ('max_drawdown_5y',      '5Y Max Drawdown (%)'),
        ('current_drawdown',     'Current Drawdown (%)'),
        ('tracking_error_3y',    '3Y Tracking Error (%)'),
        ('tracking_error_5y',    '5Y Tracking Error (%)'),
        ('volatility_1y_pct',    '1Y Volatility (%)'),
        ('volatility_7y_pct',    '7Y Volatility (%)'),
        ('volatility_si_pct',    'SI Volatility (%)'),
        ('max_drawdown_1y',      '1Y Max Drawdown (%)'),
        ('max_drawdown_si',      'SI Max Drawdown (%)'),
        ('sharpe_ratio_si',      'SI Sharpe'),
        ('sortino_ratio_si',     'SI Sortino'),
        ('romad_si',             'SI ROMAD'),
        ('r_squared_si',         'SI R-squared (%)'),
        ('alpha_si',             "SI Jensen's Alpha (%)"),
        ('beta_si',              'SI Beta'),
        ('info_ratio_si',        'SI Information Ratio'),
        ('upside_capture_si',    'SI Upside Capture (%)'),
        ('downside_capture_si',  'SI Downside Capture (%)'),
        ('excess_cat_1y',        '1Y Alpha vs Sub-Category (%)'),
        ('excess_cat_3y',        '3Y Alpha vs Sub-Category (%)'),
        ('excess_cat_5y',        '5Y Alpha vs Sub-Category (%)'),
        ('excess_cat_7y',        '7Y Alpha vs Sub-Category (%)'),
        ('away_from_ath_pct',    '% Away from ATH'),
        ('port_equity_pct',      'Equity Holding (%)'),
        ('port_debt_pct',        'Debt Holding (%)'),
        ('port_cash_pct',        'Cash Holding (%)'),
        ('port_top3_concentration','Top 3 Concentration (%)'),
        ('port_top5_concentration','Top 5 Concentration (%)'),
        ('port_top10_concentration','Top 10 Concentration (%)'),
        ('category_st_dev',      'Category Volatility (%)'),
        ('portfolio_turnover',   'Portfolio Turnover'),
        ('risk_label',           'Risk'),
        ('data_as_of',           'Data As Of'),
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
            'page_obj':      page_obj,
            'snapshots':     page_obj.object_list,
            'total_count':   paginator.count,
            'filter_options': self.filter_options(),
            'selected':      self.selected_filters(),
            'last_updated':  (
                FundScreenerSnapshot.objects.order_by('-updated_at')
                .values_list('updated_at', flat=True)
                .first()
            ),
            'query_string': self.query_string_without('page', 'export'),
        })
        return ctx

    def filtered_queryset(self):
        request = self.request
        # ── Base: Direct MFs and ETFs only ────────────────────────────────────
        qs = FundScreenerSnapshot.objects.select_related('scheme').filter(Q(is_direct=True) | Q(is_etf=True))

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(fund_name__icontains=q)
                | Q(fund_house__icontains=q)
                | Q(scheme__amfi_code__icontains=q)
                | Q(benchmark_name__icontains=q)
                | Q(fund_manager__icontains=q)
            )

        list_filters = {
            'house':          'fund_house__in',
            'category':       'category_group__in',
            'sub_category':   'scheme_sub_category__in',
            'plan_type':      'plan_type__in',
            'benchmark_type': 'benchmark_type__in',
            'benchmark':      'benchmark_name__in',
            'risk':           'risk_label__in',
            'score_badge':    'model_score_badge__in',
            'crisil':         'crisil_rating__in',
            'sip_available':  'sip_available',
        }
        for param, lookup in list_filters.items():
            if param == 'sip_available':
                val = request.GET.get(param)
                if val in ('true', '1'):
                    qs = qs.filter(sip_available=True)
                elif val in ('false', '0'):
                    qs = qs.filter(sip_available=False)
            else:
                values = [v for v in request.GET.getlist(param) if v]
                if values:
                    qs = qs.filter(**{lookup: values})

        range_filters = {
            # Scheme info
            'aum':           'aum_cr',
            'expense':       'expense_ratio',
            'age':           'fund_age_years',
            'nav':           'nav_latest',
            'sip_min':       'sip_min',
            'lump_min':      'lump_min',
            'lock_in':       'lock_in_days',
            'pturnover':     'portfolio_turnover',
            'model_score':   'model_score',
            # Returns
            'return_1m':     'returns_1m_pct',
            'return_3m':     'returns_3m_pct',
            'return_6m':     'returns_6m_pct',
            'return_1y':     'returns_1y_pct',
            'cagr_3y':       'cagr_3y_pct',
            'return_5y':     'returns_5y_pct',
            'cagr_7y':       'cagr_7y_pct',
            'cagr_10y':      'cagr_10y_pct',
            # Rolling returns
            'rolling_3y':    'rolling_return_3y_pct',
            'rolling_5y':    'rolling_return_5y_pct',
            # Risk
            'volatility_3y': 'volatility_3y_pct',
            'volatility_5y': 'volatility_5y_pct',
            'sharpe':        'sharpe_ratio',
            'sharpe_5y':     'sharpe_ratio_5y',
            'sortino':       'sortino_ratio',
            'sortino_5y':    'sortino_ratio_5y',
            'drawdown':      'max_drawdown',
            'drawdown_5y':   'max_drawdown_5y',
            'cur_drawdown':  'current_drawdown',
            'tracking_3y':   'tracking_error_3y',
            'tracking_5y':   'tracking_error_5y',
            # Ratios
            'excess_1y':     'excess_return_1y',
            'excess_3y':     'excess_return_3y',
            'alpha_3y':      'alpha_3y',
            'alpha_5y':      'alpha_5y',
            'beta_3y':       'beta_3y',
            'info_ratio_3y': 'info_ratio_3y',
            'romad_3y':      'romad_3y',
            'upside_3y':     'upside_capture_3y',
            'downside_3y':   'downside_capture_3y',
            'r_sq_3y':       'r_squared_3y',
            'volatility_1y': 'volatility_1y_pct',
            'volatility_7y': 'volatility_7y_pct',
            'volatility_si': 'volatility_si_pct',
            'drawdown_1y':   'max_drawdown_1y',
            'drawdown_si':   'max_drawdown_si',
            'sharpe_si':     'sharpe_ratio_si',
            'sortino_si':    'sortino_ratio_si',
            'romad_si':      'romad_si',
            'r_sq_si':       'r_squared_si',
            'alpha_si':      'alpha_si',
            'beta_si':       'beta_si',
            'upside_si':     'upside_capture_si',
            'downside_si':   'downside_capture_si',
            'info_ratio_si': 'info_ratio_si',
            'excess_cat_1y': 'excess_cat_1y',
            'excess_cat_3y': 'excess_cat_3y',
            'excess_cat_5y': 'excess_cat_5y',
            'excess_cat_7y': 'excess_cat_7y',
            'away_from_ath': 'away_from_ath_pct',
            'port_equity':   'port_equity_pct',
            'port_debt':     'port_debt_pct',
            'port_cash':     'port_cash_pct',
            'port_top3':     'port_top3_concentration',
            'port_top5':     'port_top5_concentration',
            'port_top10':    'port_top10_concentration',
            'cat_st_dev':    'category_st_dev',
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
        base = FundScreenerSnapshot.objects.filter(Q(is_direct=True) | Q(is_etf=True))
        return {
            'houses':          self.distinct_values(base, 'fund_house'),
            'categories':      self.distinct_values(base, 'category_group'),
            'sub_categories':  self.distinct_values(base, 'scheme_sub_category'),
            'plan_types':      self.distinct_values(base, 'plan_type'),
            'benchmark_types': self.distinct_values(base, 'benchmark_type'),
            'benchmarks':      self.distinct_values(base, 'benchmark_name') or benchmark_options(),
            'risks':           self.distinct_values(base, 'risk_label'),
            'score_badges':    [b for b in ['Strong', 'Good', 'Fair', 'Weak', 'Poor'] if
                                base.filter(model_score_badge=b).exists()],
            'crisil_options':  self.distinct_values(base, 'crisil_rating'),
        }

    def selected_filters(self):
        g = self.request.GET
        keys = [
            # list filters
            'house', 'category', 'sub_category', 'plan_type', 'benchmark_type',
            'benchmark', 'risk', 'score_badge', 'crisil', 'sip_available',
            # range params (all _min/_max pairs)
            'aum_min', 'aum_max', 'expense_min', 'expense_max',
            'age_min', 'age_max', 'nav_min', 'nav_max',
            'sip_min_min', 'sip_min_max', 'lump_min_min', 'lump_min_max',
            'lock_in_min', 'lock_in_max', 'pturnover_min', 'pturnover_max',
            'model_score_min', 'model_score_max',
            'return_1m_min', 'return_1m_max', 'return_3m_min', 'return_3m_max',
            'return_6m_min', 'return_6m_max', 'return_1y_min', 'return_1y_max',
            'cagr_3y_min', 'cagr_3y_max', 'return_5y_min', 'return_5y_max',
            'cagr_7y_min', 'cagr_7y_max', 'cagr_10y_min', 'cagr_10y_max',
            'rolling_3y_min', 'rolling_3y_max', 'rolling_5y_min', 'rolling_5y_max',
            'volatility_3y_min', 'volatility_3y_max', 'volatility_5y_min', 'volatility_5y_max',
            'sharpe_min', 'sharpe_max', 'sharpe_5y_min', 'sharpe_5y_max',
            'sortino_min', 'sortino_max', 'sortino_5y_min', 'sortino_5y_max',
            'drawdown_min', 'drawdown_max', 'drawdown_5y_min', 'drawdown_5y_max',
            'cur_drawdown_min', 'cur_drawdown_max',
            'tracking_3y_min', 'tracking_3y_max', 'tracking_5y_min', 'tracking_5y_max',
            'excess_1y_min', 'excess_1y_max', 'excess_3y_min', 'excess_3y_max',
            'alpha_3y_min', 'alpha_3y_max', 'alpha_5y_min', 'alpha_5y_max',
            'beta_3y_min', 'beta_3y_max', 'info_ratio_3y_min', 'info_ratio_3y_max',
            'romad_3y_min', 'romad_3y_max',
            'upside_3y_min', 'upside_3y_max', 'downside_3y_min', 'downside_3y_max',
            'r_sq_3y_min', 'r_sq_3y_max',
            'volatility_1y_min', 'volatility_1y_max', 'volatility_7y_min', 'volatility_7y_max',
            'volatility_si_min', 'volatility_si_max', 'drawdown_1y_min', 'drawdown_1y_max',
            'drawdown_si_min', 'drawdown_si_max', 'sharpe_si_min', 'sharpe_si_max',
            'sortino_si_min', 'sortino_si_max', 'romad_si_min', 'romad_si_max',
            'r_sq_si_min', 'r_sq_si_max', 'alpha_si_min', 'alpha_si_max',
            'beta_si_min', 'beta_si_max', 'upside_si_min', 'upside_si_max',
            'downside_si_min', 'downside_si_max', 'info_ratio_si_min', 'info_ratio_si_max',
            'excess_cat_1y_min', 'excess_cat_1y_max', 'excess_cat_3y_min', 'excess_cat_3y_max',
            'excess_cat_5y_min', 'excess_cat_5y_max', 'excess_cat_7y_min', 'excess_cat_7y_max',
            'away_from_ath_min', 'away_from_ath_max', 'port_equity_min', 'port_equity_max',
            'port_debt_min', 'port_debt_max', 'port_cash_min', 'port_cash_max',
            'port_top3_min', 'port_top3_max', 'port_top5_min', 'port_top5_max',
            'port_top10_min', 'port_top10_max', 'cat_st_dev_min', 'cat_st_dev_max',
        ]
        sel = {'sort': g.get('sort', 'name'), 'direction': g.get('direction', 'asc'), 'q': g.get('q', '')}
        for k in keys:
            if k in ('house', 'category', 'sub_category', 'plan_type', 'benchmark_type',
                     'benchmark', 'risk', 'score_badge', 'crisil'):
                sel[k] = g.getlist(k)
            else:
                sel[k] = g.get(k, '')
        return sel

    def export_csv(self, qs):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="fund-screener.csv"'
        writer = csv.writer(response)
        writer.writerow([label for _, label in self.export_columns])
        for row in qs[:5000]:
            writer.writerow([getattr(row, field, '') for field, _ in self.export_columns])
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
            'crisis_periods': getattr(runtime, 'crisis_periods', []),
            'market_regimes': getattr(runtime, 'market_regimes', []),
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

        # ── Category Average & Min/Max lookup ────────────────────────────────
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

        # Enrich trailing returns with category min, avg, max and excess metrics
        class EnrichedTrailingReturn:
            def __init__(self, original, cat_snap):
                self._o = original
                period = getattr(original, 'period', '')
                cagr = _flt(getattr(original, 'cagr_pct', None))
                bm_cagr = _flt(getattr(original, 'bm_cagr', None))
                if bm_cagr is None:
                    bm_cagr = _flt(getattr(original, 'bm_cagr_pct', None))
                
                cat_min = cat_avg = cat_max = None
                if cat_snap:
                    if period == '1Y':
                        cat_min = _flt(getattr(cat_snap, 'min_return_1y', None))
                        cat_avg = _flt(getattr(cat_snap, 'avg_return_1y', None))
                        cat_max = _flt(getattr(cat_snap, 'max_return_1y', None))
                    elif period == '3Y':
                        cat_min = _flt(getattr(cat_snap, 'min_return_3y', None))
                        cat_avg = _flt(getattr(cat_snap, 'avg_return_3y', None))
                        cat_max = _flt(getattr(cat_snap, 'max_return_3y', None))
                    elif period == '5Y':
                        cat_min = _flt(getattr(cat_snap, 'min_return_5y', None))
                        cat_avg = _flt(getattr(cat_snap, 'avg_return_5y', None))
                        cat_max = _flt(getattr(cat_snap, 'max_return_5y', None))

                self.cat_min = cat_min
                self.cat_avg = cat_avg
                self.cat_max = cat_max

                orig_excess = _flt(getattr(original, 'excess', None))
                if orig_excess is None:
                    orig_excess = _flt(getattr(original, 'excess_cagr', None))

                calc_excess = (cagr - bm_cagr) if (cagr is not None and bm_cagr is not None) else orig_excess
                self.excess_bm = calc_excess
                self.excess = calc_excess
                self.excess_cat = (cagr - cat_avg) if (cagr is not None and cat_avg is not None) else None

            def __getattr__(self, name):
                return getattr(self._o, name)

        if ctx.get('trailing_returns'):
            cat_snap = ctx.get('category_snap')
            ctx['trailing_returns'] = [
                EnrichedTrailingReturn(r, cat_snap) for r in ctx['trailing_returns']
            ]

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


@ratelimit(key='ip', rate='1/m', method='GET', block=True)
def export_pdf_view(request, amfi_code):
    """Generate Chrome-headless PDF fund report for the given AMFI scheme code."""
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

            DEFAULT_BENCHMARK_NAMES = [
                'NIFTY 50', 'SENSEX', 'NIFTY MIDCAP 150',
                'NIFTY SMALLCAP 250', 'NIFTY SMLCAP 250', 'NIFTY 200',
            ]
            default_set = [r for r in all_returns if r.index.name.upper() in DEFAULT_BENCHMARK_NAMES]
            if not default_set:
                default_set = all_returns[:5]

            # User watchlist
            watchlist_ids = []
            if self.request.user.is_authenticated:
                profile = UserBenchmarkProfile.objects.filter(user=self.request.user).first()
                if profile and profile.watchlist:
                    watchlist_ids = profile.watchlist

            # If user has a watchlist, filter to those; else default to 5 curated benchmarks
            if watchlist_ids:
                ctx['selected_returns'] = [
                    r for r in all_returns if r.index_id in watchlist_ids
                ]
            else:
                ctx['selected_returns'] = default_set

                
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
                .filter(Q(is_direct=True) | Q(is_etf=True), scheme_sub_category=sub_category)
                .select_related('scheme')
                .order_by(F('rank_return_1y').asc(nulls_last=True), F('aum_cr').desc(nulls_last=True), 'fund_name')
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
            
            # All categories with pre-computed slugs for the dropdown menu
            all_snaps = CategorySnapshot.objects.order_by('category_group', 'scheme_sub_category').values('scheme_sub_category', 'fund_count', 'category_group')
            all_categories = []
            for snap_dict in all_snaps:
                all_categories.append({
                    'scheme_sub_category': snap_dict['scheme_sub_category'],
                    'fund_count': snap_dict['fund_count'],
                    'category_group': snap_dict['category_group'],
                    'slug': _make_slug(snap_dict['scheme_sub_category'])
                })
            ctx['all_categories'] = all_categories
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
            .filter(Q(is_direct=True) | Q(is_etf=True), scheme_sub_category=sub_category)
            .select_related('scheme')
            .order_by(F('rank_return_1y').asc(nulls_last=True), F('aum_cr').desc(nulls_last=True), 'fund_name')
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
        total_funds = len(funds)
        for f in funds:
            score = score_map.get(f.scheme_id)
            badge = badge_map.get(f.scheme_id, '')
            amfi = f.scheme.amfi_code if f.scheme else ''
            base = {
                'amfi': amfi,
                'amfi_code': amfi,
                'name': f.fund_name,
                'fund_name': f.fund_name,
                'house': f.fund_house,
                'fund_house': f.fund_house,
                'is_etf': f.is_etf,
                'score': score,
                'badge': badge or f.model_score_badge or 'N/A',
                'total': f.rank_count_in_cat or total_funds,
                'rank_1y': f.rank_return_1y,
                'rank_3y': f.rank_return_3y,
                'rank_5y': f.rank_return_5y,
                'returns_1y': _flt(f.returns_1y_pct),
                'returns_3y': _flt(f.cagr_3y_pct),
                'returns_5y': _flt(f.returns_5y_pct),
                'ret_1y': _flt(f.returns_1y_pct),
                'ret_3y': _flt(f.cagr_3y_pct),
                'ret_5y': _flt(f.returns_5y_pct),
                'sharpe': _flt(f.sharpe_ratio),
                'sortino': _flt(f.sortino_ratio),
                'alpha': _flt(f.alpha_3y),
                'beta': _flt(f.beta_3y),
                'volatility': _flt(f.volatility_3y_pct or f.volatility_1y_pct),
                'max_drawdown': _flt(f.max_drawdown),
                'aum': _flt(f.aum_cr),
                'expense': _flt(f.expense_ratio),
                'age': _flt(f.fund_age_years),
                'risk_label': f.risk_label,
                'info_ratio': _flt(f.info_ratio_3y),
                'upside_capture': _flt(f.upside_capture_3y),
                'downside_capture': _flt(f.downside_capture_3y),
                'excess_cat_1y': _flt(f.excess_cat_1y),
                'excess_cat_3y': _flt(f.excess_cat_3y),
                'excess_cat_5y': _flt(f.excess_cat_5y),
                'turnover': _flt(f.portfolio_turnover),
                'benchmark': f.benchmark_name or '',
                'manager': f.fund_manager or '',
            }
            if tab == 'returns':
                base.update({
                    'ret_1w': _flt(f.returns_1w_pct),
                    'ret_1m': _flt(f.returns_1m_pct),
                    'ret_3m': _flt(f.returns_3m_pct),
                    'ret_6m': _flt(f.returns_6m_pct),
                    'ret_2y': _flt(getattr(f, 'cagr_2y_pct', None)),
                    'ret_7y': _flt(f.cagr_7y_pct),
                    'ret_10y': _flt(f.cagr_10y_pct),
                    'q_ret_1y': f.quartile_return_1y,
                    'q_ret_3y': f.quartile_return_3y,
                    'q_ret_5y': f.quartile_return_5y,
                    'rolling': f.rolling_returns_json,
                    'calendar': f.calendar_returns_json,
                })
            elif tab == 'risk':
                base.update({
                    'tracking_error': _flt(f.tracking_error_3y),
                    'q_vol': f.quartile_volatility,
                    'q_sharpe': f.quartile_sharpe,
                    'q_sortino': f.quartile_sortino,
                })
            elif tab == 'fees':
                base.update({
                    'sip_min': _flt(f.sip_min),
                    'lump_min': _flt(f.lump_min),
                })
            elif tab == 'portfolio':
                base.update({
                    'sectors': alloc_map.get(f.scheme_id, {}),
                    'top10_conc': _flt(f.port_top10_concentration),
                    'top5_conc': _flt(f.port_top5_concentration),
                })
            elif tab == 'intelligence':
                base.update({
                    'rolling': f.rolling_returns_json,
                })
            data.append(base)

        return JsonResponse({'sub_category': sub_category, 'tab': tab, 'funds': data})
    except Exception as exc:
        logger.error('category_detail_funds_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


class ResearchQuartilesView(LoginRequiredMixin, TemplateView):
    """
    Research > Quartile Rankings: Full standalone page with dynamic on-the-fly
    quartile computation. No stored quartile data — all calculated from
    FundScreenerSnapshot on request.
    Requires login.
    """

    template_name = 'research/quartile_rankings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            # Category groups and sub-categories for filter dropdowns
            all_sub_cats = list(
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True))
                .exclude(scheme_sub_category='')
                .values_list('scheme_sub_category', flat=True)
                .distinct()
                .order_by('scheme_sub_category')
            )
            # Build grouped structure: {category_group: [sub_cat, ...]}
            cat_group_map = {}
            for row in (
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True))
                .exclude(scheme_sub_category='')
                .values('category_group', 'scheme_sub_category')
                .distinct()
                .order_by('category_group', 'scheme_sub_category')
            ):
                cat_group_map.setdefault(row['category_group'], []).append(row['scheme_sub_category'])

            ctx['all_sub_categories'] = all_sub_cats
            ctx['cat_group_map'] = cat_group_map
            ctx['category_groups'] = sorted(cat_group_map.keys())
            ctx['default_sub_cat'] = self.request.GET.get('sub_category', '')
            ctx['default_category'] = self.request.GET.get('category', '')
            ctx['default_metric_group'] = self.request.GET.get('metric_group', 'returns')
            if not ctx['default_sub_cat'] and all_sub_cats:
                ctx['default_sub_cat'] = all_sub_cats[0]
        except Exception as exc:
            logger.warning('ResearchQuartilesView error: %s', exc)
            ctx['all_sub_categories'] = []
            ctx['cat_group_map'] = {}
            ctx['category_groups'] = []
            ctx['default_sub_cat'] = ''
            ctx['default_category'] = ''
            ctx['default_metric_group'] = 'returns'
        return ctx


# ── Metric definitions for on-the-fly quartile computation ──────────────────
QUARTILE_METRIC_GROUPS = {
    'returns': [
        {'key': 'cagr_1y',   'label': '1Y CAGR',          'field': 'returns_1y_pct',      'higher_is_better': True,
         'tooltip': 'Compound Annual Growth Rate over 1 year within this sub-category.'},
        {'key': 'cagr_3y',   'label': '3Y CAGR',          'field': 'cagr_3y_pct',         'higher_is_better': True,
         'tooltip': 'Compound Annual Growth Rate over 3 years within this sub-category.'},
        {'key': 'cagr_5y',   'label': '5Y CAGR',          'field': 'returns_5y_pct',      'higher_is_better': True,
         'tooltip': 'Compound Annual Growth Rate over 5 years within this sub-category.'},
        {'key': 'rolling_3y','label': '3Y Avg Rolling',   'field': 'rolling_return_3y_pct','higher_is_better': True,
         'tooltip': 'Average of all 3-year rolling return windows. Reflects consistency over time.'},
        {'key': 'rolling_5y','label': '5Y Avg Rolling',   'field': 'rolling_return_5y_pct','higher_is_better': True,
         'tooltip': 'Average of all 5-year rolling return windows. Reflects long-term consistency.'},
    ],
    'volatility': [
        {'key': 'vol_1y',    'label': '1Y Volatility',    'field': 'volatility_1y_pct',   'higher_is_better': False,
         'tooltip': 'Standard deviation of daily returns annualised over 1 year. Lower is better.'},
        {'key': 'vol_5y',    'label': '5Y Volatility',    'field': 'volatility_5y_pct',   'higher_is_better': False,
         'tooltip': 'Standard deviation of daily returns annualised over 5 years. Lower is better.'},
        {'key': 'te_3y',     'label': '3Y Tracking Error','field': 'tracking_error_3y',   'higher_is_better': False,
         'tooltip': 'Annualised deviation of fund returns from benchmark returns over 3 years. For index funds, lower is better.'},
        {'key': 'dd_1y',     'label': '1Y Max Drawdown',  'field': 'max_drawdown_1y',     'higher_is_better': False,
         'tooltip': 'Maximum peak-to-trough decline over 1 year. A less negative number is better.'},
        {'key': 'dd_5y',     'label': '5Y Max Drawdown',  'field': 'max_drawdown_5y',     'higher_is_better': False,
         'tooltip': 'Maximum peak-to-trough decline over 5 years. A less negative number is better.'},
        {'key': 'dd_si',     'label': 'SI Max Drawdown',  'field': 'max_drawdown_si',     'higher_is_better': False,
         'tooltip': 'Maximum peak-to-trough decline since inception. A less negative number is better.'},
    ],
    'ratios': [
        {'key': 'sharpe',    'label': 'Sharpe (3Y)',       'field': 'sharpe_ratio',        'higher_is_better': True,
         'tooltip': 'Return per unit of total risk (3Y). Higher is better. Ratio > 1 is generally good.'},
        {'key': 'sortino',   'label': 'Sortino (3Y)',      'field': 'sortino_ratio',       'higher_is_better': True,
         'tooltip': 'Return per unit of downside risk (3Y). Higher is better. Preferred over Sharpe for equities.'},
        {'key': 'alpha',     'label': 'Alpha (3Y)',        'field': 'alpha_3y',            'higher_is_better': True,
         'tooltip': "Jensen's Alpha over 3Y: excess annualised return above what CAPM would predict. Higher is better."},
        {'key': 'beta',      'label': 'Beta (3Y)',         'field': 'beta_3y',             'higher_is_better': None,
         'tooltip': 'Sensitivity to benchmark movements (3Y). Beta=1 moves with market. <1 is defensive, >1 is aggressive. No universal "better" direction.'},
        {'key': 'info_ratio','label': 'Info Ratio (3Y)',   'field': 'info_ratio_3y',       'higher_is_better': True,
         'tooltip': 'Excess return over benchmark per unit of tracking error (3Y). Higher is better.'},
        {'key': 'upside',    'label': 'Upside Capture',   'field': 'upside_capture_3y',   'higher_is_better': True,
         'tooltip': '% of benchmark upside the fund captures (3Y). Higher is better — captures more gains.'},
        {'key': 'downside',  'label': 'Downside Capture', 'field': 'downside_capture_3y', 'higher_is_better': False,
         'tooltip': '% of benchmark downside the fund captures (3Y). Lower is better — less loss in down markets.'},
    ],
}


def _compute_quartile(value, all_values, higher_is_better):
    """
    Compute 1-indexed quartile (Q1=best, Q4=worst) for a value among all_values.
    Returns (quartile, rank, total) or (None, None, total) if value is None.
    """
    valid = [v for v in all_values if v is not None]
    total = len(valid)
    if value is None or total == 0:
        return None, None, total
    if higher_is_better is None:
        # No ranking (e.g. Beta) — just return total
        return None, None, total
    # Sort: best first
    sorted_vals = sorted(valid, reverse=bool(higher_is_better))
    try:
        rank = sorted_vals.index(float(value)) + 1
    except ValueError:
        # Handle float precision: find nearest
        fv = float(value)
        rank = min(range(len(sorted_vals)), key=lambda i: abs(sorted_vals[i] - fv)) + 1
    # Q1=top 25%, Q4=bottom 25%
    import math
    quartile = min(4, math.ceil(rank / (total / 4))) if total > 0 else None
    return quartile, rank, total


@login_required
def quartile_rankings_api(request):
    """
    AJAX endpoint: GET /research/quartiles/api/
    Params: sub_category, metric_group (returns/volatility/ratios), q (search), sort, direction, page
    Returns JSON with funds + on-the-fly quartile data.

    Quartile ranks are ALWAYS computed against the full sub-category cohort,
    even when a search filter is active. Search only filters which rows are displayed.
    """

    sub_category = request.GET.get('sub_category', '').strip()
    metric_group = request.GET.get('metric_group', 'returns')
    q = request.GET.get('q', '').strip()
    sort_key = request.GET.get('sort', '')
    direction = request.GET.get('direction', 'asc')
    page_num = int(request.GET.get('page', 1))
    per_page = 50

    if not sub_category:
        return JsonResponse({'error': 'sub_category required'}, status=400)

    metrics = QUARTILE_METRIC_GROUPS.get(metric_group, QUARTILE_METRIC_GROUPS['returns'])

    try:
        # Always fetch ALL funds in sub-category for accurate quartile computation
        all_funds = list(
            FundScreenerSnapshot.objects
            .filter(Q(is_direct=True) | Q(is_etf=True), scheme_sub_category=sub_category)
            .select_related('scheme')
            .order_by('fund_name')
        )

        # Pre-gather all values per metric from full cohort (for correct quartile ranks)
        metric_all_values = {}
        for m in metrics:
            metric_all_values[m['key']] = [
                _flt(getattr(f, m['field'])) for f in all_funds
            ]

        # Build rows with quartile data (using full cohort ranks)
        all_rows = []
        for f in all_funds:
            row = {
                'name': f.fund_name,
                'house': f.fund_house,
                'amfi': f.scheme.amfi_code,
                'metrics': {},
            }
            for m in metrics:
                val = _flt(getattr(f, m['field']))
                q_num, rank, total = _compute_quartile(
                    val, metric_all_values[m['key']], m['higher_is_better']
                )
                row['metrics'][m['key']] = {
                    'value': val,
                    'quartile': q_num,
                    'rank': rank,
                    'total': total,
                }
            all_rows.append(row)

        # Apply search filter to display rows only (ranks unchanged)
        if q:
            q_lower = q.lower()
            rows = [r for r in all_rows if q_lower in r['name'].lower() or q_lower in r['house'].lower()]
        else:
            rows = all_rows

        total_count = len(rows)

        # Sort by selected metric
        if sort_key and sort_key in {m['key'] for m in metrics}:
            rows = sorted(
                rows,
                key=lambda r: (r['metrics'][sort_key]['value'] is None,
                               r['metrics'][sort_key]['value'] or 0),
                reverse=(direction == 'desc')
            )
        elif sort_key == 'name':
            rows = sorted(rows, key=lambda r: r['name'], reverse=(direction == 'desc'))

        # Paginate
        import math
        total_pages = max(1, math.ceil(total_count / per_page))
        page_num = max(1, min(page_num, total_pages))
        start = (page_num - 1) * per_page
        page_rows = rows[start:start + per_page]

        return JsonResponse({
            'funds': page_rows,
            'total_count': total_count,
            'cohort_size': len(all_funds),
            'page': page_num,
            'total_pages': total_pages,
            'per_page': per_page,
            'metric_group': metric_group,
            'metrics': [{'key': m['key'], 'label': m['label'],
                         'higher_is_better': m['higher_is_better'],
                         'tooltip': m['tooltip']} for m in metrics],
        })
    except Exception as exc:
        logger.error('quartile_rankings_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)

# ── AMC Analysis ─────────────────────────────────────────────────────────────

def _flt(v, decimals=2):
    """Return a rounded float or None, safe for JSON serialization."""
    if v is None:
        return None
    try:
        return round(float(v), decimals)
    except (TypeError, ValueError):
        return None


def _make_amc_slug(fund_house: str) -> str:
    """Convert fund_house name to a URL-safe slug."""
    return (
        fund_house.lower()
        .replace("'", '')
        .replace(' ', '-')
        .replace('/', '-')
        .replace('&', 'and')
        .replace('--', '-')
        .strip('-')
    )


def _slug_to_fund_house(slug: str) -> str:
    """Resolve a slug back to the exact fund_house string in the DB."""
    all_houses = list(
        FundScreenerSnapshot.objects
        .values_list('fund_house', flat=True)
        .distinct()
    )
    for house in all_houses:
        if _make_amc_slug(house) == slug:
            return house
    # Fallback: partial match
    normalized = slug.replace('-', ' ')
    for house in all_houses:
        if house.lower() == normalized:
            return house
    return ''


def _compute_amc_metrics(fund_house: str) -> dict:
    """
    Compute all available metrics for one AMC from FundScreenerSnapshot,
    SchemeMeta, Holding, and SectorAllocation tables.
    Returns a dict of metrics; None values where data is unavailable.
    """
    direct_q = Q(fund_house=fund_house) & (Q(is_direct=True) | Q(is_etf=True))

    # ── Base aggregates ────────────────────────────────────────────────────
    agg = FundScreenerSnapshot.objects.filter(direct_q).aggregate(
        total_aum=Sum('aum_cr'),
        fund_count=Count('id'),
        active_count=Count('id', filter=Q(is_etf=False, fund_house=fund_house)),
        etf_count=Count('id', filter=Q(is_etf=True, fund_house=fund_house)),
        avg_return_1y=Avg('returns_1y_pct'),
        avg_return_3y=Avg('cagr_3y_pct'),
        avg_return_5y=Avg('returns_5y_pct'),
        avg_return_7y=Avg('cagr_7y_pct'),
        avg_expense_ratio=Avg('expense_ratio'),
        avg_model_score=Avg('model_score'),
        avg_alpha_3y=Avg('alpha_3y'),
        avg_sharpe=Avg('sharpe_ratio'),
        avg_sortino=Avg('sortino_ratio'),
        avg_max_drawdown=Avg('max_drawdown'),
        avg_turnover=Avg('portfolio_turnover'),
        cat_count=Count('scheme_sub_category', distinct=True),
    )

    # ── Score distribution ─────────────────────────────────────────────────
    score_rows = list(
        FundScreenerSnapshot.objects.filter(direct_q, model_score__isnull=False)
        .values_list('model_score', flat=True)
    )
    total_scored = len(score_rows)
    pct_strong = pct_good = pct_fair = pct_weak = None
    if total_scored:
        pct_strong = round(sum(1 for s in score_rows if s >= 75) / total_scored * 100, 1)
        pct_good   = round(sum(1 for s in score_rows if 55 <= s < 75) / total_scored * 100, 1)
        pct_fair   = round(sum(1 for s in score_rows if 40 <= s < 55) / total_scored * 100, 1)
        pct_weak   = round(sum(1 for s in score_rows if s < 40) / total_scored * 100, 1)

    # ── Category breadth ──────────────────────────────────────────────────
    categories = list(
        FundScreenerSnapshot.objects.filter(direct_q)
        .values_list('scheme_sub_category', flat=True)
        .distinct()
        .order_by('scheme_sub_category')
    )

    # ── Fund managers ──────────────────────────────────────────────────────
    manager_text_list = list(
        SchemeMeta.objects.filter(scheme__fund_house=fund_house, scheme__is_active=True)
        .values_list('fund_manager', flat=True)
    )
    all_managers: set[str] = set()
    for text in manager_text_list:
        if text:
            for m in text.split(';'):
                m = m.strip()
                if m:
                    all_managers.add(m)
    unique_manager_count = len(all_managers)

    # ── Portfolio Intelligence from Holding table ──────────────────────────
    scheme_ids = list(
        Scheme.objects.filter(fund_house=fund_house, is_active=True).values_list('id', flat=True)
    )
    has_holdings = False
    high_conviction_stocks = []
    sector_data = []
    unique_stock_count = 0

    try:
        from apps.holdings.models import Holding, SectorAllocation

        # Latest month for this AMC
        latest_month = (
            Holding.objects.filter(scheme_id__in=scheme_ids)
            .order_by('-as_of_month')
            .values_list('as_of_month', flat=True)
            .first()
        )
        if latest_month:
            has_holdings = True
            # High-conviction: equity stocks held across 3+ funds
            hc = list(
                Holding.objects.filter(
                    scheme_id__in=scheme_ids,
                    as_of_month=latest_month,
                    holding_type='equity',
                ).values('security_name', 'isin').annotate(
                    fund_count=Count('scheme_id', distinct=True),
                    total_value=Sum('market_value'),
                    avg_weight=Avg('weight_pct'),
                ).filter(fund_count__gte=3).order_by('-fund_count', '-total_value')[:20]
            )
            high_conviction_stocks = [
                {
                    'name': h['security_name'],
                    'isin': h['isin'],
                    'fund_count': h['fund_count'],
                    'total_value': float(h['total_value']) if h['total_value'] else None,
                    'avg_weight': float(h['avg_weight']) if h['avg_weight'] else None,
                }
                for h in hc
            ]

            # Sector exposure across all funds (avg weight per sector, fund count)
            sec = list(
                SectorAllocation.objects.filter(
                    scheme_id__in=scheme_ids,
                    as_of_month=latest_month,
                ).values('sector').annotate(
                    avg_weight=Avg('weight_pct'),
                    fund_count=Count('scheme_id', distinct=True),
                ).order_by('-avg_weight')[:12]
            )
            sector_data = [
                {
                    'sector': s['sector'],
                    'avg_weight': float(s['avg_weight']) if s['avg_weight'] else 0,
                    'fund_count': s['fund_count'],
                }
                for s in sec
            ]

            # Unique stock count
            unique_stock_count = (
                Holding.objects.filter(
                    scheme_id__in=scheme_ids,
                    as_of_month=latest_month,
                    holding_type='equity',
                ).values('security_name').distinct().count()
            )
    except Exception as e:
        pass
    return {
        'fund_house': fund_house,
        'slug': _make_amc_slug(fund_house),
        'total_aum': float(agg['total_aum']) if agg['total_aum'] else None,
        'fund_count': agg['fund_count'] or 0,
        'active_count': agg['active_count'] or 0,
        'etf_count': agg['etf_count'] or 0,
        'avg_return_1y': _flt(agg['avg_return_1y']),
        'avg_return_3y': _flt(agg['avg_return_3y']),
        'avg_return_5y': _flt(agg['avg_return_5y']),
        'avg_return_7y': _flt(agg['avg_return_7y']),
        'avg_expense_ratio': _flt(agg['avg_expense_ratio']),
        'avg_model_score': _flt(agg['avg_model_score']),
        'avg_alpha_3y': _flt(agg['avg_alpha_3y']),
        'avg_sharpe': _flt(agg['avg_sharpe']),
        'avg_sortino': _flt(agg['avg_sortino']),
        'avg_max_drawdown': _flt(agg['avg_max_drawdown']),
        'avg_turnover': _flt(agg['avg_turnover']),
        'cat_count': agg['cat_count'] or 0,
        'categories': categories,
        'pct_strong': pct_strong,
        'pct_good': pct_good,
        'pct_fair': pct_fair,
        'pct_weak': pct_weak,
        'total_scored': total_scored,
        'unique_manager_count': unique_manager_count,
        'managers': sorted(all_managers),
        'has_holdings': has_holdings,
        'high_conviction_stocks': high_conviction_stocks,
        'sector_data': sector_data,
        'unique_stock_count': unique_stock_count,
    }


class ResearchAMCListView(LoginRequiredMixin, TemplateView):
    """
    Research > AMC Analysis: Browse all fund houses with key metrics.
    Supports multi-select comparison (2-4 AMCs).
    Requires login.
    """
    template_name = 'research/amcs.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            # Get distinct fund houses with basic aggregate for quick page load
            houses = list(
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True))
                .values('fund_house')
                .annotate(
                    total_aum=Sum('aum_cr'),
                    fund_count=Count('id'),
                    avg_return_3y=Avg('cagr_3y_pct'),
                    avg_expense_ratio=Avg('expense_ratio'),
                    avg_model_score=Avg('model_score'),
                    cat_count=Count('scheme_sub_category', distinct=True),
                    etf_count=Count('id', filter=Q(is_etf=True)),
                )
                .order_by('-total_aum')
            )
            amc_list = []
            for h in houses:
                name = h['fund_house']
                amc_list.append({
                    'name': name,
                    'slug': _make_amc_slug(name),
                    'total_aum': round(float(h['total_aum']), 0) if h['total_aum'] else None,
                    'fund_count': h['fund_count'],
                    'etf_count': h['etf_count'] or 0,
                    'active_count': (h['fund_count'] or 0) - (h['etf_count'] or 0),
                    'avg_return_3y': _flt(h['avg_return_3y']),
                    'avg_expense_ratio': _flt(h['avg_expense_ratio']),
                    'avg_model_score': _flt(h['avg_model_score']),
                    'cat_count': h['cat_count'] or 0,
                })
            ctx['amc_list_json'] = json.dumps(amc_list)
            ctx['amc_count'] = len(amc_list)
        except Exception as exc:
            logger.warning('ResearchAMCListView error: %s', exc)
            ctx['amc_list_json'] = '[]'
            ctx['amc_count'] = 0
        return ctx


@login_required
def amc_list_api(request):
    """
    AJAX endpoint: GET /research/amcs/api/list/
    Returns all AMCs with computed metrics.
    Params: ?q= (search)
    """

    q = request.GET.get('q', '').strip().lower()
    try:
        houses = list(
            FundScreenerSnapshot.objects
            .filter(Q(is_direct=True) | Q(is_etf=True))
            .values('fund_house')
            .annotate(
                total_aum=Sum('aum_cr'),
                fund_count=Count('id'),
                avg_return_1y=Avg('returns_1y_pct'),
                avg_return_3y=Avg('cagr_3y_pct'),
                avg_return_5y=Avg('returns_5y_pct'),
                avg_expense_ratio=Avg('expense_ratio'),
                avg_model_score=Avg('model_score'),
                avg_alpha_3y=Avg('alpha_3y'),
                cat_count=Count('scheme_sub_category', distinct=True),
                etf_count=Count('id', filter=Q(is_etf=True)),
            )
            .order_by('-total_aum')
        )
        if q:
            houses = [h for h in houses if q in h['fund_house'].lower()]
        result = []
        for h in houses:
            name = h['fund_house']
            result.append({
                'name': name,
                'slug': _make_amc_slug(name),
                'total_aum': round(float(h['total_aum']), 0) if h['total_aum'] else None,
                'fund_count': h['fund_count'],
                'etf_count': h['etf_count'] or 0,
                'avg_return_1y': _flt(h['avg_return_1y']),
                'avg_return_3y': _flt(h['avg_return_3y']),
                'avg_return_5y': _flt(h['avg_return_5y']),
                'avg_expense_ratio': _flt(h['avg_expense_ratio']),
                'avg_model_score': _flt(h['avg_model_score']),
                'avg_alpha_3y': _flt(h['avg_alpha_3y']),
                'cat_count': h['cat_count'] or 0,
            })
        return JsonResponse({'amcs': result})
    except Exception as exc:
        logger.error('amc_list_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


class ResearchAMCDetailView(LoginRequiredMixin, TemplateView):
    """
    Research > AMC Detail: Full analysis of a single fund house.
    Requires login.
    """
    template_name = 'research/amc_detail.html'


    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = kwargs.get('slug', '')
        fund_house = _slug_to_fund_house(slug)
        if not fund_house:
            ctx['error'] = f'AMC "{slug}" not found.'
            return ctx

        try:
            metrics = _compute_amc_metrics(fund_house)

            # Build manager-to-funds map
            manager_funds: dict[str, list] = {}
            meta_qs = list(
                SchemeMeta.objects.filter(
                    scheme__fund_house=fund_house, scheme__is_active=True
                ).select_related('scheme').values(
                    'fund_manager', 'scheme__scheme_name', 'scheme__amfi_code',
                    'scheme__scheme_category',
                )
            )
            for row in meta_qs:
                if not row['fund_manager']:
                    continue
                for mgr in row['fund_manager'].split(';'):
                    mgr = mgr.strip()
                    if not mgr:
                        continue
                    manager_funds.setdefault(mgr, []).append({
                        'name': row['scheme__scheme_name'],
                        'amfi': row['scheme__amfi_code'],
                        'category': row['scheme__scheme_category'],
                    })

            # Category group breakdown
            cat_groups = {}
            group_rows = (
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True), fund_house=fund_house)
                .values('category_group', 'scheme_sub_category')
                .annotate(fund_count=Count('id'))
                .order_by('category_group', 'scheme_sub_category')
            )
            for r in group_rows:
                cat_groups.setdefault(r['category_group'], []).append({
                    'name': r['scheme_sub_category'],
                    'fund_count': r['fund_count'],
                })

            all_amcs_list = sorted(list(set(
                FundScreenerSnapshot.objects
                .filter(Q(is_direct=True) | Q(is_etf=True))
                .values_list('fund_house', flat=True)
            )))

            ctx.update({
                'fund_house': fund_house,
                'slug': slug,
                'metrics': metrics,
                'metrics_json': json.dumps(metrics),
                'manager_funds_json': json.dumps(manager_funds),
                'cat_groups': cat_groups,
                'cat_groups_json': json.dumps(cat_groups),
                'all_amcs': all_amcs_list,
                'all_amcs_json': json.dumps(all_amcs_list),
                'fund_house_json': json.dumps(fund_house),
            })
        except Exception as exc:
            logger.error('ResearchAMCDetailView error: %s', exc)
            ctx['error'] = 'Failed to load AMC data.'
        return ctx


@login_required
def amc_detail_funds_api(request, slug: str):
    """
    AJAX: GET /research/amcs/<slug>/funds/?tab=returns|risk|portfolio|fees
    Returns fund-level table data for the AMC detail page.
    """

    fund_house = _slug_to_fund_house(slug)
    if not fund_house:
        return JsonResponse({'error': 'AMC not found'}, status=404)

    tab = request.GET.get('tab', 'returns')
    q = request.GET.get('q', '').strip().lower()
    sort_by = request.GET.get('sort', '')
    direction = request.GET.get('direction', 'desc')

    try:
        qs = (
            FundScreenerSnapshot.objects
            .filter(fund_house=fund_house)
            .filter(Q(is_direct=True) | Q(is_etf=True))
            .select_related('scheme')
        )
        if q:
            qs = qs.filter(fund_name__icontains=q)

        # Sort
        sort_field_map = {
            'returns': {
                'name': 'fund_name', 'aum': '-aum_cr', 'r1y': '-returns_1y_pct',
                'r3y': '-cagr_3y_pct', 'r5y': '-returns_5y_pct', 'r7y': '-cagr_7y_pct',
            },
            'risk': {
                'name': 'fund_name', 'sharpe': '-sharpe_ratio', 'sortino': '-sortino_ratio',
                'dd': '-max_drawdown', 'alpha': '-alpha_3y', 'beta': 'beta_3y',
            },
            'portfolio': {
                'name': 'fund_name', 'turnover': '-portfolio_turnover', 'aum': '-aum_cr',
            },
            'fees': {
                'name': 'fund_name', 'er': 'expense_ratio', 'aum': '-aum_cr',
            },
        }
        field_map = sort_field_map.get(tab, {})
        sort_expr = field_map.get(sort_by, '-aum_cr')
        if direction == 'asc' and sort_expr.startswith('-'):
            sort_expr = sort_expr[1:]
        elif direction == 'desc' and not sort_expr.startswith('-'):
            sort_expr = '-' + sort_expr
        qs = qs.order_by(sort_expr)

        funds = []
        for f in qs[:200]:
            base = {
                'name': f.fund_name,
                'amfi': f.scheme.amfi_code,
                'category': f.scheme_sub_category,
                'aum': _flt(f.aum_cr),
                'is_etf': f.is_etf,
            }
            if tab == 'returns':
                base.update({
                    'r1y': _flt(f.returns_1y_pct),
                    'r3y': _flt(f.cagr_3y_pct),
                    'r5y': _flt(f.returns_5y_pct),
                    'r7y': _flt(f.cagr_7y_pct),
                    'r10y': _flt(f.cagr_10y_pct),
                    'roll3y': _flt(f.rolling_return_3y_pct),
                    'roll5y': _flt(f.rolling_return_5y_pct),
                    'alpha_1y': _flt(f.excess_return_1y),
                    'alpha_3y': _flt(f.excess_return_3y),
                    'model_score': _flt(f.model_score),
                    'score_badge': f.model_score_badge or '',
                })
            elif tab == 'risk':
                base.update({
                    'sharpe': _flt(f.sharpe_ratio),
                    'sortino': _flt(f.sortino_ratio),
                    'alpha': _flt(f.alpha_3y),
                    'beta': _flt(f.beta_3y),
                    'max_dd': _flt(f.max_drawdown),
                    'max_dd_5y': _flt(f.max_drawdown_5y),
                    'vol_1y': _flt(f.volatility_1y_pct),
                    'vol_3y': _flt(f.volatility_3y_pct),
                    'upside': _flt(f.upside_capture_3y),
                    'downside': _flt(f.downside_capture_3y),
                })
            elif tab == 'portfolio':
                base.update({
                    'turnover': _flt(f.portfolio_turnover),
                    'equity_pct': _flt(f.port_equity_pct),
                    'debt_pct': _flt(f.port_debt_pct),
                    'cash_pct': _flt(f.port_cash_pct),
                    'top10_conc': _flt(f.port_top10_concentration),
                    'manager': f.fund_manager or '',
                })
            elif tab == 'fees':
                base.update({
                    'expense_ratio': _flt(f.expense_ratio),
                    'cat_avg_er': _flt(f.category_expense_ratio),
                    'age_years': _flt(f.fund_age_years),
                    'sip_min': _flt(f.sip_min),
                    'lump_min': _flt(f.lump_min),
                    'lock_in': f.lock_in_days or 0,
                })
            funds.append(base)

        return JsonResponse({'funds': funds, 'fund_house': fund_house, 'tab': tab})
    except Exception as exc:
        logger.error('amc_detail_funds_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


class ResearchAMCCompareView(LoginRequiredMixin, TemplateView):
    """
    Research > AMC Compare: Side-by-side comparison of 2-4 AMCs.
    Requires login.
    """
    template_name = 'research/amc_compare.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slugs_param = self.request.GET.get('amcs', '')
        slugs = [s.strip() for s in slugs_param.split(',') if s.strip()][:4]
        ctx['slugs'] = slugs
        ctx['slugs_param'] = slugs_param

        # Resolve AMC names for display
        names = []
        for slug in slugs:
            house = _slug_to_fund_house(slug)
            names.append(house or slug)
        ctx['amc_names'] = names
        ctx['amc_names_json'] = json.dumps(names)

        # All available AMCs for the "add/change" selector
        ctx['all_amcs'] = sorted(list(set(
            FundScreenerSnapshot.objects
            .filter(Q(is_direct=True) | Q(is_etf=True))
            .values_list('fund_house', flat=True)
        )))

        ctx['all_amcs_json'] = json.dumps([
            {'name': h, 'slug': _make_amc_slug(h)}
            for h in ctx['all_amcs']
        ])
        return ctx


@login_required
def amc_compare_api(request):
    """
    AJAX: GET /research/amcs/api/compare/?amcs=slug1,slug2,...
    Returns comparison metrics for 2-4 AMCs.
    """
    slugs_param = request.GET.get('amcs', '')
    slugs = [s.strip() for s in slugs_param.split(',') if s.strip()][:4]
    if len(slugs) < 2:
        return JsonResponse({'error': 'Need at least 2 AMC slugs'}, status=400)

    try:
        result = []
        for slug in slugs:
            fund_house = _slug_to_fund_house(slug)
            if not fund_house:
                result.append({'slug': slug, 'fund_house': None, 'error': 'Not found'})
                continue
            m = _compute_amc_metrics(fund_house)
            result.append(m)
        return JsonResponse({'amcs': result})
    except Exception as exc:
        logger.error('amc_compare_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


# ── Category Compare ──────────────────────────────────────────────────────────

def _compute_category_compare_metrics(sub_category: str) -> dict:
    """
    Compute all cross-category comparison metrics for a single category.
    Uses CategorySnapshot for aggregates + FundScreenerSnapshot for extra metrics.
    """
    snap = CategorySnapshot.objects.filter(scheme_sub_category=sub_category).first()
    slug = _make_slug(sub_category)

    # Total AUM from fund snapshots
    qs = FundScreenerSnapshot.objects.filter(
        Q(is_direct=True) | Q(is_etf=True),
        scheme_sub_category=sub_category
    )
    aum_agg = qs.aggregate(
        total_aum=Sum('aum_cr'),
        avg_upside=Avg('upside_capture_3y'),
        avg_downside=Avg('downside_capture_3y'),
        avg_ir=Avg('info_ratio_3y'),
        avg_te=Avg('tracking_error_3y'),
        avg_alpha_5y=Avg('alpha_5y'),
    )

    rolling = snap.rolling_returns_json if snap else {}
    pos_pct_3y = rolling.get('3Y', {}).get('pos_pct') if rolling else None
    avg_rolling_1y = rolling.get('1Y', {}).get('avg') if rolling else None
    avg_rolling_3y = rolling.get('3Y', {}).get('avg') if rolling else None
    avg_rolling_5y = rolling.get('5Y', {}).get('avg') if rolling else None

    def _fv(v):
        if v is None:
            return None
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return None

    return {
        'sub_category': sub_category,
        'slug': slug,
        'category_group': snap.category_group if snap else '',
        # Scale
        'fund_count': snap.fund_count if snap else 0,
        'total_aum': _fv(aum_agg.get('total_aum')),
        # Returns
        'avg_return_1y': _fv(snap.avg_return_1y if snap else None),
        'avg_return_3y': _fv(snap.avg_return_3y if snap else None),
        'avg_return_5y': _fv(snap.avg_return_5y if snap else None),
        'median_return_3y': _fv(snap.median_return_3y if snap else None),
        'excess_return_3y': _fv(snap.excess_return_3y if snap else None),
        'spread_1y': _fv((snap.max_return_1y - snap.min_return_1y) if snap and snap.max_return_1y is not None and snap.min_return_1y is not None else None),
        'spread_3y': _fv((snap.max_return_3y - snap.min_return_3y) if snap and snap.max_return_3y is not None and snap.min_return_3y is not None else None),
        'max_return_1y': _fv(snap.max_return_1y if snap else None),
        'min_return_1y': _fv(snap.min_return_1y if snap else None),
        # Rolling
        'avg_rolling_1y': _fv(avg_rolling_1y),
        'avg_rolling_3y': _fv(avg_rolling_3y),
        'avg_rolling_5y': _fv(avg_rolling_5y),
        'pos_pct_3y': _fv(pos_pct_3y),
        # Risk
        'avg_volatility': _fv(snap.avg_volatility if snap else None),
        'avg_sharpe': _fv(snap.avg_sharpe if snap else None),
        'avg_sortino': _fv(snap.avg_sortino if snap else None),
        'avg_max_drawdown': _fv(snap.avg_max_drawdown if snap else None),
        'avg_max_drawdown_5y': _fv(snap.avg_max_drawdown_5y if snap else None),
        'avg_upside_capture': _fv(aum_agg.get('avg_upside')),
        'avg_downside_capture': _fv(aum_agg.get('avg_downside')),
        # Quality
        'avg_model_score': _fv(snap.avg_model_score if snap else None),
        'pct_strong': _fv(snap.pct_strong if snap else None),
        'pct_good': _fv(snap.pct_good if snap else None),
        'pct_fair': _fv(snap.pct_fair if snap else None),
        'pct_weak': _fv(snap.pct_weak if snap else None),
        # Costs
        'avg_expense_ratio': _fv(snap.avg_expense_ratio if snap else None),
        'median_expense_ratio': _fv(snap.median_expense_ratio if snap else None),
        'avg_turnover': _fv(snap.avg_turnover if snap else None),
        # Alpha & IR
        'avg_alpha_3y': _fv(snap.avg_alpha_3y if snap else None),
        'median_alpha_3y': _fv(snap.median_alpha_3y if snap else None),
        'avg_beta_3y': _fv(snap.avg_beta_3y if snap else None),
        'avg_ir': _fv(aum_agg.get('avg_ir')),
        'avg_te': _fv(aum_agg.get('avg_te')),
    }


class ResearchCategoryCompareView(LoginRequiredMixin, TemplateView):
    """
    Research > Category Compare: Side-by-side comparison of 2-4 categories.
    Requires login.
    """
    template_name = 'research/category_compare.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slugs_param = self.request.GET.get('cats', '')
        slugs = [s.strip() for s in slugs_param.split(',') if s.strip()][:4]
        ctx['slugs'] = slugs
        ctx['slugs_param'] = slugs_param

        names = []
        for slug in slugs:
            cat = _slug_to_sub_category(slug)
            names.append(cat or slug)
        ctx['cat_names'] = names
        ctx['cat_names_json'] = json.dumps(names)

        # All categories for the "add/change" selector
        all_snaps = CategorySnapshot.objects.order_by('category_group', 'scheme_sub_category').values(
            'scheme_sub_category', 'fund_count', 'category_group'
        )
        ctx['all_categories'] = [
            {'name': s['scheme_sub_category'], 'slug': _make_slug(s['scheme_sub_category']),
             'fund_count': s['fund_count'], 'group': s['category_group']}
            for s in all_snaps
        ]
        ctx['all_categories_json'] = json.dumps(ctx['all_categories'])
        return ctx


def category_list_api(request):
    """
    AJAX: GET /research/categories/api/list/
    Returns all categories with aggregate metrics for the directory grid.
    """


    try:
        snaps = list(CategorySnapshot.objects.all().order_by('category_group', 'scheme_sub_category'))
        # Get AUM per category
        aum_by_cat = dict(
            FundScreenerSnapshot.objects
            .filter(Q(is_direct=True) | Q(is_etf=True))
            .values('scheme_sub_category')
            .annotate(total_aum=Sum('aum_cr'))
            .values_list('scheme_sub_category', 'total_aum')
        )

        data = []
        for snap in snaps:
            def fv(x):
                return round(float(x), 4) if x is not None else None

            rolling = snap.rolling_returns_json or {}
            data.append({
                'name': snap.scheme_sub_category,
                'slug': _make_slug(snap.scheme_sub_category),
                'group': snap.category_group,
                'fund_count': snap.fund_count,
                'total_aum': fv(aum_by_cat.get(snap.scheme_sub_category)),
                'avg_return_1y': fv(snap.avg_return_1y),
                'avg_return_3y': fv(snap.avg_return_3y),
                'avg_return_5y': fv(snap.avg_return_5y),
                'avg_sharpe': fv(snap.avg_sharpe),
                'avg_max_drawdown': fv(snap.avg_max_drawdown),
                'avg_expense_ratio': fv(snap.avg_expense_ratio),
                'avg_model_score': fv(snap.avg_model_score),
                'pct_strong': fv(snap.pct_strong),
                'pct_good': fv(snap.pct_good),
                'pct_fair': fv(snap.pct_fair),
                'pct_weak': fv(snap.pct_weak),
                'avg_rolling_3y': fv(rolling.get('3Y', {}).get('avg') if rolling else None),
                'pos_pct_3y': fv(rolling.get('3Y', {}).get('pos_pct') if rolling else None),
            })
        return JsonResponse({'categories': data})
    except Exception as exc:
        logger.error('category_list_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)


@login_required
def category_compare_api(request):
    """
    AJAX: GET /research/categories/api/compare/?cats=slug1,slug2,...
    Returns comparison metrics for 2-4 categories.
    """
    slugs_param = request.GET.get('cats', '')
    slugs = [s.strip() for s in slugs_param.split(',') if s.strip()][:4]
    if len(slugs) < 2:
        return JsonResponse({'error': 'Need at least 2 category slugs'}, status=400)


    try:
        result = []
        for slug in slugs:
            cat = _slug_to_sub_category(slug)
            if not cat:
                result.append({'slug': slug, 'sub_category': None, 'error': 'Not found'})
                continue
            result.append(_compute_category_compare_metrics(cat))
        return JsonResponse({'categories': result})
    except Exception as exc:
        logger.error('category_compare_api error: %s', exc)
        return JsonResponse({'error': 'server error'}, status=500)

