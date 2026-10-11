"""The assistant's brain: parses one inbound message, decides whether it
needs confirmation, and dispatches to the same service functions the
website uses (budgets.services, savings.services, investing.services) —
no duplicated business logic, and no money-affecting action happens
without a confirmed, explicit reply.
"""

from decimal import Decimal

from django.utils import timezone

from accounts.models import NotificationEvent
from budgets.models import Budget, BudgetPeriod
from budgets.services import compute_budget_progress
from investing.models import PortfolioSnapshot, SimulatedOrder
from investing.services import compute_investable_surplus, get_or_create_settings, propose_surplus_investment
from savings.models import Goal
from transactions.models import Transaction
from transactions.services import record_transaction

from .intents import parse_intent
from .models import ConversationMessage, PendingConfirmation

HELP_TEXT = (
    "I can help with:\n"
    "- \"how's my budget\" — budget status\n"
    "- \"what is my emergency fund goal\" — goal progress\n"
    "- \"I got paid $500\" — record income (I'll confirm first)\n"
    "- \"set my risk to high/medium/low\" — update risk comfort (confirm first)\n"
    "- \"set my Trip goal to $2000\" — change a goal's target (confirm first)\n"
    "- \"pause round-ups\" / \"resume round-ups\"\n"
    "- \"how's my portfolio doing\" — simulated performance\n"
    "- \"show my investment allocation\" — simulated allocation\n"
    "- \"propose investing $100\" — a pending simulated proposal (confirm first; not a trade)\n"
    "- \"how's the market today\"\n"
    "Bank withdrawals are not available. I will not move money from a text message."
)

MARKET_STATUS_REPLY = (
    "I can't fetch market prices directly in chat. Current quotes and daily history for the "
    "supported US stocks are available in Investments > Explore when the server's Twelve Data "
    "feed is configured. The feed does not currently cover the bundled index symbols."
)


def _log(user, direction, body, intent=""):
    ConversationMessage.objects.create(user=user, direction=direction, body=body, intent=intent)


def handle_incoming_message(user, text: str) -> str:
    text = (text or "").strip()
    _log(user, ConversationMessage.Direction.INBOUND, text)

    # Always re-query rather than use user.pending_confirmation: that
    # reverse-OneToOne accessor caches on the instance, which would return
    # a stale (already-deleted) object within one long-lived process that
    # reuses the same user instance across messages (e.g. chat_demo).
    pending = PendingConfirmation.objects.filter(user=user).first()
    if pending:
        parsed = parse_intent(text)
        if parsed and parsed[0] == "confirm":
            reply = _execute(user, pending.intent, pending.payload)
            pending.delete()
        elif parsed and parsed[0] == "cancel":
            pending.delete()
            reply = "Okay, cancelled. Nothing changed."
        else:
            reply = f'{pending.prompt_text}\n(Reply "yes" to confirm or "no" to cancel.)'
        _log(user, ConversationMessage.Direction.OUTBOUND, reply)
        return reply

    parsed = parse_intent(text)
    if not parsed:
        reply = 'Sorry, I didn\'t understand that. Reply "help" to see what I can do.'
        _log(user, ConversationMessage.Direction.OUTBOUND, reply)
        return reply

    intent, payload = parsed

    if intent in ("confirm", "cancel"):
        reply = "There's nothing pending to confirm right now."
        _log(user, ConversationMessage.Direction.OUTBOUND, reply)
        return reply

    if intent == "help":
        _log(user, ConversationMessage.Direction.OUTBOUND, HELP_TEXT, intent)
        return HELP_TEXT

    if intent in CONFIRMATION_REQUIRED:
        prompt = CONFIRMATION_PROMPTS[intent](user, payload)
        if prompt is None:
            reply = payload.get("_error") or "I couldn't find enough information to do that — try being more specific."
            _log(user, ConversationMessage.Direction.OUTBOUND, reply, intent)
            return reply
        PendingConfirmation.objects.update_or_create(
            user=user, defaults={"intent": intent, "payload": payload, "prompt_text": prompt}
        )
        reply = f'{prompt}\n(Reply "yes" to confirm or "no" to cancel.)'
        _log(user, ConversationMessage.Direction.OUTBOUND, reply, intent)
        return reply

    reply = _execute(user, intent, payload)
    _log(user, ConversationMessage.Direction.OUTBOUND, reply, intent)
    return reply


# --- Immediate (read-only or low-risk) intents -----------------------------

def _budget_status(user, payload) -> str:
    period = BudgetPeriod.objects.filter(user=user, is_active=True).first()
    if not period:
        return "You don't have an active budget period set up yet — add one on the Budgeting page."
    rows = [compute_budget_progress(b) for b in Budget.objects.filter(period=period).select_related("category")]
    if not rows:
        return f'No category limits set for "{period.name}" yet.'
    lines = [f"Budget status for {period.name}:"]
    for r in rows:
        flag = "OVER" if r.is_over else ("near limit" if r.is_warning else "on track")
        lines.append(f"- {r.category_name}: ${r.spent_amount}/${r.limit_amount} ({flag})")
    return "\n".join(lines)


