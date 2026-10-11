"""Manual income/expense setup: turns the quick-setup form into the same
IncomeSource/RecurringExpense rows the budgets app already reads, so
budgets.services.build_budget_plan is the one and only surplus/shortfall
calculation -- this module never computes its own estimate.

Every row this writes gets an "(estimate)" suffix on its name, which is
how a manually-declared figure is distinguished from anything else in the
budgets UI, without adding a source column to IncomeSource/RecurringExpense.
"""


from django.utils import timezone

from budgets.models import IncomeSource, RecurringExpense

TAKE_HOME_INCOME_NAME = "Take-home income (estimate)"
ADDITIONAL_INCOME_NAME = "Additional income (estimate)"
TOTAL_EXPENSES_NAME = "Total monthly expenses (estimate)"

BREAKDOWN_EXPENSE_NAMES = {
    "housing": "Housing (estimate)",
    "utilities": "Utilities & internet (estimate)",
    "groceries": "Groceries & household essentials (estimate)",
    "transportation": "Transportation (estimate)",
    "insurance": "Insurance & healthcare (estimate)",
    "debt_payments": "Debt & loan payments (estimate)",
    "subscriptions": "Subscriptions & recurring bills (estimate)",
    "other_expenses": "Other monthly costs (estimate)",
}

ALL_MANUAL_EXPENSE_NAMES = [TOTAL_EXPENSES_NAME, *BREAKDOWN_EXPENSE_NAMES.values()]


def _set_income_source(user, name, amount):
    if amount and amount > 0:
        IncomeSource.objects.update_or_create(
            user=user, name=name, defaults={"amount": amount, "cadence": "monthly", "is_active": True},
        )
    else:
        IncomeSource.objects.filter(user=user, name=name).update(is_active=False)


def _set_recurring_expense(user, name, amount):
    if amount and amount > 0:
        RecurringExpense.objects.update_or_create(
            user=user, name=name, defaults={"amount": amount, "cadence": "monthly", "is_active": True},
        )
    else:
        RecurringExpense.objects.filter(user=user, name=name).update(is_active=False)


def apply_manual_setup(user, cleaned_data: dict) -> None:
    """Writes the quick-setup form's cleaned_data as IncomeSource,
    RecurringExpense, and Profile rows. Idempotent: resubmitting the form
    (e.g. to update one number) updates the same reserved-name rows rather
    than piling up duplicates.
    """
    _set_income_source(user, TAKE_HOME_INCOME_NAME, cleaned_data.get("take_home_income"))
    _set_income_source(user, ADDITIONAL_INCOME_NAME, cleaned_data.get("additional_income"))

    breakdown_values = {
        field: cleaned_data.get(field) for field in BREAKDOWN_EXPENSE_NAMES
    }
    breakdown_used = any(v and v > 0 for v in breakdown_values.values())

    if breakdown_used:
        # Breakdown takes precedence over the lump total -- never both, to
        # avoid double-counting the same expenses two different ways.
        for field, name in BREAKDOWN_EXPENSE_NAMES.items():
            _set_recurring_expense(user, name, breakdown_values[field])
        _set_recurring_expense(user, TOTAL_EXPENSES_NAME, None)
    else:
        _set_recurring_expense(user, TOTAL_EXPENSES_NAME, cleaned_data.get("total_monthly_expenses"))
        for name in BREAKDOWN_EXPENSE_NAMES.values():
            _set_recurring_expense(user, name, None)

    profile = user.profile
    update_fields = ["updated_at"]

    savings_balance = cleaned_data.get("current_savings_balance")
    if savings_balance is not None:
        profile.manual_savings_balance = savings_balance
        profile.manual_savings_balance_updated_at = timezone.now()
        update_fields += ["manual_savings_balance", "manual_savings_balance_updated_at"]

    reserve = cleaned_data.get("minimum_cash_reserve")
    if reserve is not None:
        profile.cash_reserve_target = reserve
        update_fields.append("cash_reserve_target")

    savings_goal = cleaned_data.get("monthly_savings_goal")
    if savings_goal is not None:
        profile.manual_monthly_savings_goal = savings_goal
        update_fields.append("manual_monthly_savings_goal")

    profile.manual_setup_completed_at = timezone.now()
    update_fields.append("manual_setup_completed_at")
    profile.save(update_fields=update_fields)


def initial_from_existing(user) -> dict:
    """Prefill values for re-opening the form (e.g. from Settings to
    update one number) from whatever was saved last time."""
    initial = {}

    def _income_amount(name):
        row = IncomeSource.objects.filter(user=user, name=name, is_active=True).first()
        return row.amount if row else None

    initial["take_home_income"] = _income_amount(TAKE_HOME_INCOME_NAME)
    initial["additional_income"] = _income_amount(ADDITIONAL_INCOME_NAME)

    breakdown_rows = {
        field: RecurringExpense.objects.filter(user=user, name=name, is_active=True).first()
        for field, name in BREAKDOWN_EXPENSE_NAMES.items()
    }
    if any(breakdown_rows.values()):
        for field, row in breakdown_rows.items():
            initial[field] = row.amount if row else None
    else:
        total_row = RecurringExpense.objects.filter(user=user, name=TOTAL_EXPENSES_NAME, is_active=True).first()
        initial["total_monthly_expenses"] = total_row.amount if total_row else None

    profile = user.profile
    initial["current_savings_balance"] = profile.manual_savings_balance
    initial["minimum_cash_reserve"] = profile.cash_reserve_target or None
    initial["monthly_savings_goal"] = profile.manual_monthly_savings_goal
    return initial


def has_manual_estimate(user) -> bool:
    return (
        IncomeSource.objects.filter(
            user=user, name__in=[TAKE_HOME_INCOME_NAME, ADDITIONAL_INCOME_NAME], is_active=True
        ).exists()
        or RecurringExpense.objects.filter(
            user=user, name__in=ALL_MANUAL_EXPENSE_NAMES, is_active=True
        ).exists()
        or user.profile.manual_savings_balance is not None
    )
