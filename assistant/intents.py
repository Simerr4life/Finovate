"""Tiny keyword/regex intent recognizer.

No LLM, no external NLU service — just pattern matching. That's a
deliberate choice for a hackathon-scale assistant: it's fully offline,
testable, and transparent about what it will and won't understand,
rather than depending on an API key nobody has configured yet.

Each recognizer returns a (intent_name, payload) tuple or None. The first
match wins — order recognizers from most to least specific.
"""

import re
from decimal import Decimal, InvalidOperation

CONFIRM_WORDS = {"yes", "y", "confirm", "ok", "okay", "do it", "sure"}
CANCEL_WORDS = {"no", "n", "cancel", "stop", "nevermind", "never mind"}

_AMOUNT_RE = re.compile(r"\$?\s*([\d,]+(?:\.\d{1,2})?)")


def _extract_amount(text: str) -> Decimal | None:
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def parse_intent(text: str) -> tuple[str, dict] | None:
    lower = text.lower().strip()

    if any(lower == w for w in CONFIRM_WORDS):
        return ("confirm", {})
    if any(lower == w for w in CANCEL_WORDS):
        return ("cancel", {})

    if re.search(r"\bmonthly\b", lower) and re.search(r"\b(savings|save)\b", lower) and re.search(r"\btarget\b", lower):
        return ("monthly_target_unsupported", {})

    if re.search(r"\bwithdraw", lower):
        return ("withdraw_unsupported", {})

    if re.search(r"\b(available|spare)\b", lower) and re.search(r"\binvest", lower):
        return ("available_to_invest", {})

    if re.search(r"\binvested\b", lower) and re.search(r"\bmonth\b", lower):
        return ("invested_this_month", {})

    if re.search(r"\ballocation\b", lower):
        return ("allocation", {})

    if re.search(r"\binvest(?:ing)?\b", lower):
        amount = _extract_amount(lower)
        if amount and amount > 0:
            return ("propose_invest", {"amount": str(amount)})

    if re.search(r"\b(budget|spending)\b", lower):
        return ("budget_status", {})

    if re.search(r"\b(got paid|paid me|i (got|received)|income of)\b", lower):
        amount = _extract_amount(lower)
        if amount:
            return ("report_income", {"amount": str(amount)})

    if re.search(r"\brisk\b", lower):
        for level in ("low", "medium", "high"):
            if level in lower:
                return ("set_risk_comfort", {"level": level})

    if re.search(r"\bgoal\b", lower) and _extract_amount(lower) and re.search(r"\b(set|change|update|to)\b", lower):
        amount = _extract_amount(lower)
        # Pull a loose "name" hint: whatever's left after stripping noise words.
        name_hint = re.sub(
            r"\b(set|change|update|my|the|goal|target|to|for)\b|\$?[\d,]+(?:\.\d{1,2})?",
            "", lower,
        ).strip()
        return ("update_goal_target", {"amount": str(amount), "name_hint": name_hint})

    if re.search(r"\b(goal|goals|emergency)\b", lower) or re.search(r"\bsavings\b.*\bprogress\b", lower):
        name_hint = re.sub(
            r"\b(what|whats|what's|is|are|my|the|a|an|goal|goals|progress|how|much|have|i|made|toward|towards|show|savings|fund|status)\b|[?]",
            " ",
            lower,
        )
        name_hint = re.sub(r"\s+", " ", name_hint).strip()
        return ("goal_status", {"name_hint": name_hint})

    if re.search(r"\bpause\b.*\bround.?up", lower):
        return ("pause_roundups", {})
    if re.search(r"\b(resume|enable|turn on|start)\b.*\bround.?up", lower):
        return ("resume_roundups", {})

    if re.search(r"\bportfolio\b|\bperformance\b|\binvestment summary\b", lower):
        return ("portfolio_performance", {})

    if re.search(r"\bmarket\b", lower):
        return ("market_status", {})

    if re.search(r"\b(help|what can you do|commands)\b", lower):
        return ("help", {})

    return None
