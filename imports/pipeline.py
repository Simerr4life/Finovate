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

# Role -> header aliases we recognize automatically, checked against a
# normalized header (lowercased, underscores/hyphens treated as spaces,
# punctuation stripped). First match wins. Only used for auto-detection --
# there's no user-facing mapping step, so these have to be good enough on
# their own; anything not recognized is kept in a row's `raw` dict but
# never guessed at.
COLUMN_ALIASES = {
    "date": ["date", "transaction date", "trans date", "txn date", "posted date"],
    "posting_date": ["posting date", "post date", "settlement date"],
    "description": ["description", "memo", "merchant", "payee", "narrative", "details"],
    "amount": ["amount", "transaction amount", "amt", "amount usd"],
    "net_amount": ["net amount", "net amount usd", "signed amount"],
    "debit": ["debit", "withdrawal", "withdrawals", "money out", "money out usd", "debit amount"],
    "credit": ["credit", "deposit", "deposits", "money in", "money in usd", "credit amount"],
    "balance": ["balance", "running balance", "account balance", "ending balance", "running balance usd"],
    "reference": ["reference", "reference number", "transaction id", "id", "check number"],
    "currency": ["currency", "currency code"],
}

# Recognized but never required and never used to derive amount/date/kind --
# e.g. a bank's own "Category" column, a "Transaction_Type" or "Recurring"
# flag. Kept out of parsing entirely; still visible in a row's `raw` dict.
OPTIONAL_METADATA_ALIASES = {
    "category_hint": ["category"],
    "transaction_type": ["transaction type"],
    "recurring_flag": ["recurring"],
    "payment_method": ["payment method"],
}

REQUIRED_ROLES = ("date", "description")

# Tried in order; the first one that parses the whole string wins.
# Extra formats are additive — existing US-style CSVs still hit earlier entries.
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d.%m.%y",
    "%Y/%m/%d",
    "%b %d %Y",
    "%B %d, %Y",
]

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


def mapping_roles(mapping: dict) -> dict:
    """Column roles only — strips reserved keys like `_reader`."""
    if not mapping:
        return {}
    return {key: value for key, value in mapping.items() if not str(key).startswith("_")}


def text_for_parsing(text: str, mapping: dict | None = None) -> str:
    """Return the CSV text the classic parser should read.

    Classic imports (no `_reader` meta) pass through unchanged. Enhanced
    imports re-materialize a normalized CSV from the original bytes so
    preamble / delimiter / decimal quirks stay out of parse_rows.
    """
    meta = (mapping or {}).get("_reader") if isinstance(mapping, dict) else None
    if isinstance(meta, dict) and meta.get("engine") == "enhanced":
        from . import csv_enhanced

        return csv_enhanced.materialize(text, meta)
    return text


@dataclass
class PreparedStatement:
    """Result of classic-first, enhanced-fallback preparation."""

    text: str
    mapping: dict
    rows: list
    engine: str  # "classic" | "enhanced"
    problems: list = field(default_factory=list)

    @property
    def readable(self) -> bool:
        return not self.problems


def _headers_include_dr_cr_type(headers: list[str]) -> bool:
    """True when a dedicated DR/CR column is present (not generic type labels)."""
    from . import csv_enhanced

    for header in headers:
        if csv_enhanced._role_for_header(header) == "type":
            return True
    return False


def _use_enhanced_result(enhanced, account_id=None) -> PreparedStatement | None:
    enhanced_mapping = detect_columns(read_headers(enhanced.text))
    enhanced_rows = parse_rows(enhanced.text, enhanced_mapping, account_id=account_id)
    enhanced_ok, _problems = assess_readability(enhanced_mapping, enhanced_rows)
    if not enhanced_ok:
        return None
    stored = dict(enhanced_mapping)
    stored["_reader"] = enhanced.meta.as_dict()
    return PreparedStatement(
        text=enhanced.text,
        mapping=stored,
        rows=enhanced_rows,
        engine="enhanced",
    )


def prepare_statement(text: str, account_id=None) -> PreparedStatement:
    """Try the classic CSV format first; fall back to the enhanced reader.

    Existing simple exports keep using the classic path so behavior stays
    stable. Messier bank files (preamble rows, `;` delimiters, European
    decimals, DR/CR type columns) are normalized by `csv_enhanced` into the
    same shape classic already understands — the classic format itself is
    not replaced.
    """
    from . import csv_enhanced

    headers = read_headers(text)
    mapping = detect_columns(headers)
    rows = parse_rows(text, mapping, account_id=account_id)
    readable, problems = assess_readability(mapping, rows)

    if readable and not _headers_include_dr_cr_type(headers):
        return PreparedStatement(text=text, mapping=mapping, rows=rows, engine="classic")

    enhanced = csv_enhanced.prepare(text)
    if enhanced is not None:
        prepared = _use_enhanced_result(enhanced, account_id=account_id)
        if prepared is not None:
            return prepared

    if readable:
        return PreparedStatement(text=text, mapping=mapping, rows=rows, engine="classic")

    return PreparedStatement(
        text=text, mapping=mapping, rows=rows, engine="classic", problems=problems
    )


