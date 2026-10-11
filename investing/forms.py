from datetime import date

from django import forms

from .models import MarketPrice, RoundUpSettings


class RoundUpSettingsForm(forms.ModelForm):
    class Meta:
        model = RoundUpSettings
        fields = [
            "enabled",
            "is_paused",
            "round_to",
            "contribution_cap_per_period",
            "minimum_cash_reserve",
            "target_pool",
        ]
        labels = {
            "enabled": "Enable round-up investing (simulated)",
            "is_paused": "Pause round-ups (keeps settings, stops new sweeps)",
            "round_to": "Round purchases up to the nearest ($)",
            "contribution_cap_per_period": "Cap on round-ups swept per period ($, optional)",
            "minimum_cash_reserve": "Never sweep below this cash reserve ($)",
            "target_pool": "Invest round-ups into this Savings Pool",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            from savings.models import Goal

            self.fields["target_pool"].queryset = Goal.objects.filter(user=user, is_investable=True)
            self.fields["target_pool"].required = False
            self.fields["target_pool"].empty_label = "General / unassigned"


class HypotheticalScenarioForm(forms.Form):
    """Inputs for the illustrative Oct 6, 2026 "what if" calculator.

    Prices are typed in by the user and are not checked against market data.
    """

    symbol = forms.CharField(max_length=20, initial="VTI", label="Symbol (any label — not validated against a real market)")
    amount_invested = forms.DecimalField(max_digits=12, decimal_places=2, initial=200, min_value=0.01, label="Hypothetical amount invested ($)")
    invest_date = forms.DateField(initial=date(2026, 9, 30), widget=forms.DateInput(attrs={"type": "date"}), label="Hypothetical investment date")
    invest_price = forms.DecimalField(max_digits=12, decimal_places=4, min_value=0.0001, label="Price per share on investment date ($, you supply — unverified)")
    valuation_date = forms.DateField(initial=date(2026, 10, 6), widget=forms.DateInput(attrs={"type": "date"}), label="Valuation date")
    valuation_price = forms.DecimalField(max_digits=12, decimal_places=4, min_value=0.0001, label="Price per share on valuation date ($, you supply — unverified)")


class VerifiedScenarioForm(forms.Form):
    """Same hypothetical-gain calculation, but prices come from actual
    Twelve Data MarketPrice rows instead of free-text entry. Still
    hypothetical — no real purchase happened.
    """

    invest_row = forms.ModelChoiceField(
        queryset=MarketPrice.objects.filter(is_verified=True, is_twelve_data=True),
        label="Investment date (Twelve Data price)",
        help_text="Pick a Twelve Data daily bar to use as the hypothetical buy price.",
    )
    valuation_row = forms.ModelChoiceField(
        queryset=MarketPrice.objects.filter(is_verified=True, is_twelve_data=True),
        label="Valuation date (Twelve Data price)",
        help_text="Must be the same symbol as the investment-date row.",
    )
    amount_invested = forms.DecimalField(max_digits=12, decimal_places=2, initial=200, min_value=0.01, label="Hypothetical amount invested ($)")

    def clean(self):
        cleaned = super().clean()
        invest_row = cleaned.get("invest_row")
        valuation_row = cleaned.get("valuation_row")
        if invest_row and valuation_row and invest_row.symbol != valuation_row.symbol:
            raise forms.ValidationError("Choose two rows for the same symbol to compare a before/after price.")
        if invest_row and valuation_row and invest_row.date >= valuation_row.date:
            raise forms.ValidationError("The investment-date row must be earlier than the valuation-date row.")
        return cleaned
