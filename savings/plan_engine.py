"""Personalized savings-plan engine.

Analyzes income, expenses, debts, emergency reserves, and goals, then
recommends a scenario-specific allocation across the three default pools.
Recommendations are never transfers or investment orders.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import NotificationEvent
from budgets.models import IncomeSource, RecurringExpense
from budgets.services import monthly_equivalent
from core.services import quantize_money
from investing.services import available_cash_balance, get_or_create_settings
from transactions.models import Transaction

from .models import DebtObligation, Goal, SavingsPlan, SavingsPlanRevision

HIGH_INTEREST_APR = Decimal("10.00")
STARTER_EMERGENCY_FLOOR = Decimal("500.00")
STARTER_EMERGENCY_CAP = Decimal("1000.00")
# Default split for the STABLE scenario and any normalize fallback.
# Configurable via PlanAllocationForm / user_override_percents; must total 100.
FALLBACK_RAINY = Decimal("40")
FALLBACK_INVEST = Decimal("20")
FALLBACK_REGULAR = Decimal("40")
RECALC_DOLLAR_THRESHOLD = Decimal("25.00")
RECALC_PERCENT_THRESHOLD = Decimal("0.05")

ESSENTIAL_KEYWORDS = (
    "housing", "rent", "mortgage", "utilities", "internet", "electric",
    "water", "gas bill", "groceries", "household", "food", "transport",
    "transportation", "insurance", "healthcare", "health", "debt", "loan",
    "minimum", "childcare", "phone", "essential",
)
DISCRETIONARY_KEYWORDS = (
    "subscription", "streaming", "entertainment", "dining", "restaurant",
    "coffee", "hobby", "shopping", "want",
)

DEFAULT_POOLS = (
    {
        "system_key": Goal.SystemKey.RAINY_DAY,
        "name": "Rainy Day",
        "category": Goal.Category.EMERGENCY,
        "color": "#2F6F4E",
        "is_investable": False,
        "target_amount": STARTER_EMERGENCY_CAP,
    },
    {
        "system_key": Goal.SystemKey.INVESTMENT,
        "name": "Investment",
        "category": Goal.Category.OTHER,
        "color": "#1F3A5F",
        "is_investable": True,
        "target_amount": Decimal("10000.00"),
    },
    {
        "system_key": Goal.SystemKey.REGULAR,
        "name": "Regular Savings",
        "category": Goal.Category.OTHER,
        "color": "#C4A35A",
        "is_investable": False,
        "target_amount": Decimal("5000.00"),
    },
)


@dataclass
class GoalAdvice:
    goal_id: int
    name: str
    remaining: Decimal
    required_monthly: Decimal | None
    realistic: bool
    note: str


@dataclass
class FinancialAnalysis:
    monthly_income: Decimal
    monthly_essential: Decimal
    monthly_discretionary: Decimal
    monthly_expenses: Decimal
    monthly_surplus: Decimal
    additional_buffer: Decimal
    safe_to_save: Decimal
    emergency_balance: Decimal
    emergency_starter_target: Decimal
    emergency_full_target: Decimal
    total_debt_balance: Decimal
    high_interest_debt_balance: Decimal
    monthly_debt_minimums: Decimal
    income_unstable: bool
    cash_balance: Decimal
    needs_share: Decimal
    wants_share: Decimal
    savings_share: Decimal
    has_enough_data: bool
    assumptions: list[str] = field(default_factory=list)
    goal_advice: list[GoalAdvice] = field(default_factory=list)


@dataclass
class PlanRecommendation:
    scenario: str
    name: str
    objective: str
    explanation: str
    priority: str
    rainy_day_percent: Decimal
    investment_percent: Decimal
    regular_percent: Decimal
    rainy_day_amount: Decimal
    investment_amount: Decimal
    regular_amount: Decimal
    debt_extra_amount: Decimal
    estimated_completion_date: date | None
    warnings: list[str]
    goal_notes: list[dict]
    analysis: FinancialAnalysis
    fingerprint: str


def ensure_default_pools(user) -> dict[str, Goal]:
    """Create the three system pools when missing. Never resets balances."""
    pools: dict[str, Goal] = {}
    for spec in DEFAULT_POOLS:
        key = spec["system_key"]
        goal = Goal.objects.filter(user=user, system_key=key).first()
        if goal is None:
            # Adopt a same-named user goal once, instead of duplicating.
            goal = Goal.objects.filter(user=user, system_key="", name=spec["name"]).first()
            if goal is not None:
                goal.system_key = key
                if key == Goal.SystemKey.RAINY_DAY and goal.category != Goal.Category.EMERGENCY:
                    goal.category = Goal.Category.EMERGENCY
                if key == Goal.SystemKey.INVESTMENT:
                    goal.is_investable = True
                goal.save()
            else:
                try:
                    with transaction.atomic():
                        goal, _ = Goal.objects.get_or_create(
                            user=user,
                            system_key=key,
                            defaults={
                                "name": spec["name"],
                                "category": spec["category"],
                                "color": spec["color"],
                                "is_investable": spec["is_investable"],
                                "target_amount": spec["target_amount"],
                                "current_amount": Decimal("0.00"),
                            },
                        )
                except IntegrityError:
                    goal = Goal.objects.get(user=user, system_key=key)
        pools[key] = goal
    return pools


def _expense_bucket(name: str) -> str:
    lowered = (name or "").lower()
    if any(token in lowered for token in ESSENTIAL_KEYWORDS):
        return "essential"
    if any(token in lowered for token in DISCRETIONARY_KEYWORDS):
        return "discretionary"
    # Unknown recurring costs are treated as essential to avoid overstating surplus.
    return "essential"


def _months_until(target: date | None, today: date | None = None) -> int | None:
    if target is None:
        return None
    today = today or timezone.localdate()
    if target <= today:
        return 0
    days = (target - today).days
    return max(1, int((Decimal(days) / Decimal("30.44")).to_integral_value()))


def analyze_finances(user, today: date | None = None) -> FinancialAnalysis:
    today = today or timezone.localdate()
    assumptions = [
        "Income and expenses are normalized to a monthly basis.",
        "Transfers/reimbursements (non-earned income categories) are excluded from take-home income.",
        "This is a planning recommendation, not a transfer and not financial advice.",
    ]

    monthly_income = Decimal("0")
    for src in IncomeSource.objects.filter(user=user, is_active=True):
        monthly_income += monthly_equivalent(src.amount, src.cadence)

    if monthly_income <= 0:
        # Fall back to average earned income over the last 90 days.
        start = today - timedelta(days=90)
        earned = (
            Transaction.objects.filter(
                user=user,
                kind=Transaction.Kind.INCOME,
                occurred_on__gte=start,
                occurred_on__lte=today,
            )
            .exclude(category__is_earned_income=False)
            .values_list("amount", flat=True)
        )
        total = sum(earned, Decimal("0"))
        if total > 0:
            monthly_income = quantize_money(total / Decimal("3"))
            assumptions.append(
                "No active income sources were set, so take-home income is estimated "
                "from earned transactions in the last 90 days."
            )

    monthly_essential = Decimal("0")
    monthly_discretionary = Decimal("0")
    for exp in RecurringExpense.objects.filter(user=user, is_active=True):
        amount = monthly_equivalent(exp.amount, exp.cadence)
        if _expense_bucket(exp.name) == "discretionary":
            monthly_discretionary += amount
        else:
            monthly_essential += amount

    debts = list(DebtObligation.objects.filter(user=user, is_active=True))
    monthly_debt_minimums = quantize_money(
        sum((d.minimum_payment for d in debts), Decimal("0"))
    )
    # Avoid double-counting minimums already named as debt expenses.
    debt_expense_names = [
        exp.name.lower()
        for exp in RecurringExpense.objects.filter(user=user, is_active=True)
        if "debt" in exp.name.lower() or "loan" in exp.name.lower()
    ]
    if not debt_expense_names and monthly_debt_minimums > 0:
        monthly_essential += monthly_debt_minimums
        assumptions.append(
            "Debt minimum payments from DebtObligation were added to essential expenses "
            "because no debt-named recurring expense was found."
        )

    monthly_income = quantize_money(monthly_income)
    monthly_essential = quantize_money(monthly_essential)
    monthly_discretionary = quantize_money(monthly_discretionary)
    monthly_expenses = quantize_money(monthly_essential + monthly_discretionary)
    monthly_surplus = quantize_money(monthly_income - monthly_expenses)

    profile = getattr(user, "profile", None)
    income_unstable = bool(profile and profile.income_cadence == "irregular")
    checking_buffer = Decimal("0")
    if profile and profile.cash_reserve_target > 0:
        # Spread the checking reserve target across ~3 months as a monthly buffer piece.
        checking_buffer = quantize_money(profile.cash_reserve_target / Decimal("3"))
    else:
        rs = get_or_create_settings(user)
        if rs.minimum_cash_reserve > 0:
            checking_buffer = quantize_money(rs.minimum_cash_reserve / Decimal("3"))

    # Irregular-bill buffer: half a month of essential costs, or more if income is unstable.
    irregular_buffer = quantize_money(monthly_essential * (Decimal("0.50") if income_unstable else Decimal("0.25")))
    additional_buffer = quantize_money(checking_buffer + irregular_buffer)
    # Do not subtract obligations already inside monthly_expenses.
    safe_to_save = quantize_money(max(Decimal("0"), monthly_surplus - additional_buffer))

    pools = ensure_default_pools(user)
    rainy = pools[Goal.SystemKey.RAINY_DAY]
    emergency_balance = quantize_money(rainy.current_amount)
    # Also count other emergency-category goals toward the reserve.
    for goal in Goal.objects.filter(user=user, category=Goal.Category.EMERGENCY).exclude(
        system_key=Goal.SystemKey.RAINY_DAY
    ):
        emergency_balance = quantize_money(emergency_balance + goal.current_amount)

    starter = max(STARTER_EMERGENCY_FLOOR, min(STARTER_EMERGENCY_CAP, monthly_essential))
    if monthly_essential <= 0:
        starter = STARTER_EMERGENCY_FLOOR
    months_cover = Decimal("6") if income_unstable else Decimal("3")
    full_target = quantize_money(max(starter, monthly_essential * months_cover))
    if rainy.target_amount < full_target:
        rainy.target_amount = full_target
        rainy.save(update_fields=["target_amount", "updated_at"])

    total_debt = quantize_money(sum((d.balance for d in debts), Decimal("0")))
    high_interest = quantize_money(
        sum((d.balance for d in debts if d.interest_rate_apr >= HIGH_INTEREST_APR), Decimal("0"))
    )

    goal_advice: list[GoalAdvice] = []
    for goal in Goal.objects.filter(user=user, achieved_at__isnull=True).exclude(
        system_key__in=[
            Goal.SystemKey.RAINY_DAY,
            Goal.SystemKey.INVESTMENT,
            Goal.SystemKey.REGULAR,
        ]
    ):
        remaining = quantize_money(max(Decimal("0"), goal.target_amount - goal.current_amount))
        months = _months_until(goal.target_date, today)
        if months is None:
            required = None
            realistic = True
            note = "No deadline set — contribute what surplus allows after higher priorities."
        elif months == 0 and remaining > 0:
            required = remaining
            realistic = False
            note = "Deadline has passed with a remaining balance; extend the timeline or lower the target."
        else:
            required = quantize_money(remaining / Decimal(months)) if months else remaining
            realistic = required <= safe_to_save if safe_to_save > 0 else False
            if not realistic:
                if safe_to_save > 0:
                    extended = int((remaining / safe_to_save).to_integral_value()) + 1
                    note = (
                        f"Needs about {required} per month to hit the deadline, which exceeds "
                        f"the current safe-to-save amount. A more realistic timeline is about "
                        f"{extended} month(s) at today's surplus."
                    )
                else:
                    note = "No safe monthly surplus is available for this goal right now."
            else:
                note = f"About {required} per month reaches the target by {goal.target_date}."
        goal_advice.append(
            GoalAdvice(
                goal_id=goal.id,
                name=goal.name,
                remaining=remaining,
                required_monthly=required,
                realistic=realistic,
                note=note,
            )
        )

    has_enough_data = monthly_income > 0 or monthly_expenses > 0 or emergency_balance > 0
    zero = Decimal("0")
    needs_share = quantize_money(monthly_essential / monthly_income) if monthly_income > 0 else zero
    wants_share = quantize_money(monthly_discretionary / monthly_income) if monthly_income > 0 else zero
    savings_share = quantize_money(safe_to_save / monthly_income) if monthly_income > 0 else zero

    return FinancialAnalysis(
        monthly_income=monthly_income,
        monthly_essential=monthly_essential,
        monthly_discretionary=monthly_discretionary,
        monthly_expenses=monthly_expenses,
        monthly_surplus=monthly_surplus,
        additional_buffer=additional_buffer,
        safe_to_save=safe_to_save,
        emergency_balance=emergency_balance,
        emergency_starter_target=quantize_money(starter),
        emergency_full_target=full_target,
        total_debt_balance=total_debt,
        high_interest_debt_balance=high_interest,
        monthly_debt_minimums=monthly_debt_minimums,
        income_unstable=income_unstable,
        cash_balance=available_cash_balance(user),
        needs_share=needs_share,
        wants_share=wants_share,
        savings_share=savings_share,
        has_enough_data=has_enough_data,
        assumptions=assumptions,
        goal_advice=goal_advice,
    )


def choose_scenario(analysis: FinancialAnalysis) -> str:
    if analysis.monthly_income > 0 and analysis.monthly_expenses > analysis.monthly_income:
        return SavingsPlan.Scenario.STABILIZATION
    if analysis.monthly_surplus < 0:
        return SavingsPlan.Scenario.STABILIZATION
    if analysis.emergency_balance < analysis.emergency_starter_target:
        return SavingsPlan.Scenario.BUILD_RESERVE
    if analysis.high_interest_debt_balance > 0:
        return SavingsPlan.Scenario.DEBT_FOCUS
    if (
        analysis.emergency_balance >= analysis.emergency_full_target
        and analysis.safe_to_save >= max(Decimal("200"), analysis.monthly_income * Decimal("0.15"))
        and analysis.total_debt_balance == 0
    ):
        return SavingsPlan.Scenario.STRONG
    return SavingsPlan.Scenario.STABLE


def _normalize_percents(rainy: Decimal, invest: Decimal, regular: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    total = rainy + invest + regular
    if total <= 0:
        return FALLBACK_RAINY, FALLBACK_INVEST, FALLBACK_REGULAR
    rainy = quantize_money(rainy * Decimal("100") / total)
    invest = quantize_money(invest * Decimal("100") / total)
    regular = quantize_money(Decimal("100") - rainy - invest)
    return rainy, invest, regular


def _split_amount(safe: Decimal, rainy_p: Decimal, invest_p: Decimal, regular_p: Decimal):
    rainy_p, invest_p, regular_p = _normalize_percents(rainy_p, invest_p, regular_p)
    rainy_amt = quantize_money(safe * rainy_p / Decimal("100"))
    invest_amt = quantize_money(safe * invest_p / Decimal("100"))
    regular_amt = quantize_money(safe - rainy_amt - invest_amt)
    if regular_amt < 0:
        regular_amt = Decimal("0.00")
        # Adjust for rounding so we never exceed safe-to-save.
        invest_amt = quantize_money(safe - rainy_amt)
    return rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt


def build_recommendation(analysis: FinancialAnalysis, override_percents: dict | None = None) -> PlanRecommendation:
    scenario = choose_scenario(analysis)
    warnings: list[str] = []
    debt_extra = Decimal("0.00")
    safe = analysis.safe_to_save

    if scenario == SavingsPlan.Scenario.STABILIZATION:
        rainy_p = invest_p = regular_p = Decimal("0")
        name = "Stabilization plan"
        objective = "Cover essentials and stop the monthly shortfall before increasing savings."
        priority = "critical"
        explanation = (
            "Your monthly expenses leave limited room for saving. This plan focuses on "
            "covering essentials and minimum obligations rather than allocating money you do not have."
        )
        if analysis.monthly_surplus < 0:
            warnings.append(
                f"Monthly shortfall of {quantize_money(abs(analysis.monthly_surplus))} — "
                "review discretionary spending or increase take-home income before optional savings."
            )
        safe = Decimal("0.00")
    elif scenario == SavingsPlan.Scenario.BUILD_RESERVE:
        rainy_p, invest_p, regular_p = Decimal("80"), Decimal("5"), Decimal("15")
        name = "Starter emergency reserve"
        objective = "Build an initial Rainy Day fund before other optional goals."
        priority = "high"
        explanation = (
            "Your emergency savings are below your initial target, so more of your available "
            "savings are being directed toward your Rainy Day fund."
        )
        if analysis.needs_share > Decimal("0.50"):
            warnings.append(
                f"Essential expenses are about {int(analysis.needs_share * 100)}% of take-home income, "
                "above the 50% needs guideline — the 50/30/20 split is not forced."
            )
    elif scenario == SavingsPlan.Scenario.DEBT_FOCUS:
        rainy_p, invest_p, regular_p = Decimal("20"), Decimal("10"), Decimal("20")
        # 50% of safe-to-save toward high-interest debt extras (not a pool percent).
        debt_share = Decimal("50")
        name = "Debt payoff with reserve maintained"
        objective = "Keep the emergency buffer and direct extra cash to high-interest debt."
        priority = "high"
        explanation = (
            "Your emergency reserve is started, and high-interest debt remains, so additional "
            "available funds are prioritized for debt payoff before larger investment contributions."
        )
        debt_extra = quantize_money(safe * debt_share / Decimal("100"))
        safe_for_pools = quantize_money(safe - debt_extra)
        if override_percents:
            rainy_p = Decimal(str(override_percents.get("rainy_day", rainy_p)))
            invest_p = Decimal(str(override_percents.get("investment", invest_p)))
            regular_p = Decimal(str(override_percents.get("regular", regular_p)))
        rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt = _split_amount(
            safe_for_pools, rainy_p, invest_p, regular_p
        )
        return _finish_recommendation(
            analysis, scenario, name, objective, explanation, priority,
            rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt,
            debt_extra, warnings, safe,
        )
    elif scenario == SavingsPlan.Scenario.STRONG:
        rainy_p, invest_p, regular_p = Decimal("10"), Decimal("40"), Decimal("50")
        name = "Strong capacity plan"
        objective = "Maintain reserves and accelerate long-term and medium-term goals."
        priority = "normal"
        explanation = (
            "Your emergency reserve is established and debt looks manageable, so more of your "
            "available savings can go toward long-term goals and regular savings."
        )
    else:
        rainy_p, invest_p, regular_p = FALLBACK_RAINY, FALLBACK_INVEST, FALLBACK_REGULAR
        name = "Balanced savings plan"
        objective = "Maintain the emergency reserve and fund investment and regular savings goals."
        priority = "normal"
        explanation = (
            "Your emergency reserve is established, so more of your available savings can go "
            "toward your long-term goals."
        )
        if analysis.needs_share > Decimal("0.50"):
            warnings.append(
                "Needs exceed the 50% guideline; allocations use your safe-to-save amount, "
                "not a forced 50/30/20 split."
            )

    if override_percents:
        rainy_p = Decimal(str(override_percents.get("rainy_day", rainy_p)))
        invest_p = Decimal(str(override_percents.get("investment", invest_p)))
        regular_p = Decimal(str(override_percents.get("regular", regular_p)))

    rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt = _split_amount(
        safe, rainy_p, invest_p, regular_p
    )
    return _finish_recommendation(
        analysis, scenario, name, objective, explanation, priority,
        rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt,
        debt_extra, warnings, safe,
    )


def _finish_recommendation(
    analysis, scenario, name, objective, explanation, priority,
    rainy_p, invest_p, regular_p, rainy_amt, invest_amt, regular_amt,
    debt_extra, warnings, safe_total,
) -> PlanRecommendation:
    allocated = quantize_money(rainy_amt + invest_amt + regular_amt + debt_extra)
    if allocated > analysis.safe_to_save:
        warnings.append("Allocation capped so recommendations never exceed safe-to-save.")
    for advice in analysis.goal_advice:
        if not advice.realistic:
            warnings.append(f'Goal "{advice.name}": {advice.note}')

    months_to_starter = None
    remaining_emergency = max(
        Decimal("0"), analysis.emergency_starter_target - analysis.emergency_balance
    )
    if rainy_amt > 0 and remaining_emergency > 0:
        months_to_starter = int((remaining_emergency / rainy_amt).to_integral_value()) + 1
    estimated = None
    if months_to_starter:
        estimated = timezone.localdate() + timedelta(days=30 * months_to_starter)

    goal_notes = [
        {
            "goal_id": g.goal_id,
            "name": g.name,
            "remaining": str(g.remaining),
            "required_monthly": str(g.required_monthly) if g.required_monthly is not None else None,
            "realistic": g.realistic,
            "note": g.note,
        }
        for g in analysis.goal_advice
    ]
    fingerprint = _fingerprint(analysis, scenario, safe_total)
    return PlanRecommendation(
        scenario=scenario,
        name=name,
        objective=objective,
        explanation=explanation,
        priority=priority,
        rainy_day_percent=rainy_p,
        investment_percent=invest_p,
        regular_percent=regular_p,
        rainy_day_amount=rainy_amt,
        investment_amount=invest_amt,
        regular_amount=regular_amt,
        debt_extra_amount=debt_extra,
        estimated_completion_date=estimated,
        warnings=warnings,
        goal_notes=goal_notes,
        analysis=analysis,
        fingerprint=fingerprint,
    )


def _fingerprint(analysis: FinancialAnalysis, scenario: str, safe: Decimal) -> str:
    payload = {
        "scenario": scenario,
        "income": str(quantize_money(analysis.monthly_income)),
        "expenses": str(quantize_money(analysis.monthly_expenses)),
        "safe": str(quantize_money(safe)),
        "emergency": str(quantize_money(analysis.emergency_balance)),
        "debt": str(quantize_money(analysis.high_interest_debt_balance)),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _materially_changed(plan: SavingsPlan, recommendation: PlanRecommendation) -> bool:
    if plan.fingerprint and plan.fingerprint == recommendation.fingerprint:
        return False
    if plan.scenario != recommendation.scenario:
        return True
    for old, new in (
        (plan.monthly_income, recommendation.analysis.monthly_income),
        (plan.monthly_expenses, recommendation.analysis.monthly_expenses),
        (plan.safe_to_save, recommendation.analysis.safe_to_save),
        (plan.emergency_balance, recommendation.analysis.emergency_balance),
    ):
        delta = abs(old - new)
        if delta >= RECALC_DOLLAR_THRESHOLD:
            return True
        base = max(old, new, Decimal("1"))
        if delta / base >= RECALC_PERCENT_THRESHOLD:
            return True
    return True


def _analysis_to_dict(analysis: FinancialAnalysis) -> dict:
    data = asdict(analysis)
    data["goal_advice"] = [
        {
            **item,
            "remaining": str(item["remaining"]),
            "required_monthly": str(item["required_monthly"])
            if item["required_monthly"] is not None
            else None,
        }
        for item in data["goal_advice"]
    ]
    for key, value in list(data.items()):
        if isinstance(value, Decimal):
            data[key] = str(value)
    return data


@transaction.atomic
def refresh_savings_plan(user, reason: str = "manual", force: bool = False) -> SavingsPlan | None:
    """Create or update the user's plan when data supports it.

    Idempotent for unchanged fingerprints. Respects paused/disabled status
    unless force=True (used when the user explicitly requests a refresh).
    """
    ensure_default_pools(user)
    analysis = analyze_finances(user)
    if not analysis.has_enough_data:
        return None

    plan = SavingsPlan.objects.filter(user=user).select_for_update().first()
    if plan and plan.status == SavingsPlan.Status.DISABLED and not force:
        return plan
    if plan and plan.status == SavingsPlan.Status.PAUSED and not force:
        return plan

    override = None
    if plan and plan.user_override_percents:
        override = {
            "rainy_day": plan.rainy_day_percent,
            "investment": plan.investment_percent,
            "regular": plan.regular_percent,
        }
    recommendation = build_recommendation(analysis, override_percents=override)

    created = plan is None
    if plan is None:
        plan = SavingsPlan(user=user, status=SavingsPlan.Status.ACTIVE)
    elif not force and not _materially_changed(plan, recommendation):
        return plan
    else:
        SavingsPlanRevision.objects.create(
            plan=plan,
            reason=reason,
            scenario=plan.scenario,
            safe_to_save=plan.safe_to_save,
            explanation=plan.explanation,
            snapshot={
                "rainy_day_amount": str(plan.rainy_day_amount),
                "investment_amount": str(plan.investment_amount),
                "regular_amount": str(plan.regular_amount),
                "debt_extra_amount": str(plan.debt_extra_amount),
                "analysis": plan.analysis,
            },
        )

    previous_fingerprint = plan.fingerprint
    plan.scenario = recommendation.scenario
    plan.name = recommendation.name
    plan.objective = recommendation.objective
    plan.explanation = recommendation.explanation
    plan.priority = recommendation.priority
    plan.monthly_income = analysis.monthly_income
    plan.monthly_expenses = analysis.monthly_expenses
    plan.monthly_surplus = analysis.monthly_surplus
    plan.safe_to_save = analysis.safe_to_save
    plan.additional_buffer = analysis.additional_buffer
    plan.rainy_day_percent = recommendation.rainy_day_percent
    plan.investment_percent = recommendation.investment_percent
    plan.regular_percent = recommendation.regular_percent
    plan.rainy_day_amount = recommendation.rainy_day_amount
    plan.investment_amount = recommendation.investment_amount
    plan.regular_amount = recommendation.regular_amount
    plan.debt_extra_amount = recommendation.debt_extra_amount
    plan.emergency_target = analysis.emergency_full_target
    plan.emergency_balance = analysis.emergency_balance
    plan.estimated_completion_date = recommendation.estimated_completion_date
    plan.warnings = recommendation.warnings
    plan.goal_notes = recommendation.goal_notes
    plan.analysis = _analysis_to_dict(analysis)
    plan.fingerprint = recommendation.fingerprint
    plan.calculated_at = timezone.now()
    if force and plan.status != SavingsPlan.Status.DISABLED:
        plan.status = SavingsPlan.Status.ACTIVE
    plan.save()
    if created or previous_fingerprint != plan.fingerprint:
        _record_plan_notification(user, plan, created=created, reason=reason)
    return plan


def _record_plan_notification(user, plan: SavingsPlan, *, created: bool, reason: str) -> None:
    if plan.monthly_surplus < 0:
        message = (
            "Your budget cannot support a positive savings target right now "
            f"(shortfall {quantize_money(abs(plan.monthly_surplus))})."
        )
    elif created:
        message = f"Savings plan ready: {plan.name}."
    else:
        message = f"Savings plan updated ({reason.replace('_', ' ')}): {plan.name}."
    NotificationEvent.objects.create(
        user=user,
        event_type=NotificationEvent.EventType.SAVINGS_PLAN,
        message=message[:255],
        delivery_status="recorded",
    )


def get_or_build_plan(user) -> SavingsPlan | None:
    plan = getattr(user, "savings_plan", None)
    if plan is None:
        plan = SavingsPlan.objects.filter(user=user).first()
    if plan is None:
        return refresh_savings_plan(user, reason="initial")
    if plan.status == SavingsPlan.Status.ACTIVE:
        return refresh_savings_plan(user, reason="view_refresh") or plan
    return plan
