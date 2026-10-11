from django.conf import settings
from django.db import models

from core.models import TimeStampedModel

# Only CSV is implemented today. The choice list exists so a later format
# (OFX/QFX, QIF, PDF) is a new value here plus a new parser module, not a
# schema change.
SOURCE_FORMAT_CHOICES = [
    ("csv", "CSV"),
]

MAX_RAW_FILE_BYTES = 2_000_000


class ImportBatch(TimeStampedModel):
    """One upload-to-commit attempt at importing a bank statement.

    Holds the raw file (size-capped) so a failed or abandoned import can be
    retried without re-uploading, and so a user can later delete the source
    file while keeping the audit trail of what was imported. Deleting this
    row never deletes the Transaction rows it already committed -- those are
    independent records once committed, same as any other transaction.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "In progress"
        COMMITTED = "committed", "Committed"
        FAILED = "failed", "Failed"
        DISCARDED = "discarded", "Discarded"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="import_batches"
    )
    account = models.ForeignKey(
        "transactions.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_batches",
        help_text="Set once the user picks or creates an account in step 2.",
    )
    source_format = models.CharField(max_length=10, choices=SOURCE_FORMAT_CHOICES, default="csv")
    original_filename = models.CharField(max_length=255, blank=True)
    raw_file = models.BinaryField(
        max_length=MAX_RAW_FILE_BYTES,
        null=True,
        blank=True,
        help_text="Original upload bytes, cleared when the user deletes the source file.",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Set once the user confirms a mapping in step 3; re-read on every later
    # step so nothing about the parsed preview is ever trusted from the
    # client -- it's always recomputed from raw_file + column_mapping.
    column_mapping = models.JSONField(default=dict, blank=True)

    started_from_onboarding = models.BooleanField(default=False)

    rows_detected = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    rows_duplicate_skipped = models.PositiveIntegerField(default=0)
    rows_flagged = models.PositiveIntegerField(default=0)

    # Short, human-readable strings only -- never raw exceptions/tracebacks
    # and never full transaction descriptions or account numbers.
    validation_summary = models.JSONField(default=list, blank=True)
    error_message = models.CharField(max_length=255, blank=True)

    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ImportBatch<{self.pk}> {self.status}"

    @property
    def has_source_file(self) -> bool:
        return bool(self.raw_file)
