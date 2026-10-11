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

    class SystemKey(models.TextChoices):
        RAINY_DAY = "rainy_day", "Rainy Day"
        INVESTMENT = "investment", "Investment"
        REGULAR = "regular", "Regular Savings"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    system_key = models.CharField(
        max_length=20,
        choices=SystemKey.choices,
        blank=True,
        default="",
        help_text=(
            "Stable key for engine-managed default pools (Rainy Day, Investment, "
            "Regular Savings). Empty for user-created goals. Never duplicated per user."
        ),
    )
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
        constraints = [
            models.UniqueConstraint(
                fields=["user", "system_key"],
                condition=~models.Q(system_key=""),
                name="savings_goal_unique_system_key_per_user",
            ),
        ]

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


class DebtObligation(TimeStampedModel):
    """Optional debt the savings-plan engine can prioritize.

    Minimum payments should also appear as recurring expenses when the user
    tracks them that way; this model adds balance + APR so the engine can
    distinguish high-interest debt without guessing from expense names alone.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="debt_obligations"
    )
    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    minimum_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interest_rate_apr = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Annual percentage rate, e.g. 22.90 for 22.9% APR.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-interest_rate_apr", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.balance} @ {self.interest_rate_apr}%)"


class SavingsPlan(TimeStampedModel):
    """Latest personalized savings recommendation for a user.

    Recommendations are never transfers. Pausing/disabling stops updates from
    being shown as active advice; historical revisions remain in
    SavingsPlanRevision.
    """

    class Scenario(models.TextChoices):
        STABILIZATION = "stabilization", "Financial stabilization"
        BUILD_RESERVE = "build_reserve", "Building initial savings"
        DEBT_FOCUS = "debt_focus", "Emergency fund established, high-interest debt remains"
        STABLE = "stable", "Stable finances and adequate emergency reserves"
        STRONG = "strong", "Strong savings capacity"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        DISABLED = "disabled", "Disabled"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_plan"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    scenario = models.CharField(max_length=20, choices=Scenario.choices)
    name = models.CharField(max_length=120)
    objective = models.CharField(max_length=255)
    explanation = models.TextField(blank=True)
    priority = models.CharField(max_length=40, blank=True, default="")

    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_surplus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    safe_to_save = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    additional_buffer = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    rainy_day_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    investment_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    regular_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    rainy_day_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    investment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    regular_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    debt_extra_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    emergency_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    emergency_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estimated_completion_date = models.DateField(null=True, blank=True)

    warnings = models.JSONField(default=list, blank=True)
    goal_notes = models.JSONField(default=list, blank=True)
    analysis = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64, blank=True, default="")
    calculated_at = models.DateTimeField(null=True, blank=True)
    user_override_percents = models.BooleanField(
        default=False,
        help_text="When true, keep the user's edited allocation percents on recalculation.",
    )

    class Meta:
        ordering = ["-calculated_at", "-updated_at"]

    def __str__(self) -> str:
        return f"SavingsPlan<{self.user_id}> {self.scenario}"


class SavingsPlanRevision(TimeStampedModel):
    """Immutable snapshot of a prior recommendation for explainability."""

    plan = models.ForeignKey(
        SavingsPlan, on_delete=models.CASCADE, related_name="revisions"
    )
    reason = models.CharField(max_length=120, blank=True, default="")
    scenario = models.CharField(max_length=20, blank=True, default="")
    safe_to_save = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    explanation = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Revision {self.pk} for plan {self.plan_id}"
