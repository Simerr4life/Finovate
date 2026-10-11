from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import DATA_SOURCE_CHOICES, TimeStampedModel


class Goal(TimeStampedModel):
    class PoolKind(models.TextChoices):
        CUSTOM = "", "Custom pool"
        RAINY_DAY = "rainy_day", "Rainy Day"
        INVESTMENT = "investment", "Investment"
        REGULAR = "regular", "Regular Savings"

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
    pool_kind = models.CharField(
        max_length=20,
        choices=PoolKind.choices,
        default=PoolKind.CUSTOM,
        blank=True,
        help_text=(
            "Set only on the three default pools every user gets. A database "
            "constraint keeps each kind unique per user, so re-running "
            "initialization can never create a duplicate."
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
                fields=["user", "pool_kind"],
                condition=~models.Q(pool_kind=""),
                name="unique_default_pool_per_user",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_default_pool(self) -> bool:
        return bool(self.pool_kind)

    @property
    def has_target(self) -> bool:
        return self.target_amount > 0

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


class SavingsPlan(TimeStampedModel):
    """One automated savings plan per user.

    Holds the user's allocation split across the three default pools and
    the last calculated snapshot. The snapshot is a *recommendation*: it
    never moves money and is never counted as a deposit. Money only lands
    in a pool through a recorded Contribution.
    """

    class Cadence(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        WEEKLY = "weekly", "Weekly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        DISABLED = "disabled", "Disabled"

    class Basis(models.TextChoices):
        NONE = "", "Not enough information"
        DECLARED = "declared", "Declared income and expenses"
        RECORDED = "recorded", "Recorded transactions"

    DEFAULT_PERCENTS = {"rainy_day": 40, "investment": 20, "regular": 40}

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="savings_plan"
    )
    rainy_day_percent = models.PositiveSmallIntegerField(default=40)
    investment_percent = models.PositiveSmallIntegerField(default=20)
    regular_percent = models.PositiveSmallIntegerField(default=40)
    cadence = models.CharField(max_length=10, choices=Cadence.choices, default=Cadence.MONTHLY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    # Snapshot of the last calculation, so changes can be detected and the
    # user notified exactly once per real change.
    basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.NONE, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    monthly_costs = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    available_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shortfall_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    recalculated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"SavingsPlan<{self.user_id}>"

    def percents(self) -> dict[str, int]:
        return {
            Goal.PoolKind.RAINY_DAY: self.rainy_day_percent,
            Goal.PoolKind.INVESTMENT: self.investment_percent,
            Goal.PoolKind.REGULAR: self.regular_percent,
        }

    def clean(self):
        total = self.rainy_day_percent + self.investment_percent + self.regular_percent
        if total != 100:
            raise ValidationError(f"Allocation percentages must add up to 100% (currently {total}%).")


class SavingsPlanAllocation(TimeStampedModel):
    """The recommended contribution to one pool. A projection, not a transfer."""

    plan = models.ForeignKey(SavingsPlan, on_delete=models.CASCADE, related_name="allocations")
    pool = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="plan_allocations")
    percent = models.PositiveSmallIntegerField()
    recommended_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "pool"], name="unique_allocation_per_plan_pool"),
        ]

    def __str__(self) -> str:
        return f"{self.pool} {self.percent}% = {self.recommended_monthly}/mo"
