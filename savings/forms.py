from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator

from .models import Contribution, DebtObligation, Goal


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ["name", "category", "color", "target_amount", "current_amount", "target_date", "is_investable"]
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "color": forms.TextInput(attrs={"type": "color"}),
        }
        labels = {
            "is_investable": "Make this an investable Savings Pool (eligible for round-ups and proposed investments)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_amount"].validators.append(
            MinValueValidator(Decimal("0.01"), "Enter a target greater than $0.00.")
        )
        self.fields["current_amount"].validators.append(
            MinValueValidator(Decimal("0"), "The current amount can't be negative.")
        )
        if self.instance.pk and self.instance.system_key:
            # Engine-managed pools are found by system_key; the investment pool
            # must stay investable for round-ups to have somewhere to go.
            if self.instance.system_key == Goal.SystemKey.INVESTMENT:
                self.fields["is_investable"].disabled = True

    def save(self, commit=True):
        goal = super().save(commit=False)
        goal.sync_achieved()
        if commit:
            goal.save()
        return goal


class ContributionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ["kind", "amount", "note"]

    def __init__(self, *args, goal=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.goal = goal
        self.fields["amount"].validators.append(
            MinValueValidator(Decimal("0.01"), "Enter an amount greater than $0.00.")
        )

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        if (
            self.goal is not None
            and cleaned.get("kind") == Contribution.Kind.WITHDRAWAL
            and amount is not None
            and amount > self.goal.current_amount
        ):
            self.add_error("amount", f"You can withdraw at most ${self.goal.current_amount} from this goal.")
        return cleaned


class DebtObligationForm(forms.ModelForm):
    class Meta:
        model = DebtObligation
        fields = ["name", "balance", "minimum_payment", "interest_rate_apr", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("balance", "minimum_payment"):
            self.fields[name].validators.append(MinValueValidator(Decimal("0"), "Enter zero or more."))
        self.fields["interest_rate_apr"].validators += [
            MinValueValidator(Decimal("0"), "Enter zero or more."),
            MaxValueValidator(Decimal("100"), "Enter an APR no higher than 100."),
        ]


class PlanAllocationForm(forms.Form):
    rainy_day_percent = forms.DecimalField(
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "data-plan-percent": "1"}),
    )
    investment_percent = forms.DecimalField(
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "data-plan-percent": "1"}),
    )
    regular_percent = forms.DecimalField(
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "100", "data-plan-percent": "1"}),
    )

    def clean(self):
        cleaned = super().clean()
        rainy = cleaned.get("rainy_day_percent")
        invest = cleaned.get("investment_percent")
        regular = cleaned.get("regular_percent")
        if None in (rainy, invest, regular):
            return cleaned
        total = rainy + invest + regular
        if abs(total - 100) > 0.05:
            raise forms.ValidationError("Allocation percentages must add up to 100%.")
        return cleaned
