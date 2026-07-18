"""apps/core/urls.py"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('learn/resources/', views.learn_resources_view, name='learn_resources'),
    path('learn/resources/guides/', views.learn_pdf_guides_view, name='learn_pdf_guides'),
    path('learn/resources/blogs/', views.learn_blogs_view, name='learn_blogs'),
    path('learn/resources/assets/<path:resource_path>/', views.learn_resource_asset_view, name='learn_resource_asset'),
    # In-app PDF viewer (new)
    path('learn/resources/guides/view/<slug:slug>/', views.learn_pdf_viewer_view, name='learn_pdf_viewer'),
    # Raw PDF bytes served to PDF.js (new)
    path('learn/resources/guides/serve/<slug:slug>/', views.learn_pdf_serve_view, name='learn_pdf_serve'),
    # Legacy routes — now redirect to viewer
    path('learn/resources/guides/open/<slug:slug>/', views.learn_pdf_detail_view, name='learn_pdf_detail'),
    path('learn/resources/guides/<path:filename>/', views.learn_pdf_view, name='learn_pdf'),
    path('learn/resources/blog/<slug:slug>/', views.learn_blog_detail_view, name='learn_blog_detail'),
    path('learn/resources/blog/ipo-analysis/images/<path:filename>/', views.learn_blog_image_view, name='learn_blog_image'),
    path('learn/community/', views.learn_community_view, name='learn_community'),

    # ── Legal / Info pages ─────────────────────────────────────────────────────
    path('about/',   views.about_view,   name='about'),
    path('terms/',   views.terms_view,   name='terms'),
    path('privacy/', views.privacy_view, name='privacy'),
    path('contact/', views.contact_view, name='contact'),
]

