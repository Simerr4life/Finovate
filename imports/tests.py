from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from transactions.models import Account, Transaction
from transactions.services import record_transaction

from . import pipeline
from .forms import MAX_UPLOAD_BYTES
from .models import ImportBatch

SIMPLE_CSV = (
    "Date,Description,Amount\n"
    "2026-01-05,Coffee Shop,-4.35\n"
    "2026-01-06,Paycheck,2000.00\n"
)

DEBIT_CREDIT_CSV = (
    "Transaction Date,Memo,Debit,Credit\n"
    "01/05/2026,Coffee Shop,4.35,\n"
    "01/06/2026,Paycheck,,2000.00\n"
)

# The exact real-world header style from the spec: Money_In_USD/Money_Out_USD.
MONEY_IN_OUT_CSV = (
    "Date,Description,Money_In_USD,Money_Out_USD\n"
    "2026-01-05,Coffee Shop,,4.35\n"
    "2026-01-06,Paycheck,2000.00,\n"
)

UNREADABLE_CSV = "Just,Some,Random,Headers\nfoo,bar,baz,qux\n"


class PipelineValidationTests(TestCase):
    def test_rejects_empty_file(self):
        with self.assertRaises(pipeline.ImportValidationError):
            pipeline.validate_file("x.csv", b"", 2_000_000)

    def test_rejects_oversized_file(self):
        with self.assertRaises(pipeline.ImportValidationError):
            pipeline.validate_file("x.csv", b"a" * 100, max_bytes=10)

    def test_rejects_binary_content_regardless_of_extension(self):
        # A renamed binary (e.g. .exe/.pdf) must fail on content, not pass
        # just because the filename says .csv.
        binary = bytes(range(0, 20)) * 5
        with self.assertRaises(pipeline.ImportValidationError):
            pipeline.validate_file("statement.csv", binary, 2_000_000)

    def test_accepts_valid_csv_text(self):
        text = pipeline.validate_file("x.csv", SIMPLE_CSV.encode("utf-8"), 2_000_000)
        self.assertIn("Coffee Shop", text)

    def test_rejects_single_column_file(self):
        with self.assertRaises(pipeline.ImportValidationError):
            pipeline.validate_file("x.csv", b"just one column\nvalue\n", 2_000_000)


class ColumnDetectionTests(TestCase):
    def test_detects_common_header_aliases(self):
        mapping = pipeline.detect_columns(["Transaction Date", "Memo", "Debit", "Credit"])
        self.assertEqual(mapping["date"], "Transaction Date")
        self.assertEqual(mapping["description"], "Memo")
        self.assertEqual(mapping["debit"], "Debit")
        self.assertEqual(mapping["credit"], "Credit")

    def test_detects_single_amount_column(self):
        mapping = pipeline.detect_columns(["Date", "Description", "Amount"])
        self.assertEqual(mapping["amount"], "Amount")

    def test_detects_underscored_money_in_out_headers(self):
        mapping = pipeline.detect_columns(["Date", "Description", "Money_In_USD", "Money_Out_USD"])
        self.assertEqual(mapping["credit"], "Money_In_USD")
        self.assertEqual(mapping["debit"], "Money_Out_USD")

    def test_detects_amount_usd_and_net_amount_usd(self):
        mapping = pipeline.detect_columns(["Date", "Description", "Amount_USD", "Net_Amount_USD", "Running_Balance_USD"])
        self.assertEqual(mapping["amount"], "Amount_USD")
        self.assertEqual(mapping["net_amount"], "Net_Amount_USD")
        self.assertEqual(mapping["balance"], "Running_Balance_USD")

    def test_optional_metadata_columns_are_not_required_and_dont_break_detection(self):
        headers = ["Date", "Description", "Amount", "Category", "Transaction_Type", "Recurring", "Payment_Method", "Month", "Is_Income"]
        mapping = pipeline.detect_columns(headers)
        problems = pipeline.validate_mapping(mapping)
        self.assertEqual(problems, [])

    def test_validate_mapping_requires_amount_or_debit_credit(self):
        problems = pipeline.validate_mapping({"date": "Date", "description": "Description"})
        self.assertTrue(any("amount" in p.lower() for p in problems))


