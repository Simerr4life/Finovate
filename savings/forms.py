from django import forms

from .models import Contribution, Goal, SavingsPlan


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ["name", "category", "color", "target_amount", "current_amount", "target_date", "is_investable"]
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "color": forms.TextInput(attrs={"type": "color"}),
            "target_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "current_amount": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        labels = {
            "is_investable": "Make this an investable Savings Pool (eligible for round-ups and proposed investments)",
        }
        help_texts = {
            "target_amount": "Use 0 if you haven't picked a target yet.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.is_default_pool:
            # A default pool's balance only changes through recorded
            # deposits and withdrawals, so its history stays accurate.
            self.fields.pop("current_amount")
            self.fields.pop("category")

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise forms.ValidationError("Give this pool a name.")
        return name

    def clean_target_amount(self):
        value = self.cleaned_data["target_amount"]
        if value < 0:
            raise forms.ValidationError("A target can't be negative.")
        return value

    def clean_current_amount(self):
        value = self.cleaned_data["current_amount"]
        if value < 0:
            raise forms.ValidationError("A balance can't be negative.")
        return value


class ContributionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ["kind", "amount", "note"]
        widgets = {"amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"})}

    def __init__(self, *args, goal=None, **kwargs):
        self.goal = goal
        super().__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount

    def clean(self):
        cleaned = super().clean()
        if (
            self.goal is not None
            and cleaned.get("kind") == Contribution.Kind.WITHDRAWAL
            and cleaned.get("amount")
            and cleaned["amount"] > self.goal.current_amount
        ):
            self.add_error("amount", f"You can withdraw at most ${self.goal.current_amount:,.2f} from this pool.")
        return cleaned


class SavingsPlanForm(forms.ModelForm):
    class Meta:
        model = SavingsPlan
        fields = ["rainy_day_percent", "investment_percent", "regular_percent", "cadence", "status"]
        labels = {
            "rainy_day_percent": "Rainy Day (%)",
            "investment_percent": "Investment (%)",
            "regular_percent": "Regular Savings (%)",
            "cadence": "Contribution schedule",
            "status": "Plan status",
        }
        widgets = {
            "rainy_day_percent": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "1", "data-plan-percent": ""}),
            "investment_percent": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "1", "data-plan-percent": ""}),
            "regular_percent": forms.NumberInput(attrs={"min": "0", "max": "100", "step": "1", "data-plan-percent": ""}),
        }

    def clean(self):
        cleaned = super().clean()
        names = ["rainy_day_percent", "investment_percent", "regular_percent"]
        values = [cleaned.get(name) for name in names]
        if any(v is None for v in values):
            return cleaned
        for name, value in zip(names, values):
            if value > 100:
                self.add_error(name, "Use a whole number from 0 to 100.")
        total = sum(values)
        if total != 100:
            raise forms.ValidationError(f"The three percentages must add up to 100% (they add up to {total}%).")
        return cleaned
