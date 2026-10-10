from django.conf import settings
from django.db import models

from core.models import TimeStampedModel
from transactions.models import Category


class IncomeSource(TimeStampedModel):
    """A recurring (or one-off) income the budget plan should account for."""

    CADENCE_CHOICES = [
        ("weekly", "Weekly"),
        ("biweekly", "Every two weeks"),
        ("monthly", "Monthly"),
        ("irregular", "Irregular"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="income_sources"
    )
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    cadence = models.CharField(max_length=20, choices=CADENCE_CHOICES, default="monthly")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.amount}/{self.cadence})"


class RecurringExpense(TimeStampedModel):
    CADENCE_CHOICES = IncomeSource.CADENCE_CHOICES

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurring_expenses"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    cadence = models.CharField(max_length=20, choices=CADENCE_CHOICES, default="monthly")
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.amount}/{self.cadence})"


class BudgetPeriod(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budget_periods"
    )
    name = models.CharField(max_length=100, help_text='e.g. "October 2026"')
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self) -> str:
        return self.name


class Budget(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets"
    )
    period = models.ForeignKey(
        BudgetPeriod, on_delete=models.CASCADE, related_name="budgets"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="budgets"
    )
    limit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    warning_threshold_percent = models.PositiveSmallIntegerField(default=80)

    class Meta:
        unique_together = [("period", "category")]

    def __str__(self) -> str:
        return f"{self.category} limit {self.limit_amount} ({self.period})"
