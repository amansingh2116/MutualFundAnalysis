"""apps/core/views.py — Shared views including registration"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


class RegisterView:
    pass


def register_view(request):
    if request.user.is_authenticated:
        return redirect('funds:home')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('funds:home')
    else:
        form = UserCreationForm()

    # Style the form fields
    for field in form.fields.values():
        field.widget.attrs.setdefault('class', 'form-control')

    return render(request, 'registration/register.html', {'form': form})
