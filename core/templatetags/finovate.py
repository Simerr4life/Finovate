from django import template

register = template.Library()


@register.filter
def merchant_mark(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "TX"
    parts = [p for p in text.replace("-", " ").split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return text[:2].upper()


@register.filter
def money(value) -> str:
    if value is None:
        return "$0.00"
    return f"${value:,.2f}"


@register.filter
def signed_money(value, kind="expense") -> str:
    amount = abs(float(value or 0))
    formatted = f"${amount:,.2f}"
    if kind == "income" or (hasattr(value, "__gt__") and value > 0 and kind == "signed"):
        return f"+{formatted}"
    return f"-{formatted}"


@register.simple_tag
def submission_key():
    """Hidden field that lets the server ignore an accidental double submit."""
    import uuid

    from django.utils.html import format_html

    return format_html('<input type="hidden" name="idempotency_key" value="{}">', uuid.uuid4().hex)
