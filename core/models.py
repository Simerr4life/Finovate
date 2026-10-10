from django.db import models


class TimeStampedModel(models.Model):
    """Shared created/updated timestamps for most domain models."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


DATA_SOURCE_CHOICES = [
    ("manual", "Manually entered"),
    ("imported", "Imported"),
    ("demo", "Demo/sample data"),
]
