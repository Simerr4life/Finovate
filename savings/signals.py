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


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_pools_for_new_user(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    from .planning import ensure_default_pools, ensure_plan

    ensure_default_pools(instance)
    ensure_plan(instance)


def _schedule_recalculation(sender, instance, raw=False, **kwargs):
    if raw:
        return
    user_id = instance.user_id
    from .planning import recalculate_for_user_id

    transaction.on_commit(lambda: recalculate_for_user_id(user_id))


for _model in (IncomeSource, RecurringExpense, Budget, BudgetPeriod):
    post_save.connect(_schedule_recalculation, sender=_model, dispatch_uid=f"savings_recalc_save_{_model.__name__}")
    post_delete.connect(_schedule_recalculation, sender=_model, dispatch_uid=f"savings_recalc_delete_{_model.__name__}")
