"""Models for the channel-agnostic messaging assistant.

Nothing here is wired to a specific provider. A PendingConfirmation is how
the assistant holds its breath between "here's what I'm about to do" and
"you said yes" across two separate inbound messages — required because any
state-changing intent (recording income, changing a goal or risk comfort,
re-enabling round-ups) must have explicit confirmation before it touches
real data, per the project's messaging-assistant safety rule.
"""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PendingConfirmation(TimeStampedModel):
    """At most one open confirmation per user at a time."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pending_confirmation"
    )
    intent = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    prompt_text = models.CharField(max_length=500)

    def __str__(self) -> str:
        return f"Pending {self.intent} for user {self.user_id}"


class SpectrumDelivery(TimeStampedModel):
    """Idempotency record for a Spectrum webhook delivery.

    Spectrum Cloud retries with at-least-once delivery. The composite key
    is the documented dedupe pair: X-Spectrum-Webhook-Id plus message.id.
    """

    webhook_id = models.CharField(max_length=255)
    message_id = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["webhook_id", "message_id"],
                name="assistant_spectrum_delivery_unique",
            )
        ]


class ConversationMessage(TimeStampedModel):
    """Audit trail of assistant traffic — never logs raw financial amounts
    beyond what's already in the message body itself; see logging policy
    in docs/messaging-assistant.md.
    """

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_messages"
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    body = models.TextField()
    intent = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.direction}: {self.body[:40]}"
