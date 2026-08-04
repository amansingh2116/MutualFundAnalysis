"""apps/core/forms.py — Auth + contact forms."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    """Extended registration form that makes email a required field."""
    email = forms.EmailField(
        required=True,
        label='Email address',
        help_text='Required. Used for account verification and password reset.',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'you@example.com',
            'autocomplete': 'email',
        }),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists.'
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        # Account starts inactive — activated via email link
        user.is_active = False
        if commit:
            user.save()
        return user


class ContactForm(forms.Form):
    """Contact / feedback form."""
    SUBJECT_CHOICES = [
        ('data_error',  'Data Error / Incorrect NAV'),
        ('feedback',    'General Feedback'),
        ('feature',     'Feature Request'),
        ('account',     'Account Issue'),
        ('other',       'Other'),
    ]

    name = forms.CharField(
        max_length=120,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Your name',
            'id': 'contact-name',
        }),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'placeholder': 'you@example.com',
            'id': 'contact-email',
        }),
    )
    subject = forms.ChoiceField(
        choices=SUBJECT_CHOICES,
        widget=forms.Select(attrs={'id': 'contact-subject'}),
    )
    message = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': "Tell us what's on your mind...",
            'id': 'contact-message',
        }),
    )
