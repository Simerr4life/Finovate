from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import NotificationEvent
from core.idempotency import claim_submission
from investing.models import PortfolioSnapshot

from .forms import ContributionForm, GoalForm, SavingsPlanForm
from .models import Goal, SavingsPlan
from .planning import (
    DEFAULT_POOLS,
    allocate,
    pool_plan_rows,
    recalculate_plan,
    suggested_rainy_day_target,
)
from .services import MILESTONES, contribution_pace, estimate_completion_date


def plan_context(user, today=None):
    """Everything a page needs to show the automated plan. Recalculates first
    (idempotent) so figures always reflect the latest income and expenses."""
    result = recalculate_plan(user, today=today)
    plan, capacity = result.plan, result.capacity
    rows = pool_plan_rows(plan, today=today)
    preview = allocate(capacity.available, plan.percents())
    return {
        "savings_plan": plan,
        "capacity": capacity,
        "plan_rows": rows,
        "plan_total": sum((row.recommended_monthly for row in rows), Decimal("0.00")),
        "plan_total_per_period": sum((row.recommended_per_period for row in rows), Decimal("0.00")),
        "plan_preview": [
            {"name": spec["name"], "kind": spec["pool_kind"], "color": spec["color"],
             "percent": plan.percents()[spec["pool_kind"]], "amount": preview[spec["pool_kind"]]}
            for spec in DEFAULT_POOLS
        ],
        "suggested_rainy_target": suggested_rainy_day_target(capacity),
        "unreachable_targets": [row for row in rows if row.target_unreachable],
    }


@login_required
def index(request):
    from investing.services import compute_investable_surplus

    goals = list(Goal.objects.filter(user=request.user))
    saved = sum((g.current_amount for g in goals), Decimal("0"))
    surplus = compute_investable_surplus(request.user)
    context = {
        "goals": goals,
        "saved_total": saved,
        "surplus": surplus,
    }
    context.update(plan_context(request.user))
    return render(request, "savings/index.html", context)


@login_required
def pools(request):
    context = plan_context(request.user)
    goals = list(Goal.objects.filter(user=request.user))
    custom = [goal for goal in goals if not goal.is_default_pool]
    pool_rows = [
        {"goal": goal, "estimated_completion": estimate_completion_date(goal)}
        for goal in custom
    ]
    context.update(
        {
            "pool_rows": pool_rows,
            "saved_total": sum((goal.current_amount for goal in goals), Decimal("0")),
            "target_total": sum((goal.target_amount for goal in goals), Decimal("0")),
            "pool_count": len(goals),
            "plan_form": SavingsPlanForm(instance=context["savings_plan"]),
        }
    )
    return render(request, "savings/pools.html", context)


@login_required
@require_POST
def plan_update(request):
    plan, _ = SavingsPlan.objects.get_or_create(user=request.user)
    form = SavingsPlanForm(request.POST, instance=plan)
    if not form.is_valid():
        context = plan_context(request.user)
        goals = list(Goal.objects.filter(user=request.user))
        context.update(
            {
                "pool_rows": [
                    {"goal": g, "estimated_completion": estimate_completion_date(g)}
                    for g in goals if not g.is_default_pool
                ],
                "saved_total": sum((g.current_amount for g in goals), Decimal("0")),
                "target_total": sum((g.target_amount for g in goals), Decimal("0")),
                "pool_count": len(goals),
                "plan_form": form,
            }
        )
        messages.error(request, "Your plan wasn't saved. Check the highlighted fields.")
        return render(request, "savings/pools.html", context, status=400)
    with transaction.atomic():
        form.save()
    recalculate_plan(request.user)
    status = form.cleaned_data["status"]
    if status == SavingsPlan.Status.PAUSED:
        messages.success(request, "Savings plan paused. Recommendations are on hold until you resume it.")
    elif status == SavingsPlan.Status.DISABLED:
        messages.success(request, "Savings plan turned off. Your pools and their balances are unchanged.")
    else:
        messages.success(request, "Savings plan saved and recalculated.")
    return redirect(f"{reverse("savings:pools")}#plan")


@login_required
@require_POST
def apply_suggested_target(request, pk):
    pool = get_object_or_404(Goal, pk=pk, user=request.user, pool_kind=Goal.PoolKind.RAINY_DAY)
    suggested = suggested_rainy_day_target(recalculate_plan(request.user).capacity)
    if suggested is None:
        messages.error(request, "Add your income and expenses first so we can suggest a target.")
    else:
        pool.target_amount = suggested
        if pool.current_amount < suggested:
            pool.achieved_at = None
        pool.save(update_fields=["target_amount", "achieved_at", "updated_at"])
        messages.success(request, f"{pool.name} target set to ${suggested:,.2f} (about 3 months of costs).")
    return redirect(f"{reverse("savings:pools")}#pool-{pool.pk}")


