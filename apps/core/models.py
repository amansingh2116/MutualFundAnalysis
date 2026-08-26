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


# ── Investor Community Feed Models ──────────────────────────────
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class CommunityProfile(BaseModel):
    """Profile attributes and investor identity for Community members."""
    AVATAR_COLOR_CHOICES = [
        ('av-indigo', 'Indigo'),
        ('av-green',  'Emerald'),
        ('av-amber',  'Amber'),
        ('av-rose',   'Rose'),
        ('av-cyan',   'Cyan'),
        ('av-violet', 'Violet'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='community_profile')
    display_name = models.CharField(max_length=100, blank=True)
    bio = models.CharField(max_length=300, blank=True)
    investor_tag = models.CharField(max_length=100, default='Portfolio Investor', help_text='e.g. SEBI RIA, Quant Researcher, DIY Investor')
    avatar_color = models.CharField(max_length=30, choices=AVATAR_COLOR_CHOICES, default='av-indigo')
    avatar_initials = models.CharField(max_length=6, blank=True)
    is_moderator = models.BooleanField(default=False)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        if self.display_name:
            return self.display_name
        full = self.user.get_full_name()
        if full:
            return full
        return self.user.username

    def get_initials(self):
        if self.avatar_initials:
            return self.avatar_initials[:3].upper()
        name = self.get_display_name().strip()
        parts = [p for p in name.split() if p]
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        elif len(parts) == 1:
            return parts[0][:2].upper()
        return "IN"

    def followers_count(self):
        return self.user.follower_relationships.count()

    def following_count(self):
        return self.user.following_relationships.count()

    def posts_count(self):
        return self.user.community_posts.count()


@receiver(post_save, sender=User)
def create_or_save_community_profile(sender, instance, created, **kwargs):
    if created:
        CommunityProfile.objects.create(user=instance)
    else:
        if not hasattr(instance, 'community_profile'):
            CommunityProfile.objects.create(user=instance)


class CommunityFollow(BaseModel):
    """Tracks follow/following relationships between users."""
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following_relationships')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='follower_relationships')

    class Meta:
        unique_together = ('follower', 'following')
        indexes = [
            models.Index(fields=['follower', 'following']),
            models.Index(fields=['following']),
        ]

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class CommunityPost(BaseModel):
    """User generated discussion thread in the community feed."""
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='community_posts')
    title = models.CharField(max_length=255)
    content = models.TextField()
    image = models.ImageField(upload_to='community/posts/', blank=True, null=True)
    tags = models.TextField(blank=True, default='', help_text='Comma-separated or JSON list of hashtags')
    is_pinned = models.BooleanField(default=False)
    likes_count = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['-is_pinned', '-created_at']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def tag_list(self):
        raw = self.tags.strip()
        if not raw:
            return []
        if raw.startswith('['):
            import json
            try:
                return [t.strip().lstrip('#') for t in json.loads(raw) if t.strip()]
            except (ValueError, TypeError):
                pass
        return [t.strip().lstrip('#') for t in raw.split(',') if t.strip()]

    def sync_counts(self):
        self.likes_count = self.likes.count()
        self.replies_count = self.replies.count()
        self.save(update_fields=['likes_count', 'replies_count'])


class CommunityComment(BaseModel):
    """Reply / comment on a community discussion post."""
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='community_replies')
    content = models.TextField()

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['post', 'created_at']),
            models.Index(fields=['author']),
        ]

    def __str__(self):
        return f"Reply by {self.author.username} on #{self.post_id}"


class CommunityLike(BaseModel):
    """Tracks post likes by users."""
    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='community_likes')

    class Meta:
        unique_together = ('post', 'user')
        indexes = [
            models.Index(fields=['post', 'user']),
        ]

    def __str__(self):
        return f"{self.user.username} liked #{self.post_id}"

