"""apps/screener/views.py"""
import logging
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Q

from apps.funds.models import Scheme
from .forms import FundFilterForm

logger = logging.getLogger('mfanalysis')


def _apply_filters(form):
    """Return filtered Scheme queryset based on clean form data."""
    qs = Scheme.objects.filter(is_active=True)
    d = form.cleaned_data if form.is_valid() else {}

    if d.get('q'):
        qs = qs.filter(scheme_name__icontains=d['q'])
    if d.get('scheme_category'):
        qs = qs.filter(scheme_category=d['scheme_category'])
    if d.get('fund_house'):
        qs = qs.filter(fund_house=d['fund_house'])
    if d.get('plan'):
        qs = qs.filter(plan=d['plan'])
    if d.get('is_direct') is not None:
        if str(d['is_direct']).lower() == 'true':
            qs = qs.filter(is_direct=True)
        elif str(d['is_direct']).lower() == 'false':
            qs = qs.filter(is_direct=False)
    if d.get('min_aum'):
        qs = qs.filter(aum_cr__gte=d['min_aum'])
    if d.get('max_expense'):
        qs = qs.filter(expense_ratio__lte=d['max_expense'])

    sort = d.get('sort_by') or 'scheme_name'
    qs = qs.order_by(sort)
    return qs


def screener_view(request):
    form = FundFilterForm(request.GET or None)
    qs = _apply_filters(form)
    count = qs.count()
    schemes = qs.select_related('meta')[:200]
    return render(request, 'screener/screener.html', {
        'form': form, 'schemes': schemes, 'count': count
    })


def screener_results_view(request):
    """HTMX partial — returns just the results table rows."""
    form = FundFilterForm(request.GET or None)
    qs = _apply_filters(form)
    count = qs.count()
    schemes = qs.select_related('meta')[:200]
    return render(request, 'screener/_results.html', {
        'schemes': schemes, 'count': count
    })


def compare_view(request):
    """Multi-fund comparison — up to 4 funds."""
    amfi_codes = request.GET.getlist('funds')
    if request.GET.get('funds_input'):
        amfi_codes += [c.strip() for c in request.GET['funds_input'].split(',') if c.strip()]
    amfi_codes = amfi_codes[:4]
    schemes = []
    if amfi_codes:
        from apps.funds.runtime import get_runtime_snapshot

        schemes_qs = Scheme.objects.filter(amfi_code__in=amfi_codes).select_related('meta')
        schemes_map = {s.amfi_code: s for s in schemes_qs}

        for code in amfi_codes:
            s = schemes_map.get(code)
            if not s:
                continue
            runtime = get_runtime_snapshot(s)
            if runtime.nav_latest:
                s.nav_latest = runtime.nav_latest
            if runtime.nav_date:
                s.nav_date = runtime.nav_date
            if runtime.category:
                s.scheme_category = runtime.category
            if runtime.meta.aum:
                s.aum_cr = runtime.meta.aum
            if runtime.meta.expense_ratio:
                s.expense_ratio = runtime.meta.expense_ratio
            s.trailing_map = runtime.trailing_map
            s.risk_3y_runtime = runtime.risk_3y
            schemes.append(s)

    return render(request, 'screener/compare.html', {
        'schemes': schemes,
        'amfi_codes': ','.join(amfi_codes),
    })
