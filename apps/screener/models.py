"""
Screening app models – predefined fund screening criteria.

We keep it lightweight; the real logic lives in the analytics engine.
"""
from django.db import models
from apps.core.models import BaseModel


class Screener(BaseModel):
    """A saved screening configuration (e.g., by user or admin)."""
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    # JSON field containing criteria, e.g., {"min_nav":10, "max_expense_ratio":1.5}
    criteria = models.JSONField(default=dict, help_text="Screening criteria in JSON")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name
