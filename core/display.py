"""Presentation helpers for dashboard/insights charts.

Money totals stay Decimal. Floats are used only for SVG coordinates.
"""

from calendar import month_abbr
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from core.services import quantize_money
from transactions.models import Transaction

RANGE_MONTHS = {"1W": 0, "1M": 1, "3M": 3, "6M": 6, "1Y": 12}


def user_initials(user) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return (first[0] + last[0]).upper()
    if first:
        return first[:2].upper()
    name = (user.username or "U").strip()
    return name[:2].upper()


def display_name(user) -> str:
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.username


def greeting_for(when=None) -> str:
    hour = (when or timezone.localtime()).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def cash_series(user, range_key: str = "6M"):
    """End-of-bucket cash balances from recorded transactions only."""
    today = timezone.now().date()
    range_key = range_key if range_key in RANGE_MONTHS else "6M"
    if range_key in ("1W", "1M"):
        # Daily points: one monthly bucket would draw a single dot for 1M.
        days = 7 if range_key == "1W" else 30
        start = today - timedelta(days=days - 1)
        labels = []
        points = []
        running = _balance_before(user, start)
        by_day = _totals_by_day(user, start, today)
        day = start
        while day <= today:
            running = quantize_money(running + by_day.get(day, Decimal("0")))
            if range_key == "1W":
                labels.append(day.strftime("%a"))
            else:
                index = (day - start).days
                labels.append(f"{day:%b} {day.day}" if index % 5 == 4 else "")
            points.append(running)
            day += timedelta(days=1)
        return labels, points

    months = RANGE_MONTHS[range_key]
    labels = []
    points = []
    cursor = date(today.year, today.month, 1)
    buckets = []
    for _ in range(months):
        buckets.append(cursor)
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    buckets.reverse()
    if not buckets:
        return [], []
    start = buckets[0]
    running = _balance_before(user, start)
    by_month = _totals_by_month(user, start, today)
    for month_start in buckets:
        key = (month_start.year, month_start.month)
        running = quantize_money(running + by_month.get(key, Decimal("0")))
        labels.append(month_abbr[month_start.month])
        points.append(running)
    return labels, points


def line_chart(points, labels):
    if not points:
        return None
    nums = [float(p) for p in points]
    lo, hi = min(nums), max(nums)
    if hi == lo:
        hi = lo + 1.0
    width, top, bottom = 800.0, 30.0, 225.0
    n = len(nums)

    def x_at(i: int) -> float:
        return 0.0 if n == 1 else i / (n - 1) * width

    def y_at(v: float) -> float:
        return bottom - (v - lo) / (hi - lo) * (bottom - top)

    parts = []
    for i, v in enumerate(nums):
        cmd = "M" if i == 0 else "L"
        parts.append(f"{cmd}{x_at(i):.1f} {y_at(v):.1f}")
    current = " ".join(parts)
    last_x, last_y = x_at(n - 1), y_at(nums[-1])
    area = f"{current} L{last_x:.1f} 260 L0 260 Z"
    y_labels = [
        f"${hi:,.0f}",
        f"${(hi * 2 + lo) / 3:,.0f}",
        f"${(hi + lo * 2) / 3:,.0f}",
        f"${lo:,.0f}",
    ]
    return {
        "current": current,
        "area": area,
        "point_x": f"{last_x:.1f}",
        "point_y": f"{last_y:.1f}",
        "y_labels": y_labels,
        "x_labels": labels,
        "max_label": f"${hi:,.0f}",
        "min_label": f"${lo:,.0f}",
    }


def _balance_before(user, start: date) -> Decimal:
    income = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.INCOME, occurred_on__lt=start
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expense = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.EXPENSE, occurred_on__lt=start
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return quantize_money(income - expense)


def _totals_by_day(user, start: date, end: date) -> dict[date, Decimal]:
    rows = Transaction.objects.filter(user=user, occurred_on__gte=start, occurred_on__lte=end)
    totals: dict[date, Decimal] = {}
    for txn in rows:
        delta = txn.amount if txn.kind == Transaction.Kind.INCOME else -txn.amount
        totals[txn.occurred_on] = quantize_money(totals.get(txn.occurred_on, Decimal("0")) + delta)
    return totals