def _pause_roundups(user, payload) -> str:
    rs = get_or_create_settings(user)
    rs.is_paused = True
    rs.save(update_fields=["is_paused", "updated_at"])
    if user.profile.notify_budget_warnings:
        NotificationEvent.objects.create(
            user=user, event_type=NotificationEvent.EventType.ROUNDUP_PAUSED,
            message="Round-up investing was paused via the assistant.",
        )
    return "Done — round-ups are paused. Say \"resume round-ups\" any time to turn them back on."


def _portfolio_performance(user, payload) -> str:
    snapshots = PortfolioSnapshot.objects.filter(user=user, pool__isnull=True).order_by("-as_of")
    general = snapshots.first()
    pool_snapshots = PortfolioSnapshot.objects.filter(user=user, pool__isnull=False).order_by("-as_of")
    if not general and not pool_snapshots.exists():
        return "No simulated investment activity yet — nothing to report. Remember: this is all simulated, no real brokerage is connected."
    lines = ["Simulated investment performance (not real brokerage data):"]
    if general:
        lines.append(f"- General bucket as of {general.as_of}: contributed ${general.net_contributions}, value ${general.market_value}, gain/loss ${general.gain_loss}")
    seen_pools = set()
    for snap in pool_snapshots:
        if snap.pool_id in seen_pools:
            continue
        seen_pools.add(snap.pool_id)
        lines.append(f"- \"{snap.pool.name}\" as of {snap.as_of}: contributed ${snap.net_contributions}, value ${snap.market_value}, gain/loss ${snap.gain_loss}")
    return "\n".join(lines)


def _goal_status(user, payload) -> str:
    hint = (payload.get("name_hint") or "").lower()
    goals = list(Goal.objects.filter(user=user))
    if hint:
        matches = [
            goal for goal in goals
            if hint in goal.name.lower()
            or hint in goal.get_category_display().lower()
            or hint in goal.category
        ]
    else:
        matches = goals
    if not matches:
        return "I couldn't find a savings goal with that name on your account."
    lines = ["Savings goal progress (cash on the goal, not invested funds):"]
    for goal in matches[:8]:
        lines.append(
            f"- {goal.name}: ${goal.current_amount} of ${goal.target_amount} ({goal.progress_percent}%)"
        )
    return "\n".join(lines)


def _allocation(user, payload) -> str:
    settings_row = get_or_create_settings(user)
    if settings_row.is_paused:
        roundups = "paused"
    elif settings_row.enabled:
        roundups = "enabled"
    else:
        roundups = "disabled"
    return (
        "There is no approved brokerage allocation. "
        f"Risk comfort is {user.profile.risk_comfort}, and simulated round-ups are {roundups}. "
        "Nothing here is a live ETF position."
    )


def _available_to_invest(user, payload) -> str:
    surplus = compute_investable_surplus(user)
    return (
        f"Estimated investable surplus is ${surplus.investable_surplus}. "
        "That estimate is not a brokerage buying power figure, and no trade has been created."
    )