def _normalize_header(name: str) -> str:
    name = name.lower().strip().replace("_", " ").replace("-", " ")
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch == " ")
    return " ".join(cleaned.split())


def detect_columns(headers: list[str]) -> dict:
    """Best-effort, fully-automatic role -> header-name mapping. This is
    the only mapping step there is -- there's no screen asking the user to
    confirm it, so `assess_readability` is what decides whether the guess
    was good enough to import from, not a human."""
    normalized = {_normalize_header(h): h for h in headers}
    mapping = {}
    for role, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[role] = normalized[alias]
                break
    return mapping


def validate_mapping(mapping: dict) -> list[str]:
    """Return a list of problems with a detected mapping, empty if it's
    usable. Doesn't require perfection -- just enough to parse."""
    problems = []
    for role in REQUIRED_ROLES:
        if not mapping.get(role):
            problems.append(f"Couldn't find a {role.replace('_', ' ')} column.")
    if not mapping.get("amount") and not mapping.get("net_amount") and not (mapping.get("debit") or mapping.get("credit")):
        problems.append("Couldn't find an amount, or debit/credit, column.")
    return problems


def assess_readability(mapping: dict, rows: list) -> tuple[bool, list[str]]:
    """Whether this file has enough of a recognizable shape to import from
    at all. Used right after upload, before asking the user anything else --
    if this says no, they go straight to the unreadable-file fallback
    (retry with another file, or enter finances manually) instead of
    wading through a wizard for a file that was never going to work.
    """
    problems = validate_mapping(mapping)
    if problems:
        return False, problems
    if not rows:
        return False, ["No transaction rows were found in this file."]
    if not any(not r.errors for r in rows):
        return False, ["None of the rows in this file could be read reliably."]
    return True, []


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    # ISO datetimes from some exports: keep the date portion only.
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
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


def _resolve_amount(raw: dict, mapping: dict) -> tuple[Decimal | None, str | None, list]:
    """Figures out the signed amount for one row from whichever of
    debit/credit, net_amount, and amount are mapped -- without ever adding
    them together. When more than one is present, they must agree (same
    signed value); if they don't, the row is flagged for review rather
    than silently trusting one field over another.

    Returns (positive amount, kind, errors).
    """
    candidates: dict = {}

    if mapping.get("debit") or mapping.get("credit"):
        debit = _parse_decimal(raw.get(mapping.get("debit", ""), "")) if mapping.get("debit") else None
        credit = _parse_decimal(raw.get(mapping.get("credit", ""), "")) if mapping.get("credit") else None
        if debit and credit:
            return None, None, ["Both debit and credit are filled in for this row."]
        if debit:
            candidates["debit/credit"] = -abs(debit)
        elif credit:
            candidates["debit/credit"] = abs(credit)

    if mapping.get("net_amount"):
        net = _parse_decimal(raw.get(mapping["net_amount"], ""))
        if net is not None:
            candidates["net amount"] = net

    if mapping.get("amount"):
        amt = _parse_decimal(raw.get(mapping["amount"], ""))
        if amt is not None:
            candidates["amount"] = amt

    if not candidates:
        return None, None, ["No amount found for this row."]

    distinct = set(candidates.values())
    if len(distinct) > 1:
        names = " and ".join(candidates.keys())
        return None, None, [f"The {names} columns disagree on this row's amount -- skipped rather than guessed."]

    signed = distinct.pop()
    if signed == 0:
        return None, None, ["This row's amount is zero -- please review."]
    kind = "expense" if signed < 0 else "income"
    return abs(signed), kind, []


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

    Reserved mapping keys starting with `_` (e.g. `_reader`) are ignored so
    enhanced-reader metadata can live alongside role → header entries.
    """
    roles = mapping_roles(mapping)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[ParsedRow] = []
    for i, raw in enumerate(reader, start=1):
        if i > MAX_ROWS:
            break
        row = ParsedRow(row_number=i, raw=raw)

        occurred_on = _parse_date(raw.get(roles.get("date", ""), ""))
        if occurred_on is None:
            row.errors.append("Couldn't read the date for this row.")
        row.occurred_on = occurred_on

        row.description = (raw.get(roles.get("description", ""), "") or "").strip()

        amount, kind, amount_errors = _resolve_amount(raw, roles)
        row.errors.extend(amount_errors)
        row.amount = amount
        row.kind = kind

        if roles.get("balance"):
            row.balance_after = _parse_decimal(raw.get(roles["balance"], ""))

        if roles.get("currency"):
            currency = (raw.get(roles["currency"], "") or "").strip().upper() or None
            row.currency = currency
            if currency and currency != ASSUMED_CURRENCY:
                row.errors.append(
                    f"This row's currency column says {currency}, not {ASSUMED_CURRENCY}. "
                    "Finovate only supports single-currency accounts today -- please review."
                )

        if roles.get("reference"):
            ref = (raw.get(roles["reference"], "") or "").strip()
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