class ParseRowsTests(TestCase):
    def test_single_signed_amount_column(self):
        rows = pipeline.parse_rows(SIMPLE_CSV, {"date": "Date", "description": "Description", "amount": "Amount"})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].kind, "expense")
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[1].kind, "income")
        self.assertEqual(rows[1].amount, Decimal("2000.00"))

    def test_debit_credit_columns_and_alternate_date_format(self):
        mapping = {"date": "Transaction Date", "description": "Memo", "debit": "Debit", "credit": "Credit"}
        rows = pipeline.parse_rows(DEBIT_CREDIT_CSV, mapping)
        self.assertEqual(rows[0].kind, "expense")
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[1].kind, "income")
        self.assertEqual(rows[1].amount, Decimal("2000.00"))

    def test_money_in_money_out_style_columns(self):
        mapping = pipeline.detect_columns(["Date", "Description", "Money_In_USD", "Money_Out_USD"])
        rows = pipeline.parse_rows(MONEY_IN_OUT_CSV, mapping)
        self.assertEqual(rows[0].kind, "expense")
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[1].kind, "income")
        self.assertEqual(rows[1].amount, Decimal("2000.00"))

    def test_parenthesized_negative_amount_is_a_refund_style_expense_reversal(self):
        csv_text = "Date,Description,Amount\n2026-01-05,Refund,(12.50)\n"
        rows = pipeline.parse_rows(csv_text, {"date": "Date", "description": "Description", "amount": "Amount"})
        self.assertEqual(rows[0].kind, "expense")
        self.assertEqual(rows[0].amount, Decimal("12.50"))

    def test_unparseable_date_is_flagged_not_crashed(self):
        csv_text = "Date,Description,Amount\nnot-a-date,Mystery,10.00\n"
        rows = pipeline.parse_rows(csv_text, {"date": "Date", "description": "Description", "amount": "Amount"})
        self.assertTrue(rows[0].errors)
        self.assertTrue(rows[0].needs_review)

    def test_non_assumed_currency_is_flagged_for_review(self):
        csv_text = "Date,Description,Amount,Currency\n2026-01-05,Paris hotel,10.00,EUR\n"
        mapping = {"date": "Date", "description": "Description", "amount": "Amount", "currency": "Currency"}
        rows = pipeline.parse_rows(csv_text, mapping)
        self.assertTrue(rows[0].errors)
        self.assertTrue(rows[0].needs_review)

    def test_both_debit_and_credit_filled_is_flagged(self):
        csv_text = "Date,Description,Debit,Credit\n2026-01-05,Weird,5.00,5.00\n"
        mapping = {"date": "Date", "description": "Description", "debit": "Debit", "credit": "Credit"}
        rows = pipeline.parse_rows(csv_text, mapping)
        self.assertTrue(rows[0].errors)

    def test_amount_usd_and_running_balance_usd_does_not_double_count(self):
        # Running_Balance_USD must never be treated as a second amount.
        csv_text = "Date,Description,Amount_USD,Running_Balance_USD\n2026-01-05,Coffee,-4.35,95.65\n"
        mapping = pipeline.detect_columns(["Date", "Description", "Amount_USD", "Running_Balance_USD"])
        rows = pipeline.parse_rows(csv_text, mapping)
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[0].balance_after, Decimal("95.65"))
        self.assertFalse(rows[0].errors)

    def test_agreeing_amount_usd_and_net_amount_usd_is_used_once(self):
        csv_text = "Date,Description,Amount_USD,Net_Amount_USD\n2026-01-05,Coffee,-4.35,-4.35\n"
        mapping = pipeline.detect_columns(["Date", "Description", "Amount_USD", "Net_Amount_USD"])
        rows = pipeline.parse_rows(csv_text, mapping)
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[0].kind, "expense")
        self.assertFalse(rows[0].errors)

    def test_disagreeing_amount_usd_and_net_amount_usd_is_flagged_not_guessed(self):
        csv_text = "Date,Description,Amount_USD,Net_Amount_USD\n2026-01-05,Coffee,-4.35,-9.99\n"
        mapping = pipeline.detect_columns(["Date", "Description", "Amount_USD", "Net_Amount_USD"])
        rows = pipeline.parse_rows(csv_text, mapping)
        self.assertIsNone(rows[0].amount)
        self.assertTrue(rows[0].errors)
        self.assertTrue(rows[0].needs_review)

    def test_zero_amount_is_flagged_for_review(self):
        csv_text = "Date,Description,Amount\n2026-01-05,Zero,0.00\n"
        rows = pipeline.parse_rows(csv_text, {"date": "Date", "description": "Description", "amount": "Amount"})
        self.assertTrue(rows[0].errors)


class DuplicateDetectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345")
        self.account = Account.objects.create(
            user=self.user, institution_name="Test Bank", account_holder_name="Alice",
            account_type="Checking", masked_number="••••0001",
        )

    def test_reference_column_dedupes_against_existing_transaction(self):
        record_transaction(
            self.user, kind=Transaction.Kind.EXPENSE, amount=Decimal("4.35"),
            occurred_on="2026-01-05", source="imported", external_id="csv:ref-1", account=self.account,
        )
        csv_text = "Date,Description,Amount,Ref\n2026-01-05,Coffee Shop,-4.35,ref-1\n"
        mapping = {"date": "Date", "description": "Description", "amount": "Amount", "reference": "Ref"}
        rows = pipeline.parse_rows(csv_text, mapping, account_id=self.account.id)
        pipeline.detect_duplicates(rows, self.account)
        self.assertTrue(rows[0].is_duplicate)

    def test_two_identical_new_rows_sharing_a_fingerprint_are_ambiguous_not_deduped(self):
        csv_text = (
            "Date,Description,Amount\n"
            "2026-01-05,Coffee Shop,-4.35\n"
            "2026-01-05,Coffee Shop,-4.35\n"
        )
        mapping = {"date": "Date", "description": "Description", "amount": "Amount"}
        rows = pipeline.parse_rows(csv_text, mapping, account_id=self.account.id)
        pipeline.detect_duplicates(rows, self.account)
        self.assertTrue(rows[0].is_ambiguous)
        self.assertTrue(rows[1].is_ambiguous)
        self.assertFalse(rows[0].is_duplicate)

    def test_distinct_rows_are_untouched(self):
        csv_text = (
            "Date,Description,Amount\n"
            "2026-01-05,Coffee Shop,-4.35\n"
            "2026-01-06,Groceries,-20.00\n"
        )
        mapping = {"date": "Date", "description": "Description", "amount": "Amount"}
        rows = pipeline.parse_rows(csv_text, mapping, account_id=self.account.id)
        pipeline.detect_duplicates(rows, self.account)
        self.assertFalse(any(r.is_duplicate or r.is_ambiguous for r in rows))


