"""Keep default pools and the savings plan in step with the user's finances.

Pools are created when an account is created. Plan recalculation runs after
the surrounding transaction commits, so a failed save never leaves a plan
computed from data that was rolled back.
"""

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from budgets.models import Budget, BudgetPeriod, IncomeSource, RecurringExpense

from .models import DebtObligation


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_pools_for_new_user(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    from .plan_engine import ensure_default_pools

    # Pools only — do not build a plan here. Plan refresh can create investing
    # RoundUpSettings as a side effect and should wait until finances exist.
    ensure_default_pools(instance)


def _schedule_recalculation(sender, instance, raw=False, **kwargs):
    if raw:
        return
    user_id = instance.user_id

    def _run():
        from django.contrib.auth import get_user_model

        from .plan_engine import refresh_savings_plan

        user = get_user_model().objects.filter(pk=user_id).first()
        if user is None:
            return
        refresh_savings_plan(user, reason=f"{sender._meta.model_name}_changed")

    transaction.on_commit(_run)


for _model in (IncomeSource, RecurringExpense, Budget, BudgetPeriod, DebtObligation):
    post_save.connect(
        _schedule_recalculation,
        sender=_model,
        dispatch_uid=f"savings_recalc_save_{_model.__name__}",
    )
    post_delete.connect(
        _schedule_recalculation,
        sender=_model,
        dispatch_uid=f"savings_recalc_delete_{_model.__name__}",
    )
