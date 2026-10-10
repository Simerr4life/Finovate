from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import NotificationEvent
from investing.models import PortfolioSnapshot

from .forms import ContributionForm, GoalForm
from .models import Goal
from .services import MILESTONES, estimate_completion_date


@login_required
def index(request):
    goals = Goal.objects.filter(user=request.user)
    goal_rows = [
        {"goal": g, "estimated_completion": estimate_completion_date(g)} for g in goals
    ]
    return render(
        request,
        "savings/index.html",
        {"goal_rows": goal_rows, "form": GoalForm()},
    )


@login_required
def goal_add(request):
    if request.method == "POST":
        form = GoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, "Savings goal created.")
            return redirect("savings:index")
    else:
        form = GoalForm()
    return render(request, "savings/goal_form.html", {"form": form, "mode": "add"})


@login_required
def goal_edit(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        form = GoalForm(request.POST, instance=goal)
        if form.is_valid():
            form.save()
            messages.success(request, "Goal updated.")
            return redirect("savings:index")
    else:
        form = GoalForm(instance=goal)
    return render(request, "savings/goal_form.html", {"form": form, "mode": "edit"})


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
