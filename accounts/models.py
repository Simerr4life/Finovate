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
    photon_chat_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=(
            "The iMessage chat/sender id this account is reachable at, once a "
            "Photon Spectrum line exists. Used to route an inbound webhook "
            "message to the right Finovate user. Empty until you set it."
        ),
    )
    auth0_sub = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text=(
            "Auth0's stable 'sub' claim for this user, if they've ever logged "
            "in via Auth0. Null for local demo-only accounts. Never used to "
            "merge accounts by email — only this exact identifier maps to a "
            "Finovate user."
        ),
    )
    messaging_linked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this user proved control of photon_chat_id by sending a one-time link code.",
    )
    notify_simulated_orders = models.BooleanField(
        default=False,
        help_text="Opt in to local records when a simulated investment proposal is created. This does not send iMessage.",
    )
    identity_status = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=(
            "Latest Auth0 account state. Empty for local fixture users that "
            "were never created through Auth0. Never set to verified just "
            "because a form was submitted."
        ),
    )
    email_verified = models.BooleanField(
        default=False,
        help_text="True only when Auth0's email_verified claim is true.",
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Contact number collected for messaging. Ownership is not verified by saving this value.",
    )
    phone_verified = models.BooleanField(
        default=False,
        help_text="True only when Auth0 reports phone_number_verified. A typed number never sets this.",
    )
    messaging_consent = models.BooleanField(
        default=False,
        help_text="The user agreed to receive Finovate messages. Consent alone does not verify the phone.",
    )
    account_created_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the Finovate profile was first created for this Auth0 subject.",
    )
    welcome_recorded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the one-time welcome record was written. Stops retries from sending it again.",
    )

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
        ACCOUNT_CREATED = "account_created", "Auth0 account created"
        WELCOME = "welcome", "Welcome"
        SYSTEM = "system", "System message"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_events"
    )
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    message = models.CharField(max_length=255)
    read_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(
        max_length=20,
        default="recorded",
        help_text="recorded means Finovate stored the event. This server does not mark events sent over iMessage.",
    )

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
