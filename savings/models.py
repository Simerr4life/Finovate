from django.conf import settings
from django.db import models

from core.models import DATA_SOURCE_CHOICES, TimeStampedModel


class Goal(TimeStampedModel):
    class Category(models.TextChoices):
        EMERGENCY = "emergency", "Emergency fund"
        TRAVEL = "travel", "Travel"
        HOME = "home", "Home"
        EDUCATION = "education", "Education"
        VEHICLE = "vehicle", "Vehicle"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Actual cash tracked toward this goal (not a plan allocation, not invested funds).",
    )
    target_date = models.DateField(null=True, blank=True)
    color = models.CharField(
        max_length=7, default="#6366F1", help_text="Hex color used to customize this pool's display."
    )
    is_investable = models.BooleanField(
        default=False,
        help_text=(
            "When on, this pool can be chosen as a target for round-ups and "
            "proposed surplus investments. Invested amounts are tracked "
            "separately (see investing.PortfolioSnapshot) from this pool's "
            "own cash current_amount — never combined into one number."
        ),
    )
    is_demo = models.BooleanField(default=False)
    achieved_at = models.DateTimeField(null=True, blank=True)
    highest_milestone_notified = models.PositiveSmallIntegerField(
        default=0,
        help_text="Highest milestone percent (0/25/50/75/100) already notified for, to avoid repeat alerts.",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def progress_percent(self) -> int:
        if self.target_amount <= 0:
            return 0
        pct = (self.current_amount / self.target_amount) * 100
        return int(min(max(pct, 0), 100))

    @property
    def remaining_amount(self):
        remaining = self.target_amount - self.current_amount
        return remaining if remaining > 0 else type(self.target_amount)(0)


class Contribution(TimeStampedModel):
    """A manual add/withdraw/adjust against a goal's current_amount."""

    class Kind(models.TextChoices):
        CONTRIBUTION = "contribution", "Contribution"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        ADJUSTMENT = "adjustment", "Adjustment"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goal_contributions"
    )
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="contributions")
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.CONTRIBUTION)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Always positive; kind determines whether it increases or decreases current_amount.",
    )
    note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=10, choices=DATA_SOURCE_CHOICES, default="manual")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount} -> {self.goal}"
