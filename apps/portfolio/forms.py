from django import forms
from django.core.exceptions import ValidationError
from datetime import date

class ManualTransactionForm(forms.Form):
    TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('SIP', 'SIP'),
        ('SWP', 'SWP'),
    ]
    scheme_id = forms.IntegerField(required=True)
    tx_type = forms.ChoiceField(choices=TYPES, required=True)
    amount = forms.DecimalField(max_digits=15, decimal_places=2, required=True)
    start_date = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        cleaned_data = super().clean()
        tx_type = cleaned_data.get('tx_type')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if tx_type in ('SIP', 'SWP'):
            if not end_date:
                raise ValidationError("End date is required for SIP/SWP")
            if end_date < start_date:
                raise ValidationError("End date cannot be before start date")
            if start_date > date.today():
                raise ValidationError("Start date cannot be in the future")
        else:
            if start_date > date.today():
                raise ValidationError("Transaction date cannot be in the future")
        return cleaned_data