def _invested_this_month(user, payload) -> str:
    from django.db.models import Sum

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = (
        SimulatedOrder.objects.filter(
            user=user,
            status=SimulatedOrder.Status.FILLED,
            filled_at__gte=month_start,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return (
        f"Simulated filled orders this month total ${total}. "
        "These are not brokerage executions."
    )


def _withdraw_unsupported(user, payload) -> str:
    return (
        "Withdrawals to a bank account are not available. "
        "No transfer provider is connected, so nothing was requested, pending, or completed."
    )


def _monthly_target_unsupported(user, payload) -> str:
    return (
        "Finovate does not store a separate monthly savings target. "
        "You can change a goal's target amount, for example: set my Trip goal to $2000."
    )


IMMEDIATE_HANDLERS = {
    "budget_status": _budget_status,
    "goal_status": _goal_status,
    "pause_roundups": _pause_roundups,
    "portfolio_performance": _portfolio_performance,
    "allocation": _allocation,
    "available_to_invest": _available_to_invest,
    "invested_this_month": _invested_this_month,
    "withdraw_unsupported": _withdraw_unsupported,
    "monthly_target_unsupported": _monthly_target_unsupported,
    "market_status": lambda user, payload: MARKET_STATUS_REPLY,
}


# --- Confirmation-gated intents ---------------------------------------------

def _prompt_report_income(user, payload) -> str | None:
    amount = payload.get("amount")
    if not amount:
        return None
    return f"Record ${amount} as income today? This will add a transaction."


def _execute_report_income(user, payload) -> str:
    amount = Decimal(payload["amount"])
    record_transaction(
        user, kind=Transaction.Kind.INCOME, amount=amount, occurred_on=timezone.now().date(),
        description="Reported via assistant", source="manual",
    )
    return f"Recorded ${amount} income for today."


def _prompt_set_risk_comfort(user, payload) -> str | None:
    level = payload.get("level")
    if not level:
        return None
    return f"Set your risk comfort to \"{level}\"?"


def _execute_set_risk_comfort(user, payload) -> str:
    level = payload["level"]
    user.profile.risk_comfort = level
    user.profile.save(update_fields=["risk_comfort", "updated_at"])
    return f"Done — risk comfort set to \"{level}\"."


def _find_goal(user, name_hint: str):
    qs = Goal.objects.filter(user=user)
    if name_hint:
        matches = [g for g in qs if name_hint in g.name.lower()]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"That matches more than one goal: {', '.join(g.name for g in matches)}. Be more specific."
    if qs.count() == 1:
        return qs.first(), None
    # Every user also has three default pools; a lone goal the user created
    # themselves is still unambiguous. The change still needs a "yes".
    custom = qs.filter(pool_kind="")
    if custom.count() == 1:
        return custom.first(), None
    return None, "I couldn't tell which goal you meant — include part of its name."


def _prompt_update_goal_target(user, payload) -> str | None:
    amount = payload.get("amount")
    if not amount:
        return None
    goal, error = _find_goal(user, payload.get("name_hint", ""))
    if error:
        payload["_error"] = error
        return None
    payload["goal_id"] = goal.pk
    return f"Set \"{goal.name}\"'s target to ${amount}?"


def _execute_update_goal_target(user, payload) -> str:
    goal = Goal.objects.filter(user=user, pk=payload["goal_id"]).first()
    if not goal:
        return "That goal no longer exists."
    goal.target_amount = Decimal(payload["amount"])
    goal.save(update_fields=["target_amount", "updated_at"])
    return f"Done — \"{goal.name}\"'s target is now ${goal.target_amount}."


def _prompt_propose_invest(user, payload) -> str | None:
    amount = payload.get("amount")
    if not amount or Decimal(amount) <= 0:
        return None
    surplus = compute_investable_surplus(user).investable_surplus
    return (
        f"Create a simulated pending proposal to invest ${amount}? "
        f"Estimated investable surplus is ${surplus}. "
        "This does not place a brokerage order or move money. "
        "Approving it later on the Investments page is still simulated."
    )


def _execute_propose_invest(user, payload) -> str:
    amount = Decimal(payload["amount"])
    surplus = compute_investable_surplus(user).investable_surplus
    if amount > surplus:
        return (
            f"Not created. ${amount} is above the estimated investable surplus of ${surplus}. "
            "No proposal was saved."
        )
    order = propose_surplus_investment(user, amount)
    if user.profile.notify_simulated_orders:
        NotificationEvent.objects.create(
            user=user,
            event_type=NotificationEvent.EventType.SYSTEM,
            message=f"Simulated investment proposal for ${order.amount} is pending. This is not a brokerage order.",
            delivery_status="recorded",
        )
    return (
        f"Saved a simulated pending proposal for ${order.amount}. "
        f"Status: {order.status}. No brokerage is connected, so this is not a trade."
    )


def _prompt_resume_roundups(user, payload) -> str:
    return "Resume round-up investing? New eligible purchases will start generating round-ups again."


def _execute_resume_roundups(user, payload) -> str:
    rs = get_or_create_settings(user)
    rs.is_paused = False
    rs.save(update_fields=["is_paused", "updated_at"])
    return "Done — round-ups are resumed."


CONFIRMATION_PROMPTS = {
    "report_income": _prompt_report_income,
    "set_risk_comfort": _prompt_set_risk_comfort,
    "update_goal_target": _prompt_update_goal_target,
    "propose_invest": _prompt_propose_invest,
    "resume_roundups": _prompt_resume_roundups,
}

CONFIRMATION_EXECUTORS = {
    "report_income": _execute_report_income,
    "set_risk_comfort": _execute_set_risk_comfort,
    "update_goal_target": _execute_update_goal_target,
    "propose_invest": _execute_propose_invest,
    "resume_roundups": _execute_resume_roundups,
}

CONFIRMATION_REQUIRED = set(CONFIRMATION_PROMPTS)


def _execute(user, intent: str, payload: dict) -> str:
    if intent in IMMEDIATE_HANDLERS:
        return IMMEDIATE_HANDLERS[intent](user, payload)
    if intent in CONFIRMATION_EXECUTORS:
        return CONFIRMATION_EXECUTORS[intent](user, payload)
    return "I'm not sure how to do that."
