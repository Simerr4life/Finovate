from decimal import Decimal

from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import NotificationEvent
from investing.models import PortfolioSnapshot

from .forms import ContributionForm, GoalForm
from .models import Goal
from .services import MILESTONES, estimate_completion_date


@login_required
def index(request):
    from investing.services import compute_investable_surplus

    goals = list(Goal.objects.filter(user=request.user))
    saved = sum((g.current_amount for g in goals), Decimal("0"))
    emergency = next((g for g in goals if g.category == Goal.Category.EMERGENCY), None)
    surplus = compute_investable_surplus(request.user)
    return render(
        request,
        "savings/index.html",
        {
            "goals": goals,
            "saved_total": saved,
            "emergency": emergency,
            "surplus": surplus,
        },
    )


@login_required
def pools(request):
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
    goal_rows = [
        {"goal": g, "estimated_completion": estimate_completion_date(g)} for g in goals
    ]
    saved = sum((row["goal"].current_amount for row in goal_rows), start=0)
    monthly = Decimal("0")
    on_track = 0
    for row in goal_rows:
        goal = row["goal"]
        if goal.achieved_at or goal.progress_percent >= 100:
            on_track += 1
        elif row["estimated_completion"]:
            on_track += 1
        if goal.target_date and not goal.achieved_at:
            months = max(
                ((goal.target_date.year - timezone.now().date().year) * 12)
                + (goal.target_date.month - timezone.now().date().month),
                1,
            )
            row["monthly"] = (goal.remaining_amount / months).quantize(Decimal("0.01"))
            monthly += row["monthly"]
        else:
            row["monthly"] = None
    return render(
        request,
        "savings/goals.html",
        {
            "goal_rows": goal_rows,
            "saved_total": saved,
            "monthly_total": monthly,
            "on_track": on_track,
            "goal_count": len(goal_rows),
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
        request.GET.get("from") == "pools" or request.POST.get("from") == "pools"
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
        {"form": form, "mode": "edit", "return_to_pools": return_to_pools},
    )


@login_required
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        goal.delete()
        messages.success(request, "Goal deleted.")
        return redirect("savings:index")
    return render(request, "confirm_delete.html", {"object": goal, "cancel_url": "savings:index"})


@login_required
def goal_detail(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        form = ContributionForm(request.POST)
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
        form = ContributionForm()
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
