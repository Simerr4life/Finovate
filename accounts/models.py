from django.conf import settings
from django.db import models

from core.models import TimeStampedModel

INCOME_CADENCE_CHOICES = [
    ("weekly", "Weekly"),
    ("biweekly", "Every two weeks"),
    ("monthly", "Monthly"),
    ("irregular", "Irregular"),
]

RISK_COMFORT_CHOICES = [
    ("unspecified", "Not specified"),
    ("low", "Low — prefer stability"),
    ("medium", "Medium — some ups and downs are okay"),
    ("high", "High — comfortable with volatility"),
]

THEME_CHOICES = [
    ("light", "Light"),
    ("dark", "Dark"),
    ("system", "Match system"),
]


class Profile(TimeStampedModel):
    """Per-user preferences collected during onboarding and settings.

    This is intentionally the only place user-level preferences live today;
    it is not meant to model every future setting, just what the current
    pages (onboarding, settings, budget planning) actually read.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    income_cadence = models.CharField(
        max_length=20, choices=INCOME_CADENCE_CHOICES, default="monthly"
    )
    risk_comfort = models.CharField(
        max_length=20, choices=RISK_COMFORT_CHOICES, default="unspecified"
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="system")
    budget_warning_threshold_percent = models.PositiveSmallIntegerField(
        default=80,
        help_text="Default warning threshold applied to new budgets, as a percent of the limit.",
    )
    cash_reserve_target = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Minimum cash the user wants to keep untouched before round-ups/investing dip in.",
    )
    notify_budget_warnings = models.BooleanField(default=True)
    notify_goal_milestones = models.BooleanField(default=True)
    onboarding_completed = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Profile<{self.user_id}>"


class NotificationEvent(TimeStampedModel):
    """A record of something the app would have notified the user about.

    No real email/SMS/chat delivery happens yet — this is the audit trail
    that a future notification channel (including a messaging integration)
    would read from and mark as delivered.
    """

    class EventType(models.TextChoices):
        BUDGET_WARNING = "budget_warning", "Budget warning threshold reached"
        GOAL_MILESTONE = "goal_milestone", "Savings goal milestone reached"
        ROUNDUP_PAUSED = "roundup_paused", "Round-ups paused"
        SYSTEM = "system", "System message"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_events"
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    message = models.CharField(max_length=255)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type}: {self.message[:40]}"


class ConnectedAccountPlaceholder(TimeStampedModel):
    """Metadata-only placeholder for a future connected bank/brokerage account.

    Deliberately holds no credentials or account numbers — just enough to
    render an honest "not connected yet" status in Settings. Real connection
    metadata (external account IDs, sync status) would extend this model
    once a provider is actually configured.
    """

    class ProviderType(models.TextChoices):
        BANK = "bank", "Bank account"
        BROKERAGE = "brokerage", "Brokerage account"

    class Status(models.TextChoices):
        NOT_CONNECTED = "not_connected", "Not connected"
        PENDING = "pending", "Pending"
        CONNECTED = "connected", "Connected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connected_accounts"
    )
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    display_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_CONNECTED
    )

    class Meta:
        unique_together = [("user", "provider_type")]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.status})"
