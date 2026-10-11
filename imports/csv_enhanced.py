"""Enhanced CSV statement reader — additive, does not replace the classic path.

Bank exports often need more than "first row is the header, comma-separated
US numbers." This module:

- sniffs comma / semicolon / tab / pipe delimiters
- skips preamble rows (account metadata above the real header)
- normalizes European decimals (4,35 / 1.234,56) into classic form
- folds Description+Memo and Amount+DR/CR into columns the classic
  pipeline already understands

Output is always a clean, comma-separated CSV whose first row is the
header, so `pipeline.detect_columns` + `pipeline.parse_rows` keep working
unchanged. The classic format is never overwritten; this is a fallback
and an opt-in materializer keyed by `column_mapping["_reader"]`.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

# Roles and aliases recognized when hunting for a header row. Broader than
# the classic list on purpose — matching here only decides where the table
# starts; the classic detector still maps columns on the materialized CSV.
_HEADER_ALIASES = {
    "date": [
        "date", "transaction date", "trans date", "txn date", "posted date",
        "booking date", "book date", "value date", "buchungstag", "wertstellung",
    ],
    "description": [
        "description", "merchant", "payee", "narrative", "details",
        "booking text", "transaction description", "verwendungszweck", "name",
    ],
    "amount": [
        "amount", "transaction amount", "amt", "amount usd", "betrag",
    ],
    "net_amount": ["net amount", "net amount usd", "signed amount"],
    "debit": [
        "debit", "withdrawal", "withdrawals", "money out", "money out usd",
        "debit amount", "payment", "ausgaben",
    ],
    "credit": [
        "credit", "deposit", "deposits", "money in", "money in usd",
        "credit amount", "receipt", "einnahmen",
    ],
    "balance": [
        "balance", "running balance", "account balance", "ending balance",
        "running balance usd", "saldo",
    ],
    "reference": [
        "reference", "reference number", "transaction id", "id",
        "check number", "fitid", "bank reference",
    ],
    "currency": ["currency", "currency code", "curr"],
    "memo": ["memo", "notes", "note", "additional information"],
    # Only headers that usually carry DR/CR (not free-form "Transaction_Type").
    "type": ["type", "dr cr", "debit credit", "credit debit", "dr/cr", "cr/dr"],
}

_CANONICAL_HEADERS = {
    "date": "Date",
    "posting_date": "Posting Date",
    "description": "Description",
    "amount": "Amount",
    "net_amount": "Net Amount",
    "debit": "Debit",
    "credit": "Credit",
    "balance": "Balance",
    "reference": "Reference",
    "currency": "Currency",
}

_EU_DECIMAL = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d{1,4}$|^-?\d+,\d{1,4}$")
_US_DECIMAL = re.compile(r"^-?\d{1,3}(,\d{3})*\.\d{1,4}$|^-?\d+\.\d{1,4}$")
_DATE_DOT = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")

MAX_PREAMBLE_SCAN = 40


@dataclass
class EnhancedMeta:
    engine: str = "enhanced"
    delimiter: str = ","
    header_row: int = 0
    decimal_style: str = "us"  # "us" | "eu"
    original_headers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "engine": self.engine,
            "delimiter": self.delimiter,
            "header_row": self.header_row,
            "decimal_style": self.decimal_style,
            "original_headers": list(self.original_headers),
        }


@dataclass
class EnhancedPrepareResult:
    text: str
    meta: EnhancedMeta
    role_map: dict  # role -> original header name (pre-canonicalize)


def _normalize_header(name: str) -> str:
    name = (name or "").lower().strip().replace("_", " ").replace("-", " ")
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch == " ")
    return " ".join(cleaned.split())


def _role_for_header(name: str) -> str | None:
    normalized = _normalize_header(name)
    if not normalized:
        return None
    for role, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return role
    return None


def detect_delimiter(sample: str) -> str:
    """Pick the most likely delimiter without requiring a perfect sniff."""
    try:
        dialect = csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|")
        if dialect.delimiter in ",;\t|":
            return dialect.delimiter
    except csv.Error:
        pass
    counts = {d: sample.count(d) for d in [",", ";", "\t", "|"]}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _read_matrix(text: str, delimiter: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader]


def _header_score(row: list[str]) -> tuple[int, set[str]]:
    roles: set[str] = set()
    for cell in row:
        role = _role_for_header(cell)
        if role:
            # memo/type are helpers, not core scoring roles
            if role in {"memo", "type"}:
                roles.add(role)
            else:
                roles.add(role)
    score = len(roles - {"memo", "type"})
    if "date" in roles:
        score += 2
    if "description" in roles or "memo" in roles:
        score += 1
    if {"amount", "net_amount", "debit", "credit"} & roles:
        score += 2
    return score, roles


def find_header_row(matrix: list[list[str]]) -> int:
    """Return the index of the most header-like row in the preamble window."""
    best_index = 0
    best_score = -1
    limit = min(len(matrix), MAX_PREAMBLE_SCAN)
    for i in range(limit):
        row = matrix[i]
        if sum(1 for c in row if (c or "").strip()) < 2:
            continue
        score, _roles = _header_score(row)
        if score > best_score:
            best_score = score
            best_index = i
    return best_index


def _detect_decimal_style(matrix: list[list[str]], header_index: int, role_indexes: dict) -> str:
    amount_indexes = [
        idx for role, idx in role_indexes.items()
        if role in {"amount", "net_amount", "debit", "credit", "balance"}
    ]
    eu = us = 0
    for row in matrix[header_index + 1 : header_index + 1 + 80]:
        for idx in amount_indexes:
            if idx >= len(row):
                continue
            cell = (row[idx] or "").strip().replace("$", "").replace("€", "").replace(" ", "")
            if not cell or cell in {"-", "—"}:
                continue
            if cell.startswith("(") and cell.endswith(")"):
                cell = cell[1:-1]
            if _EU_DECIMAL.match(cell):
                eu += 1
            elif _US_DECIMAL.match(cell):
                us += 1
    if eu > us:
        return "eu"
    return "us"


def _to_us_decimal(value: str, style: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1].strip()
    raw = raw.replace("$", "").replace("€", "").replace(" ", "")
    if raw.startswith("-"):
        negative = True
        raw = raw[1:]
    elif raw.startswith("+"):
        raw = raw[1:]
    if style == "eu" and "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", "")
    if not raw:
        return ""
    return f"-{raw}" if negative else raw


def _normalize_date_cell(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if _ISO_DT.match(value):
        return value[:10]
    if _DATE_DOT.match(value):
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%m.%d.%Y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
    return value


def _build_role_indexes(header: list[str]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for i, cell in enumerate(header):
        role = _role_for_header(cell)
        if role and role not in indexes:
            indexes[role] = i
    return indexes


def _signed_from_type(amount: str, type_value: str) -> str:
    """Apply DR/CR (or debit/credit) sign to a positive amount cell."""
    if not amount:
        return ""
    token = _normalize_header(type_value)
    if token in {"dr", "debit", "d", "withdrawal", "payment", "out"}:
        if not amount.startswith("-"):
            return f"-{amount.lstrip('+')}"
    if token in {"cr", "credit", "c", "deposit", "receipt", "in"}:
        return amount.lstrip("+").lstrip("-") if amount.startswith("-") else amount
    return amount


def prepare(text: str) -> EnhancedPrepareResult | None:
    """Build a classic-compatible CSV from a messy bank export.

    Returns None when nothing header-like is found — caller keeps the
    classic failure path.
    """
    if not (text or "").strip():
        return None
    delimiter = detect_delimiter(text)
    matrix = _read_matrix(text, delimiter)
    if not matrix:
        return None
    header_index = find_header_row(matrix)
    header = matrix[header_index]
    score, roles = _header_score(header)
    if score < 3 or "date" not in roles:
        return None
    if not ({"amount", "net_amount", "debit", "credit"} & roles):
        return None

    role_indexes = _build_role_indexes(header)
    decimal_style = _detect_decimal_style(matrix, header_index, role_indexes)

    # Choose output columns the classic pipeline already understands.
    out_roles: list[str] = []
    for role in (
        "date", "posting_date", "description", "amount", "net_amount",
        "debit", "credit", "balance", "reference", "currency",
    ):
        if role == "description":
            if "description" in role_indexes or "memo" in role_indexes:
                out_roles.append("description")
            continue
        if role in role_indexes:
            out_roles.append(role)

    if "date" not in out_roles:
        return None
    if "description" not in out_roles:
        return None
    if not any(r in out_roles for r in ("amount", "net_amount", "debit", "credit")):
        return None

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([_CANONICAL_HEADERS[r] for r in out_roles])

    for row in matrix[header_index + 1 :]:
        if not any((c or "").strip() for c in row):
            continue
        cells: list[str] = []
        for role in out_roles:
            if role == "description":
                parts = []
                for key in ("description", "memo"):
                    idx = role_indexes.get(key)
                    if idx is not None and idx < len(row):
                        part = (row[idx] or "").strip()
                        if part and part not in parts:
                            parts.append(part)
                cells.append(" — ".join(parts))
                continue

            idx = role_indexes.get(role)
            value = (row[idx] or "").strip() if idx is not None and idx < len(row) else ""

            if role == "date" or role == "posting_date":
                cells.append(_normalize_date_cell(value))
            elif role in {"amount", "net_amount", "debit", "credit", "balance"}:
                normalized = _to_us_decimal(value, decimal_style)
                if role == "amount" and "type" in role_indexes:
                    type_idx = role_indexes["type"]
                    type_val = row[type_idx] if type_idx < len(row) else ""
                    normalized = _signed_from_type(normalized, type_val)
                cells.append(normalized)
            else:
                cells.append(value)
        if not any(cells):
            continue
        writer.writerow(cells)

    meta = EnhancedMeta(
        delimiter=delimiter,
        header_row=header_index,
        decimal_style=decimal_style,
        original_headers=[(h or "").strip() for h in header],
    )
    role_map = {
        role: header[idx]
        for role, idx in role_indexes.items()
        if role in _CANONICAL_HEADERS or role in {"memo", "type"}
    }
    return EnhancedPrepareResult(text=out.getvalue(), meta=meta, role_map=role_map)


def materialize(text: str, meta: dict) -> str:
    """Re-run enhanced preparation from stored meta (delimiter/header hint).

    Meta is advisory — preparation re-detects so a slightly edited re-upload
    still works. Falls back to the original text if preparation fails.
    """
    result = prepare(text)
    if result is None:
        return text
    return result.text
