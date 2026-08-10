"""
Shared base models for all apps.
All project models should inherit from BaseModel to get timestamps.
"""
from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model providing created_at and updated_at timestamps.
    All project models must inherit from this.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DataProvenance(BaseModel):
    """
    Records which data source fetched which field for which object, and when.
    Used to display "Data as of DD-MMM-YYYY (Source: captnemo)" in the UI.
    """
    # Generic FK fields (content_type free version for simplicity)
    app_label    = models.CharField(max_length=50)    # e.g. 'funds'
    model_name   = models.CharField(max_length=50)    # e.g. 'Scheme'
    object_id    = models.BigIntegerField()
    field_name   = models.CharField(max_length=100)   # e.g. 'expense_ratio'
    source       = models.CharField(max_length=50)    # e.g. 'captnemo'
    fetched_at   = models.DateTimeField()
    is_stale     = models.BooleanField(default=False)  # True if > 7 days old

    class Meta:
        indexes = [
            models.Index(fields=['app_label', 'model_name', 'object_id']),
        ]

    def __str__(self):
        return f"{self.model_name}({self.object_id}).{self.field_name} from {self.source}"


class LearnPDFGuide(BaseModel):
    """A PDF learning resource synced from Resources/PDF Guides."""

    CATEGORY_CHAPTERS = 'chapters'
    CATEGORY_HANDBOOK = 'handbook'
    CATEGORY_OTHER = 'other'
    CATEGORY_CHOICES = [
        (CATEGORY_CHAPTERS, 'Chapterwise Guides'),
        (CATEGORY_HANDBOOK, 'Complete Handbook'),
        (CATEGORY_OTHER, 'Other Guides'),
    ]

    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    pdf_path = models.CharField(max_length=500, unique=True)
    cover_image_path = models.CharField(max_length=500, blank=True)
    accent = models.CharField(max_length=100, blank=True)
    size_kb = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=100)
    is_published = models.BooleanField(default=True)
    downloadable = models.BooleanField(default=False, help_text='Allow users to download this PDF')
    synced_at = models.DateTimeField(null=True, blank=True)
    # Category places the guide in a sub-section of the Resources page
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
    )
    # Comma-separated or JSON-list tags stored as plain text
    tags = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['sort_order', 'title']
        indexes = [models.Index(fields=['is_published', 'sort_order', 'category'])]

    def __str__(self):
        return self.title

    def tag_list(self):
        """Return tags as a cleaned Python list."""
        raw = self.tags.strip()
        if not raw:
            return []
        # Support JSON-array format ["a", "b"] or comma-separated
        if raw.startswith('['):
            import json
            try:
                return [t.strip() for t in json.loads(raw) if t.strip()]
            except (ValueError, TypeError):
                pass
        return [t.strip() for t in raw.split(',') if t.strip()]


class LearnBlogPost(BaseModel):
    """A markdown blog post synced from Resources/Blogs."""
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    markdown_path = models.CharField(max_length=500, unique=True)
    thumbnail_path = models.CharField(max_length=500, blank=True)
    read_time = models.CharField(max_length=32, blank=True)
    sort_order = models.PositiveIntegerField(default=100)
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    # Comma-separated or JSON-list tags stored as plain text
    tags = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['sort_order', 'title']
        indexes = [models.Index(fields=['is_published', 'sort_order'])]

    def __str__(self):
        return self.title

    def tag_list(self):
        """Return tags as a cleaned Python list."""
        raw = self.tags.strip()
        if not raw:
            return []
        if raw.startswith('['):
            import json
            try:
                return [t.strip() for t in json.loads(raw) if t.strip()]
            except (ValueError, TypeError):
                pass
        return [t.strip() for t in raw.split(',') if t.strip()]
