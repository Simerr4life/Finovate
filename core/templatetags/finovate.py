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
    if value < 0:
        return f"-${-value:,.2f}"
    return f"${value:,.2f}"
