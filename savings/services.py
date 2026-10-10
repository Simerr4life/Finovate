"""Savings goal math: contributions, milestones, and completion estimates."""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from core.services import quantize_money

MILESTONES = [25, 50, 75, 100]


def apply_contribution(goal, kind: str, amount: Decimal, note: str = "", source: str = "manual"):
    """Create a Contribution and update the goal's current_amount.

    Returns (contribution, newly_crossed_milestone_or_None). Caller decides
    whether to raise a NotificationEvent for a crossed milestone — kept out
    of this function so the savings app doesn't depend on accounts.
    """
    from .models import Contribution  # local import avoids import-time cycle

    amount = quantize_money(amount)
    before_percent = goal.progress_percent

    if kind == Contribution.Kind.WITHDRAWAL:
        goal.current_amount = quantize_money(goal.current_amount - amount)
    else:
        goal.current_amount = quantize_money(goal.current_amount + amount)

    if goal.current_amount < 0:
        goal.current_amount = Decimal("0.00")

    if goal.current_amount >= goal.target_amount and goal.achieved_at is None:
        goal.achieved_at = timezone.now()
    elif goal.current_amount < goal.target_amount:
        goal.achieved_at = None

    goal.save(update_fields=["current_amount", "achieved_at", "updated_at"])

    contribution = Contribution.objects.create(
        user_id=goal.user_id,
        goal=goal,
        kind=kind,
        amount=amount,
        note=note,
        source=source,
    )

    after_percent = goal.progress_percent
    crossed = None
    for milestone in MILESTONES:
        if before_percent < milestone <= after_percent and goal.highest_milestone_notified < milestone:
            crossed = milestone
    if crossed:
        goal.highest_milestone_notified = crossed
        goal.save(update_fields=["highest_milestone_notified"])

    return contribution, crossed


def estimate_completion_date(goal, lookback_days: int = 90) -> date | None:
    """Estimate when the goal will be fully funded from its recent pace.

    Returns None when there isn't enough history to make a responsible
    estimate (no contributions yet, or no net progress), rather than
    guessing. This is always an estimate, never a guarantee.
    """
    if goal.current_amount >= goal.target_amount:
        return None

    cutoff = timezone.now() - timedelta(days=lookback_days)
    recent = goal.contributions.filter(created_at__gte=cutoff)
    net = Decimal("0")
    for c in recent:
        if c.kind == c.Kind.WITHDRAWAL:
            net -= c.amount
        else:
            net += c.amount

    if net <= 0:
        return None

    daily_rate = net / Decimal(lookback_days)
    remaining = goal.target_amount - goal.current_amount
    days_needed = remaining / daily_rate
    if days_needed > Decimal(365 * 50):  # sanity cap: don't project absurd dates
        return None
    return timezone.now().date() + timedelta(days=int(days_needed) + 1)
