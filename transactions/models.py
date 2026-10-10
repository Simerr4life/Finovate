from django.conf import settings
from django.db import models

from core.models import DATA_SOURCE_CHOICES, TimeStampedModel


class Account(TimeStampedModel):
    """A container of transactions from one source statement/feed.

    Today the only account in the system is a fictional demo statement
    (see docs/demo-peachtree-account.md). This model is deliberately
    generic — a future real bank-import adapter would create rows here
    too — but it holds no credentials, ever. Compare to
    accounts.ConnectedAccountPlaceholder, which models *connection status*
    for a not-yet-built real integration and never holds transactions.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts"
    )
    institution_name = models.CharField(max_length=120)
    account_holder_name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=60)
    masked_number = models.CharField(max_length=20, help_text='e.g. "••••4821"')
    location = models.CharField(max_length=120, blank=True)
    is_demo = models.BooleanField(
        default=True,
        help_text="True for fictional/sample accounts. Always true today — no real bank is connected.",
    )

    # Statement-period bookkeeping, used for reconciliation and the
    # statement view. opening_balance is the source of truth for running
    # balances; the stated_* fields preserve what the (fictional) source
    # document claimed, so a mismatch can be surfaced rather than hidden.
    statement_start_date = models.DateField(null=True, blank=True)
    statement_end_date = models.DateField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stated_total_deposits = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stated_total_withdrawals = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stated_ending_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = [("user", "masked_number", "institution_name")]

    def __str__(self) -> str:
        return f"{self.institution_name} {self.masked_number}"


class Category(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    color = models.CharField(
        max_length=7,
        default="#6366F1",
        help_text="Hex color used for charts and badges.",
    )
    is_earned_income = models.BooleanField(
        default=True,
        help_text=(
            "Only meaningful when kind=income. False marks this category as a "
            "transfer/reimbursement/gift rather than genuine earned income, so "
            "it's excluded from 'income' totals used for budgeting while still "
            "counting toward the cash balance."
        ),
    )
    is_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "categories"
        unique_together = [("user", "name", "kind")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Transaction(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Which statement/feed this came from. Null for ad-hoc manual entries.",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Always stored as a positive amount; sign is implied by kind.",
    )
    description = models.CharField(max_length=200, blank=True)
    occurred_on = models.DateField()
    source = models.CharField(max_length=10, choices=DATA_SOURCE_CHOICES, default="manual")
    external_id = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        help_text=(
            "Identifier from an external provider, used to make imports "
            "idempotent. Null for manual/demo entries."
        ),
    )
    reverses = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversed_by",
        help_text="Set when this transaction is a refund/reversal of another transaction.",
    )
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-occurred_on", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "external_id"],
                name="unique_external_transaction_per_user",
                condition=models.Q(external_id__isnull=False),
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.kind == self.Kind.INCOME else "-"
        return f"{sign}{self.amount} {self.description or self.category}"

    @property
    def signed_amount(self):
        return self.amount if self.kind == self.Kind.INCOME else -self.amount
