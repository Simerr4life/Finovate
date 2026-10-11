"""Statement-import pipeline: validation, parsing, normalization, and
duplicate detection for CSV bank-transaction exports.

Every function here is pure (no DB writes, no HTTP) except
`find_existing_duplicates`, which only reads. This mirrors
transactions/services.py: business logic that's independently testable and
never trusts client-submitted "already parsed" data -- every step is
re-derived from the raw bytes + column mapping each time it's needed.

Money is always Decimal, never float. amount is always stored positive;
`kind` carries the sign, matching transactions.Transaction's convention.
"""

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MAX_ROWS = 20_000

# Role -> header aliases we recognize automatically, checked case-insensitively
# with whitespace/punctuation stripped. First match wins.
COLUMN_ALIASES = {
    "date": ["date", "transaction date", "trans date", "txn date", "posted date"],
    "posting_date": ["posting date", "post date", "settlement date"],
    "description": ["description", "memo", "merchant", "payee", "narrative", "details"],
    "amount": ["amount", "transaction amount", "amt"],
    "debit": ["debit", "withdrawal", "withdrawals", "money out", "debit amount"],
    "credit": ["credit", "deposit", "deposits", "money in", "credit amount"],
    "balance": ["balance", "running balance", "account balance", "ending balance"],
    "reference": ["reference", "reference number", "transaction id", "id", "check number"],
    "currency": ["currency", "currency code"],
}

REQUIRED_ROLES = ("date", "description")

# Tried in order; the first one that parses the whole string wins.
DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d %Y", "%B %d, %Y"]

ASSUMED_CURRENCY = "USD"


class ImportValidationError(Exception):
    """A short, user-facing message. Never wraps/exposes the original
    exception -- callers should log that separately if needed."""


@dataclass
class ParsedRow:
    row_number: int  # 1-based, excludes header
    raw: dict  # original cell values, for the review table
    occurred_on: date | None = None
    description: str = ""
    amount: Decimal | None = None
    kind: str | None = None  # "income" | "expense"
    currency: str | None = None
    external_id: str | None = None
    balance_after: Decimal | None = None
    errors: list = field(default_factory=list)
    is_duplicate: bool = False
    is_ambiguous: bool = False

    @property
    def needs_review(self) -> bool:
        return bool(self.errors) or self.is_ambiguous

    @property
    def is_importable(self) -> bool:
        return not self.errors and not self.is_duplicate


