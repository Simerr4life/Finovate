"""Savings goal math: contributions, milestones, and completion estimates."""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.services import quantize_money

MILESTONES = [25, 50, 75, 100]


@transaction.atomic
def apply_contribution(goal, kind: str, amount: Decimal, note: str = "", source: str = "manual"):
    """Create a Contribution and update the goal's current_amount.

    Returns (contribution, newly_crossed_milestone_or_None). Caller decides
    whether to raise a NotificationEvent for a crossed milestone — kept out
    of this function so the savings app doesn't depend on accounts.
    """
    from .models import Contribution, Goal  # local import avoids import-time cycle

    # Work from a locked, fresh row so two contributions saved at the same
    # time both land instead of one overwriting the other.
    locked = Goal.objects.select_for_update().get(pk=goal.pk)
    goal.current_amount = locked.current_amount
    goal.target_amount = locked.target_amount
    goal.achieved_at = locked.achieved_at
    goal.highest_milestone_notified = locked.highest_milestone_notified

    amount = quantize_money(amount)
    before_percent = goal.progress_percent

    if kind == Contribution.Kind.WITHDRAWAL:
        # Record what actually left the goal, so the history adds up to
        # the balance even if more was requested than was there.
        amount = min(amount, goal.current_amount)
        goal.current_amount = quantize_money(goal.current_amount - amount)
    else:
        goal.current_amount = quantize_money(goal.current_amount + amount)

    goal.sync_achieved()
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


def contribution_pace(
    remaining_amount: Decimal, target_date: date | None, today: date | None = None
):
    """Return suggested weekly, monthly, and yearly savings rates for a deadline."""
    if target_date is None:
        return None
    today = today or timezone.localdate()
    days_remaining = (target_date - today).days
    if remaining_amount <= 0 or days_remaining <= 0:
        return None

    daily_amount = remaining_amount / Decimal(days_remaining)
    yearly = quantize_money(daily_amount * Decimal("365.25"))
    return {
        "days_remaining": days_remaining,
        "weekly": quantize_money(yearly / Decimal("52")),
        "monthly": quantize_money(yearly / Decimal("12")),
        "yearly": yearly,
    }
