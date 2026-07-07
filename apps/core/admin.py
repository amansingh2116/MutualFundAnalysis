from django.contrib import admin

from .models import DataProvenance, LearnBlogPost, LearnPDFGuide


@admin.register(LearnPDFGuide)
class LearnPDFGuideAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'sort_order', 'size_kb', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'description', 'pdf_path')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('size_kb', 'synced_at', 'created_at', 'updated_at')
    ordering = ('sort_order', 'title')


@admin.register(LearnBlogPost)
class LearnBlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'sort_order', 'read_time', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'description', 'markdown_path')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('synced_at', 'created_at', 'updated_at')
    ordering = ('sort_order', 'title')


@admin.register(DataProvenance)
class DataProvenanceAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'object_id', 'field_name', 'source', 'fetched_at', 'is_stale')
    list_filter = ('app_label', 'model_name', 'source', 'is_stale')
    search_fields = ('model_name', 'field_name', 'source')
    readonly_fields = ('created_at', 'updated_at')
