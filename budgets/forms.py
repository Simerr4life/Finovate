from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from transactions.models import Category, Transaction

from .models import Budget, BudgetPeriod, IncomeSource, RecurringExpense

MIN_AMOUNT = Decimal("0.01")


def _require_positive(form, *names):
    for name in names:
        field = form.fields[name]
        field.validators.append(MinValueValidator(MIN_AMOUNT, "Enter an amount greater than $0.00."))
        field.widget.attrs.setdefault("min", "0.01")
        field.widget.attrs.setdefault("step", "0.01")


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["kind", "category", "amount", "description", "occurred_on"]
        widgets = {"occurred_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].queryset = Category.objects.filter(user=user)
        self.fields["category"].required = False
        # Amounts are stored positive; kind carries the sign.
        _require_positive(self, "amount")

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        kind = cleaned.get("kind")
        if category and kind and category.kind != kind:
            self.add_error("category", f"{category.name} is an {category.get_kind_display().lower()} category.")
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        kind = cleaned.get("kind")
        # user isn't a form field, so ModelForm's own unique check skips
        # (user, name, kind); without this the save would hit the DB constraint.
        if self.user is not None and name and kind:
            if Category.objects.filter(user=self.user, name__iexact=name, kind=kind).exists():
                self.add_error("name", "You already have a category with that name.")
        return cleaned


class BudgetPeriodForm(forms.ModelForm):
    class Meta:
        model = BudgetPeriod
        fields = ["name", "start_date", "end_date", "is_active"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "The end date must be on or after the start date.")
        return cleaned


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["period", "category", "limit_amount", "warning_threshold_percent"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["period"].queryset = BudgetPeriod.objects.filter(user=user)
            self.fields["category"].queryset = Category.objects.filter(
                user=user, kind=Category.Kind.EXPENSE
            )
            if not self.is_bound and self.instance.pk is None:
                self.initial.setdefault(
                    "warning_threshold_percent", user.profile.budget_warning_threshold_percent
                )
        _require_positive(self, "limit_amount")
        threshold = self.fields["warning_threshold_percent"]
        threshold.validators += [MinValueValidator(1), MaxValueValidator(100)]
        threshold.widget.attrs.update({"min": "1", "max": "100"})


class IncomeSourceForm(forms.ModelForm):
    class Meta:
        model = IncomeSource
        fields = ["name", "amount", "cadence", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _require_positive(self, "amount")


class RecurringExpenseForm(forms.ModelForm):
    class Meta:
        model = RecurringExpense
        fields = ["name", "category", "amount", "cadence", "is_active"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["category"].queryset = Category.objects.filter(
                user=user, kind=Category.Kind.EXPENSE
            )
        _require_positive(self, "amount")
