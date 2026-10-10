from django import forms

from transactions.models import Category, Transaction

from .models import Budget, BudgetPeriod, IncomeSource, RecurringExpense


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


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class BudgetPeriodForm(forms.ModelForm):
    class Meta:
        model = BudgetPeriod
        fields = ["name", "start_date", "end_date", "is_active"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


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


class IncomeSourceForm(forms.ModelForm):
    class Meta:
        model = IncomeSource
        fields = ["name", "amount", "cadence", "is_active"]


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