def month_start(day: date) -> date:
    return date(day.year, day.month, 1)


def add_months(day: date, delta: int) -> date:
    month_index = day.year * 12 + (day.month - 1) + delta
    year, month0 = divmod(month_index, 12)
    return date(year, month0 + 1, 1)


def flow_between(user, start: date, end: date) -> tuple[Decimal, Decimal]:
    income = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.INCOME, occurred_on__gte=start, occurred_on__lte=end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expense = Transaction.objects.filter(
        user=user, kind=Transaction.Kind.EXPENSE, occurred_on__gte=start, occurred_on__lte=end
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return quantize_money(income), quantize_money(expense)


def category_totals(user, start: date, end: date):
    rows = (
        Transaction.objects.filter(
            user=user,
            kind=Transaction.Kind.EXPENSE,
            occurred_on__gte=start,
            occurred_on__lte=end,
            category__isnull=False,
        )
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    items = [{"name": row["category__name"], "total": quantize_money(row["total"])} for row in rows]
    grand = quantize_money(sum((item["total"] for item in items), Decimal("0")))
    palette = ["#2f7d62", "#d2a44d", "#112b2b", "#aab2af"]
    cursor = 0
    for index, item in enumerate(items):
        pct = int((item["total"] / grand) * 100) if grand else 0
        item["percent"] = pct
        item["color"] = palette[index % len(palette)]
        item["start"] = cursor
        cursor += pct
    return items, grand


def conic_style(items) -> str:
    if not items:
        return "radial-gradient(circle, white 58%, transparent 59%), conic-gradient(#e8ece8 0 100%)"
    stops = []
    cursor = 0
    for item in items:
        nxt = min(cursor + item["percent"], 100)
        stops.append(f"{item['color']} {cursor}% {nxt}%")
        cursor = nxt
    if cursor < 100:
        stops.append(f"#e8ece8 {cursor}% 100%")
    return (
        "radial-gradient(circle, white 58%, transparent 59%), conic-gradient("
        + ", ".join(stops)
        + ")"
    )


def monthly_bars(user, months: int = 6, end: date | None = None):
    today = end or timezone.now().date()
    start_month = add_months(month_start(today), -(months - 1))
    expense_by_month: dict[tuple[int, int], Decimal] = {}
    income_by_month: dict[tuple[int, int], Decimal] = {}
    rows = Transaction.objects.filter(user=user, occurred_on__gte=start_month, occurred_on__lte=today)
    for txn in rows:
        key = (txn.occurred_on.year, txn.occurred_on.month)
        if txn.kind == Transaction.Kind.INCOME:
            income_by_month[key] = quantize_money(income_by_month.get(key, Decimal("0")) + txn.amount)
        else:
            expense_by_month[key] = quantize_money(expense_by_month.get(key, Decimal("0")) + txn.amount)
    bars = []
    cursor = start_month
    peak = Decimal("1")
    raw = []
    for _ in range(months):
        key = (cursor.year, cursor.month)
        inc = income_by_month.get(key, Decimal("0"))
        exp = expense_by_month.get(key, Decimal("0"))
        peak = max(peak, inc, exp)
        raw.append((month_abbr[cursor.month], inc, exp))
        cursor = add_months(cursor, 1)
    for label, inc, exp in raw:
        bars.append(
            {
                "label": label,
                "income": inc,
                "expense": exp,
                "income_h": int((inc / peak) * 100) if peak else 0,
                "expense_h": int((exp / peak) * 100) if peak else 0,
            }
        )
    return bars


def _totals_by_month(user, start: date, end: date) -> dict[tuple[int, int], Decimal]:
    rows = Transaction.objects.filter(user=user, occurred_on__gte=start, occurred_on__lte=end)
    totals: dict[tuple[int, int], Decimal] = {}
    for txn in rows:
        key = (txn.occurred_on.year, txn.occurred_on.month)
        delta = txn.amount if txn.kind == Transaction.Kind.INCOME else -txn.amount
        totals[key] = quantize_money(totals.get(key, Decimal("0")) + delta)
    return totals
