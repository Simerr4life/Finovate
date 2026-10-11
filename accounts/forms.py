from decimal import Decimal

from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from .identity import normalize_phone
from .models import Profile

MAX_REASONABLE_AMOUNT = Decimal("10000000")


def _money_field(label, help_text="", required=False):
    return forms.DecimalField(
        label=label,
        help_text=help_text,
        required=required,
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(MAX_REASONABLE_AMOUNT)],
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
    )


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


class EmailSignUpForm(forms.Form):
    """Email-and-password registration. Supabase stores the password."""

    name = forms.CharField(max_length=150, label="Name")
    email = forms.EmailField(label="Email")
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password and password != cleaned.get("password2"):
            self.add_error("password2", "The two passwords don't match.")
        elif password:
            try:
                password_validation.validate_password(password)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class EmailLoginForm(forms.Form):
    email = forms.CharField(label="Email", max_length=254, widget=forms.TextInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class DisplayNameForm(forms.Form):
    """Changes only the user's display name: never email, username, or credentials."""

    name = forms.CharField(
        max_length=150,
        label="Display name",
        widget=forms.TextInput(attrs={"autocomplete": "name", "maxlength": "150"}),
    )

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        if not name:
            raise ValidationError("Enter a name.")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            raise ValidationError("Use letters, numbers, and ordinary punctuation only.")
        first, _, rest = name.partition(" ")
        if len(first) > 150 or len(rest) > 150:
            raise ValidationError("That name is too long.")
        return name


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
            "phone_number": "Phone number",
            "messaging_consent": "I agree to Finovate messages",
        }

    def clean_phone_number(self):
        phone = normalize_phone(self.cleaned_data.get("phone_number"))
        if phone is None:
            raise ValidationError("Enter a phone number with 8 to 15 digits, or leave it blank.")
        return phone

    def save(self, commit=True):
        profile = super().save(commit=False)
        if profile.pk:
            previous = Profile.objects.get(pk=profile.pk)
            if profile.phone_number != previous.phone_number:
                profile.phone_verified = False
        if commit:
            profile.save()
        return profile


class ManualSetupForm(forms.Form):
    """A deliberately shallow form: the two 'minimum' fields plus an
    optional breakdown, submitted as one page rather than a multi-step
    questionnaire. Every field is optional -- a user can set just one
    number (e.g. only a minimum cash reserve) and submit.
    """

    take_home_income = _money_field("Monthly take-home income ($)")
    additional_income = _money_field("Additional monthly income ($)", "Side income, benefits, etc. -- optional.")
    total_monthly_expenses = _money_field(
        "Total monthly expenses ($)",
        "Use this, or break it down by category below -- not both.",
    )

    housing = _money_field("Housing")
    utilities = _money_field("Utilities & internet")
    groceries = _money_field("Groceries & household essentials")
    transportation = _money_field("Transportation")
    insurance = _money_field("Insurance & healthcare")
    debt_payments = _money_field("Debt & loan payments")
    subscriptions = _money_field("Subscriptions & recurring bills")
    other_expenses = _money_field("Other monthly costs")

    current_savings_balance = _money_field("Current savings balance ($)", "If you know it -- optional.")
    minimum_cash_reserve = _money_field(
        "Minimum cash reserve to always keep ($)",
        "Finovate won't suggest investing below this amount.",
    )
    monthly_savings_goal = _money_field("Monthly savings goal ($)", "How much you'd like to save each month.")

    @property
    def breakdown_fields(self):
        names = [
            "housing", "utilities", "groceries", "transportation",
            "insurance", "debt_payments", "subscriptions", "other_expenses",
        ]
        return [self[name] for name in names]


class ProfileSettingsForm(OnboardingForm):
    """Same fields as onboarding, plus notification choices used only in Settings."""

    class Meta(OnboardingForm.Meta):
        fields = [*OnboardingForm.Meta.fields, "theme", "notify_simulated_orders"]
        labels = {
            **OnboardingForm.Meta.labels,
            "theme": "Color theme",
            "notify_simulated_orders": "Record simulated investment proposals",
        }
