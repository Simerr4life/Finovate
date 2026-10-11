from django import forms

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


class ContributionForm(forms.ModelForm):
    class Meta:
        model = Contribution
        fields = ["kind", "amount", "note"]


class DebtObligationForm(forms.ModelForm):
    class Meta:
        model = DebtObligation
        fields = ["name", "balance", "minimum_payment", "interest_rate_apr", "is_active"]


class PlanAllocationForm(forms.Form):
    rainy_day_percent = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2)
    investment_percent = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2)
    regular_percent = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2)

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
