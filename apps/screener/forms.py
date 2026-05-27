"""apps/screener/forms.py — Fund screener filter form"""
from django import forms
from apps.funds.models import Scheme


def get_categories():
    return [('', 'All Categories')] + [
        (c['scheme_category'], c['scheme_category'])
        for c in Scheme.objects.values('scheme_category').distinct().order_by('scheme_category')
    ]

def get_fund_houses():
    return [('', 'All AMCs')] + [
        (h['fund_house'], h['fund_house'])
        for h in Scheme.objects.values('fund_house').distinct().order_by('fund_house')
    ]


class FundFilterForm(forms.Form):
    q                = forms.CharField(required=False, label='Search name')
    scheme_category  = forms.ChoiceField(required=False, label='Category', choices=[])
    fund_house       = forms.ChoiceField(required=False, label='AMC', choices=[])
    plan             = forms.ChoiceField(required=False, label='Plan', choices=[
        ('', 'All Plans'), ('GROWTH', 'Growth'), ('IDCW', 'IDCW')
    ])
    is_direct        = forms.NullBooleanField(required=False, label='Direct Only',
                                               widget=forms.Select(choices=[('', 'All'), ('true', 'Direct'), ('false', 'Regular')]))
    min_aum          = forms.FloatField(required=False, label='Min AUM (Cr)')
    max_expense      = forms.FloatField(required=False, label='Max Expense Ratio (%)')
    min_return_1y    = forms.FloatField(required=False, label='Min 1Y Return (%)')
    min_return_3y    = forms.FloatField(required=False, label='Min 3Y Return (%)')
    min_return_5y    = forms.FloatField(required=False, label='Min 5Y Return (%)')
    sort_by          = forms.ChoiceField(required=False, label='Sort By', choices=[
        ('scheme_name', 'Name A→Z'),
        ('-nav_latest', 'NAV ↓'),
        ('-aum_cr', 'AUM ↓'),
        ('-expense_ratio', 'Expense Ratio ↓'),
        ('expense_ratio', 'Expense Ratio ↑'),
    ])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Lazy-load choices at request time (not import time) to avoid DB hit on startup
        self.fields['scheme_category'].choices = get_categories()
        self.fields['fund_house'].choices = get_fund_houses()
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
