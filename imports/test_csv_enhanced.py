"""Tests for the additive enhanced CSV reader.

Classic-format fixtures must keep using the classic engine. Enhanced only
engages when the existing format cannot read the file reliably.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import csv_enhanced, pipeline
from .models import ImportBatch

PREAMBLE_CSV = (
    "Account Name,Everyday Checking\n"
    "Account Number,****1234\n"
    "Exported,2026-01-10\n"
    "\n"
    "Date,Description,Amount\n"
    "2026-01-05,Coffee Shop,-4.35\n"
    "2026-01-06,Paycheck,2000.00\n"
)

SEMICOLON_EU_CSV = (
    "Date;Description;Amount;Balance\n"
    "05.01.2026;Cafe;4,35;95,65\n"
    "06.01.2026;Salary;2000,00;2095,65\n"
)

DR_CR_CSV = (
    "Transaction Date,Description,Amount,Type\n"
    "2026-01-05,Coffee Shop,4.35,DR\n"
    "2026-01-06,Paycheck,2000.00,CR\n"
)

MEMO_SPLIT_CSV = (
    "Bank export for Alice\n"
    "Date,Description,Memo,Amount\n"
    "2026-01-05,POS PURCHASE,COFFEE SHOP,-4.35\n"
)


class EnhancedReaderUnitTests(TestCase):
    def test_detects_semicolon_delimiter(self):
        self.assertEqual(csv_enhanced.detect_delimiter(SEMICOLON_EU_CSV), ";")

    def test_finds_header_below_preamble(self):
        matrix = csv_enhanced._read_matrix(PREAMBLE_CSV, ",")
        self.assertEqual(csv_enhanced.find_header_row(matrix), 4)

    def test_prepare_normalizes_preamble_file(self):
        result = csv_enhanced.prepare(PREAMBLE_CSV)
        self.assertIsNotNone(result)
        self.assertEqual(result.meta.header_row, 4)
        self.assertTrue(result.text.startswith("Date,Description,Amount\n"))
        self.assertIn("Coffee Shop", result.text)

    def test_prepare_converts_european_decimals_and_dot_dates(self):
        result = csv_enhanced.prepare(SEMICOLON_EU_CSV)
        self.assertIsNotNone(result)
        self.assertEqual(result.meta.decimal_style, "eu")
        self.assertEqual(result.meta.delimiter, ";")
        rows = pipeline.parse_rows(
            result.text,
            pipeline.detect_columns(pipeline.read_headers(result.text)),
        )
        self.assertEqual(rows[0].occurred_on.isoformat(), "2026-01-05")
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[0].kind, "income")  # positive signed amount in source
        self.assertEqual(rows[1].amount, Decimal("2000.00"))

    def test_prepare_applies_dr_cr_signs(self):
        result = csv_enhanced.prepare(DR_CR_CSV)
        self.assertIsNotNone(result)
        rows = pipeline.parse_rows(
            result.text,
            pipeline.detect_columns(pipeline.read_headers(result.text)),
        )
        self.assertEqual(rows[0].kind, "expense")
        self.assertEqual(rows[0].amount, Decimal("4.35"))
        self.assertEqual(rows[1].kind, "income")
        self.assertEqual(rows[1].amount, Decimal("2000.00"))

    def test_prepare_joins_description_and_memo(self):
        result = csv_enhanced.prepare(MEMO_SPLIT_CSV)
        self.assertIsNotNone(result)
        rows = pipeline.parse_rows(
            result.text,
            pipeline.detect_columns(pipeline.read_headers(result.text)),
        )
        self.assertIn("POS PURCHASE", rows[0].description)
        self.assertIn("COFFEE SHOP", rows[0].description)


class PrepareStatementFallbackTests(TestCase):
    def test_classic_simple_csv_still_uses_classic_engine(self):
        text = "Date,Description,Amount\n2026-01-05,Coffee,-4.35\n"
        prepared = pipeline.prepare_statement(text)
        self.assertTrue(prepared.readable)
        self.assertEqual(prepared.engine, "classic")
        self.assertNotIn("_reader", prepared.mapping)
        self.assertEqual(prepared.rows[0].amount, Decimal("4.35"))

    def test_preamble_csv_falls_back_to_enhanced(self):
        prepared = pipeline.prepare_statement(PREAMBLE_CSV)
        self.assertTrue(prepared.readable)
        self.assertEqual(prepared.engine, "enhanced")
        self.assertEqual(prepared.mapping["_reader"]["engine"], "enhanced")
        self.assertEqual(len(prepared.rows), 2)
        self.assertEqual(prepared.rows[0].amount, Decimal("4.35"))

    def test_semicolon_european_csv_falls_back_to_enhanced(self):
        prepared = pipeline.prepare_statement(SEMICOLON_EU_CSV)
        self.assertTrue(prepared.readable)
        self.assertEqual(prepared.engine, "enhanced")
        self.assertEqual(prepared.rows[0].amount, Decimal("4.35"))

    def test_dr_cr_csv_falls_back_to_enhanced(self):
        # Classic treats both rows as income (unsigned amount column).
        classic_mapping = pipeline.detect_columns(["Transaction Date", "Description", "Amount", "Type"])
        classic_rows = pipeline.parse_rows(DR_CR_CSV, classic_mapping)
        self.assertEqual(classic_rows[0].kind, "income")

        prepared = pipeline.prepare_statement(DR_CR_CSV)
        self.assertEqual(prepared.engine, "enhanced")
        self.assertEqual(prepared.rows[0].kind, "expense")
        self.assertEqual(prepared.rows[1].kind, "income")

    def test_text_for_parsing_is_noop_for_classic_mapping(self):
        text = "Date,Description,Amount\n2026-01-05,Coffee,-4.35\n"
        self.assertEqual(
            pipeline.text_for_parsing(text, {"date": "Date", "amount": "Amount"}),
            text,
        )

    def test_text_for_parsing_rematerializes_enhanced_mapping(self):
        prepared = pipeline.prepare_statement(PREAMBLE_CSV)
        remade = pipeline.text_for_parsing(PREAMBLE_CSV, prepared.mapping)
        self.assertTrue(remade.startswith("Date,Description,Amount\n"))
        self.assertNotIn("Account Name", remade.splitlines()[0])

    def test_unreadable_garbage_still_fails(self):
        prepared = pipeline.prepare_statement("Just,Some,Random,Headers\nfoo,bar,baz,qux\n")
        self.assertFalse(prepared.readable)
        self.assertEqual(prepared.engine, "classic")


class EnhancedUploadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw12345")
        self.client.login(username="alice", password="pw12345")

    def _upload(self, content, filename="statement.csv"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload_file = SimpleUploadedFile(filename, content.encode("utf-8"), content_type="text/csv")
        return self.client.post(reverse("imports:upload"), {"file": upload_file})

    def test_preamble_upload_creates_batch_with_enhanced_reader_meta(self):
        response = self._upload(PREAMBLE_CSV)
        self.assertEqual(response.status_code, 302)
        batch = ImportBatch.objects.get(user=self.user)
        self.assertEqual(batch.column_mapping["_reader"]["engine"], "enhanced")
        self.assertEqual(batch.column_mapping["date"], "Date")

    def test_enhanced_batch_preview_reparses_from_original_bytes(self):
        self._upload(PREAMBLE_CSV)
        batch = ImportBatch.objects.get(user=self.user)
        self.client.post(
            reverse("imports:choose_account", kwargs={"pk": batch.pk}),
            {
                "institution_name": "Test Bank",
                "account_type": "Checking",
                "masked_number": "0001",
                "opening_balance": "100.00",
            },
        )
        response = self.client.get(reverse("imports:preview", kwargs={"pk": batch.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"].importable, 2)
        self.assertContains(response, "Coffee Shop")

    def test_classic_upload_does_not_attach_reader_meta(self):
        response = self._upload("Date,Description,Amount\n2026-01-05,Coffee,-4.35\n")
        self.assertEqual(response.status_code, 302)
        batch = ImportBatch.objects.get(user=self.user)
        self.assertNotIn("_reader", batch.column_mapping)