def decode_text(content: bytes) -> str:
    """Content-based decoding, not filename-based: a renamed binary file
    fails here because it won't decode as text, regardless of extension."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            raise ImportValidationError(
                "That file doesn't look like a text CSV export. "
                "Please export a CSV statement from your bank and try again."
            )
    if "\x00" in text:
        raise ImportValidationError("That file contains binary data and isn't a valid CSV.")
    return text


def validate_file(filename: str, content: bytes, max_bytes: int) -> str:
    """Check the upload is plausibly a text CSV and within size limits.
    Returns the decoded text. Raises ImportValidationError with a message
    safe to show the user -- never the underlying decode/parse exception.
    """
    if not content:
        raise ImportValidationError("That file is empty.")
    if len(content) > max_bytes:
        raise ImportValidationError(
            f"That file is too large ({len(content):,} bytes). The limit is {max_bytes:,} bytes."
        )
    text = decode_text(content)
    try:
        sample = text[:4096]
        csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        # Not fatal on its own -- some single-column or oddly quoted CSVs
        # fail sniffing but still parse fine with the default dialect.
        pass
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportValidationError("That file has no header row.")
    if len(header) < 2:
        raise ImportValidationError(
            "That file doesn't look like a multi-column CSV export."
        )
    return text


def read_headers(text: str) -> list[str]:
    reader = csv.reader(io.StringIO(text))
    return next(reader, [])


def _normalize_header(name: str) -> str:
    return "".join(ch for ch in name.lower().strip() if ch.isalnum() or ch == " ").strip()


def detect_columns(headers: list[str]) -> dict:
    """Best-effort role -> header-name guesses, for pre-filling the mapping
    form. Never used directly to import -- the user always confirms it."""
    normalized = {_normalize_header(h): h for h in headers}
    mapping = {}
    for role, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[role] = normalized[alias]
                break
    return mapping


def validate_mapping(mapping: dict) -> list[str]:
    """Return a list of user-facing problems with a proposed mapping, empty
    if it's usable. Doesn't require perfection -- just enough to parse."""
    problems = []
    for role in REQUIRED_ROLES:
        if not mapping.get(role):
            problems.append(f"Pick a column for {role.replace('_', ' ')}.")
    if not mapping.get("amount") and not (mapping.get("debit") or mapping.get("credit")):
        problems.append("Pick either an amount column, or debit/credit columns.")
    chosen = [v for v in mapping.values() if v]
    if len(chosen) != len(set(chosen)):
        problems.append("The same column is mapped to more than one field.")
    return problems


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    value = (value or "").strip()
    if not value:
        return None
    negative = False
    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1]
    value = value.replace(",", "").replace("$", "").strip()
    if value.startswith("-"):
        negative = True
        value = value[1:]
    elif value.startswith("+"):
        value = value[1:]
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def _normalize_description(text: str) -> str:
    return " ".join((text or "").lower().split())


def fingerprint(account_id, occurred_on, amount: Decimal, kind: str, description: str) -> str:
    key = "|".join([
        str(account_id or ""),
        occurred_on.isoformat() if occurred_on else "",
        str(amount) if amount is not None else "",
        kind or "",
        _normalize_description(description),
    ])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"fp:{digest}"


def parse_rows(text: str, mapping: dict, account_id=None) -> list[ParsedRow]:
    """Parse + normalize in one pass: reads the CSV with `mapping`'s column
    names, producing typed rows with Decimal amounts and a positive-amount
    + kind convention matching transactions.Transaction. Never raises on a
    single bad row -- it's recorded in that row's `errors` and flagged for
    review instead, so one malformed row never blocks the rest of the file.
    """
    reader = csv.DictReader(io.StringIO(text))
    rows: list[ParsedRow] = []
    for i, raw in enumerate(reader, start=1):
        if i > MAX_ROWS:
            break
        row = ParsedRow(row_number=i, raw=raw)

        occurred_on = _parse_date(raw.get(mapping.get("date", ""), ""))
        if occurred_on is None:
            row.errors.append("Couldn't read the date for this row.")
        row.occurred_on = occurred_on

        row.description = (raw.get(mapping.get("description", ""), "") or "").strip()

        amount = None
        kind = None
        if mapping.get("amount"):
            signed = _parse_decimal(raw.get(mapping["amount"], ""))
            if signed is None:
                row.errors.append("Couldn't read the amount for this row.")
            else:
                kind = "expense" if signed < 0 else "income"
                amount = abs(signed)
        else:
            debit = _parse_decimal(raw.get(mapping.get("debit", ""), "")) if mapping.get("debit") else None
            credit = _parse_decimal(raw.get(mapping.get("credit", ""), "")) if mapping.get("credit") else None
            if debit and credit:
                row.errors.append("Both debit and credit are filled in for this row.")
            elif debit:
                amount, kind = abs(debit), "expense"
            elif credit:
                amount, kind = abs(credit), "income"
            else:
                row.errors.append("No amount found in the debit or credit column for this row.")
        row.amount = amount
        row.kind = kind

        if mapping.get("balance"):
            row.balance_after = _parse_decimal(raw.get(mapping["balance"], ""))

        if mapping.get("currency"):
            currency = (raw.get(mapping["currency"], "") or "").strip().upper() or None
            row.currency = currency
            if currency and currency != ASSUMED_CURRENCY:
                row.errors.append(
                    f"This row's currency column says {currency}, not {ASSUMED_CURRENCY}. "
                    "Finovate only supports single-currency accounts today -- please review."
                )

        if mapping.get("reference"):
            ref = (raw.get(mapping["reference"], "") or "").strip()
            if ref:
                row.external_id = f"csv:{ref}"

        if row.external_id is None and amount is not None and kind is not None and occurred_on is not None:
            row.external_id = fingerprint(account_id, occurred_on, amount, kind, row.description)

        rows.append(row)
    return rows


def find_existing_duplicates(account, external_ids: set) -> set:
    """Read-only: which of these external_ids already exist as Transactions
    on this account. Imported here (not at module top) to keep pipeline.py
    importable without Django settings configured, for fast unit tests."""
    from transactions.models import Transaction

    if not account or not external_ids:
        return set()
    return set(
        Transaction.objects.filter(account=account, external_id__in=external_ids)
        .values_list("external_id", flat=True)
    )


def detect_duplicates(rows: list[ParsedRow], account) -> None:
    """Mutates rows in place: marks is_duplicate (safe to auto-skip) or
    is_ambiguous (needs the user's explicit decision).

    A row is a safe duplicate only when its external_id already exists on
    this account AND exactly one new row in this batch shares that id --
    if two+ new rows share a fingerprint (e.g. two identical $20 charges on
    the same day), we can't tell which is genuinely new, so all of them are
    flagged ambiguous instead of silently deduped.
    """
    candidate_ids = {r.external_id for r in rows if r.external_id and not r.errors}
    existing = find_existing_duplicates(account, candidate_ids)

    counts: dict = {}
    for row in rows:
        if row.external_id and not row.errors:
            counts[row.external_id] = counts.get(row.external_id, 0) + 1

    for row in rows:
        if row.errors or not row.external_id:
            continue
        same_batch_count = counts.get(row.external_id, 0)
        already_exists = row.external_id in existing
        if same_batch_count > 1:
            row.is_ambiguous = True
        elif already_exists:
            row.is_duplicate = True


@dataclass
class ImportSummary:
    detected: int = 0
    importable: int = 0
    duplicate: int = 0
    needs_review: int = 0


def summarize(rows: list[ParsedRow]) -> ImportSummary:
    summary = ImportSummary(detected=len(rows))
    for row in rows:
        if row.needs_review:
            summary.needs_review += 1
        elif row.is_duplicate:
            summary.duplicate += 1
        else:
            summary.importable += 1
    return summary
