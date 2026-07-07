"""apps/core/urls.py"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('learn/resources/', views.learn_resources_view, name='learn_resources'),
    path('learn/resources/assets/<path:resource_path>/', views.learn_resource_asset_view, name='learn_resource_asset'),
    path('learn/resources/guides/open/<slug:slug>/', views.learn_pdf_detail_view, name='learn_pdf_detail'),
    path('learn/resources/guides/<path:filename>/', views.learn_pdf_view, name='learn_pdf'),
    path('learn/resources/blog/<slug:slug>/', views.learn_blog_detail_view, name='learn_blog_detail'),
    path('learn/resources/blog/ipo-analysis/images/<path:filename>/', views.learn_blog_image_view, name='learn_blog_image'),
    path('learn/community/', views.learn_community_view, name='learn_community'),
]