@login_required
def goals(request):
    # Default pools only appear as goals once they have a target.
    goals = [
        goal for goal in Goal.objects.filter(user=request.user)
        if not goal.is_default_pool or goal.has_target
    ]
    today = timezone.localdate()
    goal_rows = []
    for goal in goals:
        row = {
            "goal": goal,
            "estimated_completion": estimate_completion_date(goal),
            "pace": None,
            "deadline_passed": False,
        }
        if goal.remaining_amount <= 0:
            row["next_milestone_percent"] = 100
            row["next_milestone_amount"] = Decimal("0.00")
        else:
            next_milestone = next(
                (milestone for milestone in MILESTONES if goal.progress_percent < milestone),
                100,
            )
            milestone_target = (
                goal.target_amount * Decimal(next_milestone) / Decimal("100")
            ).quantize(Decimal("0.01"))
            row["next_milestone_percent"] = next_milestone
            row["next_milestone_amount"] = max(
                milestone_target - goal.current_amount, Decimal("0.00")
            )
            if goal.target_date:
                row["pace"] = contribution_pace(
                    goal.remaining_amount, goal.target_date, today=today
                )
                row["deadline_passed"] = goal.target_date <= today and goal.remaining_amount > 0
        goal_rows.append(row)

    saved = sum((row["goal"].current_amount for row in goal_rows), Decimal("0.00"))
    remaining_total = sum(
        (row["goal"].remaining_amount for row in goal_rows), Decimal("0.00")
    )
    monthly = Decimal("0")
    on_track = 0
    for row in goal_rows:
        goal = row["goal"]
        if goal.achieved_at or goal.progress_percent >= 100:
            on_track += 1
        elif row["pace"]:
            on_track += 1
        row["monthly"] = row["pace"]["monthly"] if row["pace"] else None
        if row["monthly"]:
            monthly += row["monthly"]
    return render(
        request,
        "savings/goals.html",
        {
            "goal_rows": goal_rows,
            "saved_total": saved,
            "remaining_total": remaining_total,
            "monthly_total": monthly,
            "on_track": on_track,
            "goal_count": len(goal_rows),
            "today": today,
        },
    )


@login_required
def goal_add(request):
    return_to_pools = (
        request.GET.get("from") == "pools" or request.POST.get("from") == "pools"
    )
    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Savings goal created.")
            return redirect("savings:pools" if return_to_pools else "savings:index")
    else:
        form = GoalForm()
    return render(
        request,
        "savings/goal_form.html",
        {"form": form, "mode": "add", "return_to_pools": return_to_pools},
    )


@login_required
def goal_edit(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    return_to_pools = (
        goal.is_default_pool
        or request.GET.get("from") == "pools"
        or request.POST.get("from") == "pools"
    )
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect("savings:pools" if return_to_pools else "savings:index")
    else:
        form = GoalForm(instance=goal)
    return render(
        request,
        "savings/goal_form.html",
        {"form": form, "mode": "edit", "return_to_pools": return_to_pools, "goal": goal},
    )


@login_required
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if goal.is_default_pool:
        messages.error(request, f"{goal.name} is one of your three default pools and can't be deleted. You can rename it or change its target instead.")
        return redirect("savings:pools")
    if request.method == "POST":
        goal.delete()
        messages.success(request, "Goal deleted.")
        return redirect("savings:index")
    return render(request, "confirm_delete.html", {"object": goal, "cancel_url": "savings:index"})


@login_required
def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        form = ContributionForm(request.POST, goal=goal)
        if form.is_valid() and not claim_submission(request, request.POST.get("idempotency_key")):
            messages.info(request, "That entry was already recorded, so it wasn't added twice.")
            return redirect("savings:goal_detail", pk=goal.pk)
        if form.is_valid():
            from .services import apply_contribution

            _, crossed = apply_contribution(
                goal,
                kind=form.cleaned_data["kind"],
                amount=form.cleaned_data["amount"],
                note=form.cleaned_data["note"],
                source="manual",
            )
            if crossed and request.user.profile.notify_goal_milestones:
                NotificationEvent.objects.create(
                    user=request.user,
                    event_type=NotificationEvent.EventType.GOAL_MILESTONE,
                    message=f'"{goal.name}" reached {crossed}% of its target.',
                )
                messages.success(request, f'Nice! "{goal.name}" just reached {crossed}%.')
            else:
                messages.success(request, "Contribution recorded.")
            return redirect("savings:goal_detail", pk=goal.pk)
    else:
        initial = {}
        suggested = request.GET.get("amount")
        if suggested:
            try:
                value = Decimal(suggested)
                if value > 0:
                    initial["amount"] = value.quantize(Decimal("0.01"))
            except (ArithmeticError, ValueError):
                pass
        form = ContributionForm(goal=goal, initial=initial)
    invested_snapshot = None
    if goal.is_investable:
        invested_snapshot = PortfolioSnapshot.objects.filter(user=request.user, pool=goal).order_by("-as_of").first()
    return render(
        request,
        "savings/goal_detail.html",
        {
            "goal": goal,
            "form": form,
            "estimated_completion": estimate_completion_date(goal),
            "contributions": goal.contributions.all()[:25],
            "milestone_percents": MILESTONES,
            "invested_snapshot": invested_snapshot,
        },
    )
