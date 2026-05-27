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
