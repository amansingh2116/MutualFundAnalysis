"""apps/core/urls.py"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('learn/resources/', views.learn_resources_view, name='learn_resources'),
    path('learn/resources/guides/<path:filename>/', views.learn_pdf_view, name='learn_pdf'),
    path('learn/resources/blog/ipo-analysis/', views.learn_blog_detail_view, name='learn_blog_detail'),
    path('learn/resources/blog/ipo-analysis/images/<path:filename>/', views.learn_blog_image_view, name='learn_blog_image'),
    path('learn/community/', views.learn_community_view, name='learn_community'),
]
