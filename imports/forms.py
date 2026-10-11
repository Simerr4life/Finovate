from django import forms

from transactions.models import Account

from .pipeline import COLUMN_ALIASES, REQUIRED_ROLES

MAX_UPLOAD_BYTES = 2_000_000


class UploadForm(forms.Form):
    file = forms.FileField(label="Statement file (CSV)")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"That file is too large ({upload.size:,} bytes). The limit is {MAX_UPLOAD_BYTES:,} bytes."
            )
        return upload


class AccountSelectForm(forms.Form):
    existing_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        required=False,
        label="Use an existing account",
        empty_label="— Create a new account instead —",
    )
    institution_name = forms.CharField(max_length=120, required=False, label="Institution name")
    account_type = forms.CharField(max_length=60, required=False, label="Account type", initial="Checking")
    masked_number = forms.CharField(
        max_length=20, required=False, label="Last 4 digits",
        help_text='Only the last 4 digits, e.g. "4821". Never the full account number.',
    )
    opening_balance = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, initial=0,
        label="Opening balance ($)",
        help_text="The balance immediately before this statement's first transaction.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["existing_account"].queryset = Account.objects.filter(user=user)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("existing_account"):
            return cleaned
        for field_name in ("institution_name", "account_type", "masked_number"):
            if not cleaned.get(field_name):
                self.add_error(field_name, "Required when creating a new account.")
        masked = cleaned.get("masked_number") or ""
        if masked and (not masked.isdigit() or len(masked) > 6):
            self.add_error("masked_number", "Enter only the last few digits of the account number.")
        return cleaned


ROLE_LABELS = {
    "date": "Transaction date",
    "posting_date": "Posting date (optional)",
    "description": "Description / merchant",
    "amount": "Amount (single signed column)",
    "debit": "Debit / withdrawal amount",
    "credit": "Credit / deposit amount",
    "balance": "Balance after transaction (optional)",
    "reference": "Transaction reference / ID (optional)",
    "currency": "Currency (optional)",
}

NOT_PRESENT = ""


def build_column_mapping_form(headers: list[str], initial: dict, data=None) -> forms.Form:
    """A Form built at request time, since its fields depend on the
    uploaded file's actual header row."""
    choices = [(NOT_PRESENT, "— Not present —")] + [(h, h) for h in headers]
    fields = {}
    for role in COLUMN_ALIASES:
        fields[role] = forms.ChoiceField(
            choices=choices,
            required=role in REQUIRED_ROLES,
            label=ROLE_LABELS.get(role, role),
            initial=initial.get(role, NOT_PRESENT),
        )
    form_class = type("ColumnMappingForm", (forms.Form,), fields)
    return form_class(data=data, initial=initial)
