from django import forms

from .models import Contribution, Goal


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
