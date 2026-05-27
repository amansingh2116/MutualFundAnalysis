"""apps/core/urls.py"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('register/', views.register_view, name='register'),
]
