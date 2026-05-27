"""
apps/funds/report.py — PDF report generation using WeasyPrint
Based on the structure of docs/mutual fund analysis template.pdf
Sections: Cover, Fund Info, Trailing Returns, Calendar Returns,
          Risk Metrics, Top Holdings, Sector Allocation, Cost Summary
"""
import logging
from datetime import date
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string

from apps.analytics.models import CalendarReturn, RiskMetrics, TrailingReturn
from apps.holdings.models import Holding, SectorAllocation

logger = logging.getLogger('mfanalysis')


def generate_fund_report_response(request, scheme) -> HttpResponse:
    """
    Generate a report for a mutual fund scheme.
    Because WeasyPrint (GTK3) is difficult to install on Windows,
    this serves an HTML page designed for printing (via browser 'Save as PDF').
    """
    today = date.today()
    meta = getattr(scheme, 'meta', None)

    # Gather data
    trailing = list(scheme.trailing_returns.order_by('-as_of', 'years')[:15])
    calendar = list(scheme.calendar_returns.order_by('-year')[:10])
    risk_3y = scheme.risk_metrics.filter(period='3Y').order_by('-as_of').first()
    risk_5y = scheme.risk_metrics.filter(period='5Y').order_by('-as_of').first()

    last_holding = Holding.objects.filter(scheme=scheme).order_by('-as_of_month').first()
    holdings = []
    sector_alloc = []
    if last_holding:
        holdings = list(
            Holding.objects.filter(scheme=scheme, as_of_month=last_holding.as_of_month)
            .order_by('-weight_pct')[:20]
        )
        sector_alloc = list(
            SectorAllocation.objects.filter(scheme=scheme, as_of_month=last_holding.as_of_month)
            .order_by('-weight_pct')
        )

    context = {
        'scheme': scheme,
        'meta': meta,
        'report_date': today.strftime('%d %B %Y'),
        'trailing_returns': trailing,
        'calendar_returns': calendar,
        'risk_3y': risk_3y,
        'risk_5y': risk_5y,
        'top_holdings': holdings,
        'sector_alloc': sector_alloc,
        'request': request,
    }

    html_string = render_to_string('funds/report_pdf.html', context)
    # Add a simple window.print() script at the end so the print dialog opens automatically
    print_script = "<script>window.onload = function() { window.print(); }</script>"
    html_string = html_string.replace("</body>", f"{print_script}</body>")
    
    return HttpResponse(html_string)
