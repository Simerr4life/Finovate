from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class OnboardingForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "income_cadence",
            "risk_comfort",
            "cash_reserve_target",
            "budget_warning_threshold_percent",
            "notify_budget_warnings",
            "notify_goal_milestones",
        ]
        widgets = {
            "cash_reserve_target": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "budget_warning_threshold_percent": forms.NumberInput(attrs={"min": "1", "max": "100"}),
        }
        labels = {
            "cash_reserve_target": "Cash reserve to always keep untouched ($)",
            "budget_warning_threshold_percent": "Warn me when a budget category hits (%)",
            "notify_budget_warnings": "Notify me about budget warnings",
            "notify_goal_milestones": "Notify me about savings goal milestones",
        }


class ProfileSettingsForm(OnboardingForm):
    """Same fields as onboarding, reused on the Settings page."""

    class Meta(OnboardingForm.Meta):
        pass