class ImportWizardViewTests(TestCase):
    """Covers the simplified flow: upload -> (auto-detected) -> account ->
    preview -> confirm. There is no column-mapping page in this flow."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345")
        self.client.login(username="alice", password="pw12345")

    def _upload(self, content=SIMPLE_CSV, filename="statement.csv", **extra):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload_file = SimpleUploadedFile(filename, content.encode("utf-8"), content_type="text/csv")
        return self.client.post(reverse("imports:upload"), {"file": upload_file, **extra})

    def _choose_new_account(self, batch):
        return self.client.post(
            reverse("imports:choose_account", kwargs={"pk": batch.pk}),
            {"institution_name": "Test Bank", "account_type": "Checking",
             "masked_number": "0001", "opening_balance": "100.00"},
        )

    def test_oversized_upload_is_rejected_with_no_batch_created(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        big = SimpleUploadedFile("big.csv", b"a" * (MAX_UPLOAD_BYTES + 1), content_type="text/csv")
        response = self.client.post(reverse("imports:upload"), {"file": big})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_empty_file_shows_the_unreadable_page_with_manual_entry_option(self):
        response = self._upload(content="", filename="empty.csv")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "imports/unreadable.html")
        self.assertContains(response, "We couldn")
        self.assertContains(response, "Enter finances manually")
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_file_with_no_recognizable_columns_shows_the_unreadable_page(self):
        response = self._upload(content=UNREADABLE_CSV, filename="mystery.csv")
        self.assertTemplateUsed(response, "imports/unreadable.html")
        self.assertEqual(ImportBatch.objects.count(), 0)

    def test_unreadable_page_never_shows_a_stack_trace(self):
        response = self._upload(content=UNREADABLE_CSV, filename="mystery.csv")
        content = response.content.decode()
        self.assertNotIn("Traceback", content)
        self.assertNotIn("Exception", content)

    def test_readable_file_skips_straight_past_any_column_mapping_step(self):
        response = self._upload()
        self.assertEqual(response.status_code, 302)
        batch = ImportBatch.objects.get(user=self.user)
        self.assertEqual(batch.column_mapping["date"], "Date")
        self.assertEqual(batch.column_mapping["amount"], "Amount")
        self.assertEqual(response.headers["Location"], reverse("imports:choose_account", kwargs={"pk": batch.pk}))

    def test_full_happy_path_imports_transactions_and_updates_dashboard_data(self):
        self._upload()
        batch = ImportBatch.objects.get(user=self.user)
        response = self._choose_new_account(batch)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("imports:preview", kwargs={"pk": batch.pk}))
        batch.refresh_from_db()
        self.assertIsNotNone(batch.account_id)

        preview_url = reverse("imports:preview", kwargs={"pk": batch.pk})
        response = self.client.get(preview_url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(preview_url, {"include": ["1", "2"]})
        self.assertEqual(response.status_code, 302)

        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.COMMITTED)
        self.assertEqual(batch.rows_imported, 2)
        self.assertEqual(Transaction.objects.filter(user=self.user, source="imported").count(), 2)

        # The dashboard is computed live from the DB on every request, so
        # importing is immediately reflected with no extra refresh step.
        self.user.profile.onboarding_completed = True
        self.user.profile.save(update_fields=["onboarding_completed", "updated_at"])
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["recent_transactions"][0].source, "imported")

    def test_money_in_out_style_csv_imports_automatically(self):
        self._upload(content=MONEY_IN_OUT_CSV)
        batch = ImportBatch.objects.get(user=self.user)
        self._choose_new_account(batch)
        preview_url = reverse("imports:preview", kwargs={"pk": batch.pk})
        response = self.client.post(preview_url, {"include": ["1", "2"]})
        self.assertEqual(response.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.rows_imported, 2)

    def test_unchecking_a_row_excludes_it(self):
        self._upload()
        batch = ImportBatch.objects.get(user=self.user)
        self._choose_new_account(batch)
        self.client.post(reverse("imports:preview", kwargs={"pk": batch.pk}), {"include": ["1"]})
        batch.refresh_from_db()
        self.assertEqual(batch.rows_imported, 1)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 1)

    def test_reimporting_the_same_file_does_not_double_count(self):
        for _ in range(2):
            self._upload()
            batch = ImportBatch.objects.latest("created_at")
            existing_account = Account.objects.filter(user=self.user).first()
            if existing_account:
                self.client.post(
                    reverse("imports:choose_account", kwargs={"pk": batch.pk}),
                    {"existing_account": existing_account.pk},
                )
            else:
                self._choose_new_account(batch)
            self.client.post(reverse("imports:preview", kwargs={"pk": batch.pk}), {"include": ["1", "2"]})

        self.assertEqual(Transaction.objects.filter(user=self.user, source="imported").count(), 2)
        second_batch = ImportBatch.objects.latest("created_at")
        self.assertEqual(second_batch.rows_imported, 0)
        self.assertEqual(second_batch.rows_duplicate_skipped, 2)

    def test_failed_commit_rolls_back_atomically_and_marks_batch_failed(self):
        self._upload()
        batch = ImportBatch.objects.get(user=self.user)
        self._choose_new_account(batch)
        preview_url = reverse("imports:preview", kwargs={"pk": batch.pk})
        with patch("imports.views.record_transaction", side_effect=RuntimeError("boom")):
            response = self.client.post(preview_url, {"include": ["1", "2"]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.FAILED)
        self.assertTrue(batch.error_message)
        self.assertNotIn("RuntimeError", batch.error_message)
        self.assertNotIn("boom", batch.error_message)


class CrossUserAccessTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="pw12345")
        self.bob = User.objects.create_user(username="bob", password="pw12345")
        self.batch = ImportBatch.objects.create(
            user=self.alice, original_filename="a.csv", raw_file=SIMPLE_CSV.encode(),
            column_mapping={"date": "Date", "description": "Description", "amount": "Amount"},
        )

    def test_other_user_cannot_view_or_act_on_the_batch(self):
        self.client.login(username="bob", password="pw12345")
        for url_name in ("imports:choose_account", "imports:preview", "imports:batch_detail"):
            response = self.client.get(reverse(url_name, kwargs={"pk": self.batch.pk}))
            self.assertEqual(response.status_code, 404, url_name)

    def test_other_user_cannot_delete_the_batch(self):
        self.client.login(username="bob", password="pw12345")
        response = self.client.post(reverse("imports:delete", kwargs={"pk": self.batch.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ImportBatch.objects.filter(pk=self.batch.pk).exists())


class DeleteAndRetryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345")
        self.client.login(username="alice", password="pw12345")

    def test_deleting_a_committed_batch_keeps_the_record_but_drops_the_file(self):
        batch = ImportBatch.objects.create(
            user=self.user, status=ImportBatch.Status.COMMITTED,
            raw_file=SIMPLE_CSV.encode(), rows_imported=2,
        )
        self.client.post(reverse("imports:delete", kwargs={"pk": batch.pk}))
        batch.refresh_from_db()
        self.assertIsNone(batch.raw_file)
        self.assertEqual(batch.rows_imported, 2)

    def test_deleting_a_draft_batch_removes_it_entirely(self):
        batch = ImportBatch.objects.create(user=self.user, status=ImportBatch.Status.DRAFT, raw_file=SIMPLE_CSV.encode())
        self.client.post(reverse("imports:delete", kwargs={"pk": batch.pk}))
        self.assertFalse(ImportBatch.objects.filter(pk=batch.pk).exists())

    def test_retrying_a_failed_batch_resets_it_to_draft(self):
        batch = ImportBatch.objects.create(
            user=self.user, status=ImportBatch.Status.FAILED, raw_file=SIMPLE_CSV.encode(),
            column_mapping={"date": "Date", "description": "Description", "amount": "Amount"},
            error_message="Something went wrong.",
        )
        response = self.client.post(reverse("imports:retry", kwargs={"pk": batch.pk}))
        self.assertEqual(response.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.DRAFT)
        self.assertEqual(batch.error_message, "")

    def test_cannot_retry_a_batch_that_did_not_fail(self):
        batch = ImportBatch.objects.create(user=self.user, status=ImportBatch.Status.COMMITTED, raw_file=SIMPLE_CSV.encode())
        self.client.post(reverse("imports:retry", kwargs={"pk": batch.pk}))
        batch.refresh_from_db()
        self.assertEqual(batch.status, ImportBatch.Status.COMMITTED)
