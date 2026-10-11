from decimal import Decimal

from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import NotificationEvent
from investing.models import PortfolioSnapshot

from .forms import ContributionForm, DebtObligationForm, GoalForm, PlanAllocationForm
from .models import DebtObligation, Goal, SavingsPlan
from .plan_engine import ensure_default_pools, get_or_build_plan, refresh_savings_plan
from .services import MILESTONES, contribution_pace, estimate_completion_date


@login_required
def index(request):
    from investing.services import compute_investable_surplus

    ensure_default_pools(request.user)
    goals = list(Goal.objects.filter(user=request.user))
    saved = sum((g.current_amount for g in goals), Decimal("0"))
    emergency = next(
        (g for g in goals if g.system_key == Goal.SystemKey.RAINY_DAY),
        next((g for g in goals if g.category == Goal.Category.EMERGENCY), None),
    )
    surplus = compute_investable_surplus(request.user)
    plan = get_or_build_plan(request.user)
    return render(
        request,
        "savings/index.html",
        {
            "goals": goals,
            "saved_total": saved,
            "emergency": emergency,
            "surplus": surplus,
            "plan": plan,
        },
    )


@login_required
def plan_detail(request):
    plan = get_or_build_plan(request.user)
    pools = ensure_default_pools(request.user)
    revisions = []
    if plan is not None:
        revisions = plan.revisions.all()[:10]
    return render(
        request,
        "savings/plan.html",
        {
            "plan": plan,
            "pools": pools,
            "revisions": revisions,
            "allocation_form": PlanAllocationForm(
                initial={
                    "rainy_day_percent": plan.rainy_day_percent if plan else 20,
                    "investment_percent": plan.investment_percent if plan else 30,
                    "regular_percent": plan.regular_percent if plan else 50,
                }
            )
            if plan
            else None,
        },
    )


@login_required
@require_POST
def plan_refresh(request):
    plan = refresh_savings_plan(request.user, reason="user_refresh", force=True)
    if plan is None:
        messages.error(
            request,
            "Not enough income or expense information yet to build a savings plan. "
            "Add income sources or recurring expenses first.",
        )
    else:
        messages.success(request, "Savings plan recalculated from your latest numbers.")
    return redirect("savings:plan")


@login_required
@require_POST
def plan_status(request):
    plan = get_object_or_404(SavingsPlan, user=request.user)
    action = request.POST.get("action")
    if action == "pause":
        plan.status = SavingsPlan.Status.PAUSED
        plan.save(update_fields=["status", "updated_at"])
        messages.success(request, "Recommendations paused. No money was moved.")
    elif action == "resume":
        plan.status = SavingsPlan.Status.ACTIVE
        plan.save(update_fields=["status", "updated_at"])
        refresh_savings_plan(request.user, reason="resumed", force=True)
        messages.success(request, "Recommendations resumed.")
    elif action == "disable":
        plan.status = SavingsPlan.Status.DISABLED
        plan.save(update_fields=["status", "updated_at"])
        messages.success(request, "Recommendations disabled. You can turn them back on here at any time.")
    else:
        messages.error(request, "That action isn't available.")
    return redirect("savings:plan")


@login_required
@require_POST
def plan_allocations(request):
    plan = get_object_or_404(SavingsPlan, user=request.user)
    form = PlanAllocationForm(request.POST)
    if form.is_valid():
        plan.rainy_day_percent = form.cleaned_data["rainy_day_percent"]
        plan.investment_percent = form.cleaned_data["investment_percent"]
        plan.regular_percent = form.cleaned_data["regular_percent"]
        plan.user_override_percents = True
        plan.save(
            update_fields=[
                "rainy_day_percent",
                "investment_percent",
                "regular_percent",
                "user_override_percents",
                "updated_at",
            ]
        )
        refresh_savings_plan(request.user, reason="allocation_edit", force=True)
        messages.success(request, "Allocation percentages updated. Totals still use your safe-to-save amount.")
    else:
        messages.error(request, "Allocation percentages must add up to 100%.")
    return redirect("savings:plan")


@login_required
def debt_list(request):
    debts = DebtObligation.objects.filter(user=request.user)
    return render(request, "savings/debts.html", {"debts": debts})


@login_required
def debt_add(request):
    if request.method == "POST":
        form = DebtObligationForm(request.POST)
        if form.is_valid():
            debt = form.save(commit=False)
            debt.user = request.user
            debt.save()  # the savings signals recalculate the plan on commit
            messages.success(request, "Debt recorded for planning. No payment was made.")
            return redirect("savings:debts")
    else:
        form = DebtObligationForm()
    return render(request, "savings/debt_form.html", {"form": form, "mode": "add"})


@login_required
def debt_edit(request, pk):
    debt = get_object_or_404(DebtObligation, pk=pk, user=request.user)
    if request.method == "POST":
        form = DebtObligationForm(request.POST, instance=debt)
        if form.is_valid():
            form.save()  # the savings signals recalculate the plan on commit
            messages.success(request, "Debt updated.")
            return redirect("savings:debts")
    else:
        form = DebtObligationForm(instance=debt)
    return render(request, "savings/debt_form.html", {"form": form, "mode": "edit", "debt": debt})


@login_required
def pools(request):
    ensure_default_pools(request.user)
    goals = list(Goal.objects.filter(user=request.user))
    pool_rows = [
        {"goal": goal, "estimated_completion": estimate_completion_date(goal)}
        for goal in goals
    ]
    saved_total = sum((goal.current_amount for goal in goals), Decimal("0"))
    target_total = sum((goal.target_amount for goal in goals), Decimal("0"))
    return render(
        request,
        "savings/pools.html",
        {
            "pool_rows": pool_rows,
            "saved_total": saved_total,
            "target_total": target_total,
            "pool_count": len(pool_rows),
        },
    )


@login_required
def goals(request):
    goals = Goal.objects.filter(user=request.user)
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
            refresh_savings_plan(request.user, reason="goal_created")
            messages.success(request, "Savings goal created.")
            return redirect("savings:pools" if return_to_pools else "savings:goals")
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
        request.GET.get("from") == "pools" or request.POST.get("from") == "pools"
    )
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            refresh_savings_plan(request.user, reason="goal_updated")
            messages.success(request, "Goal updated.")
            return redirect("savings:pools" if return_to_pools else "savings:goals")
    else:
        form = GoalForm(instance=goal)
    return render(
        request,
        "savings/goal_form.html",
        {"form": form, "mode": "edit", "return_to_pools": return_to_pools},
    )


@login_required
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if goal.system_key:
        # Default pools are recreated (empty) on the next page load, so a
        # delete would only look like it worked while wiping the balance.
        messages.error(
            request,
            f'"{goal.name}" is one of your default pools and can\'t be deleted. '
            "You can rename it, change its target, or withdraw its balance instead.",
        )
        return redirect("savings:goal_detail", pk=goal.pk)
    if request.method == "POST":
        goal.delete()
        messages.success(request, "Goal deleted.")
        return redirect("savings:goals")
    return render(request, "confirm_delete.html", {"object": goal, "cancel_url": "savings:goals"})


@login_required
def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        form = ContributionForm(request.POST, goal=goal)
        if form.is_valid():
            from .services import apply_contribution

            _, crossed = apply_contribution(
                goal,
                kind=form.cleaned_data["kind"],
                amount=form.cleaned_data["amount"],
                note=form.cleaned_data["note"],
                source="manual",
            )
            refresh_savings_plan(request.user, reason="contribution")
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
        form = ContributionForm(goal=goal)
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
