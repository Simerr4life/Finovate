from django import forms
from django.core.exceptions import ValidationError

from .identity import normalize_phone
from .models import Profile


class RegistrationForm(forms.Form):
    """Details collected before Auth0 Universal Login. Passwords are not accepted."""

    name = forms.CharField(max_length=150, label="Name")
    email = forms.EmailField(label="Email")
    phone = forms.CharField(
        required=False,
        label="Phone number",
        help_text="Optional. Saving a number here does not prove you control that phone.",
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name or any(ord(ch) < 32 for ch in name):
            raise ValidationError("Enter your name.")
        return name

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone"))
        if phone is None:
            raise ValidationError("Enter a phone number with 8 to 15 digits, or leave it blank.")
        return phone


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
            "phone_number",
            "messaging_consent",
        ]
        help_texts = {
            "phone_number": "Optional contact number. Saving it does not verify ownership.",
            "messaging_consent": "I agree to receive Finovate messages after my phone is verified and a chat is linked.",
        }
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
    """Same fields as onboarding, plus notification choices used only in Settings."""

    class Meta(OnboardingForm.Meta):
        fields = [*OnboardingForm.Meta.fields, "theme", "notify_simulated_orders"]
        labels = {
            **OnboardingForm.Meta.labels,
            "theme": "Color theme",
            "notify_simulated_orders": "Record simulated investment proposals",
        }
