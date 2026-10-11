"""Keep round-up ledger entries in step with the purchases they came from.

Every way a transaction is recorded (manual entry, statement import, the
messaging assistant, demo seeding) ends in a Transaction save, so this is
the one place round-ups are created rather than each caller remembering to.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from core.services import round_up_to_nearest
from transactions.models import Transaction


@receiver(post_save, sender=Transaction, dispatch_uid="investing_roundup_for_transaction")
def sync_roundup_for_transaction(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from .models import RoundUpLedgerEntry
    from .services import (
        create_roundup_for_transaction,
        get_or_create_settings,
        reverse_roundup_for_transaction,
    )

    if created:
        create_roundup_for_transaction(instance)
        return

    entry = RoundUpLedgerEntry.objects.filter(source_transaction=instance).first()
    if entry is None or entry.status != RoundUpLedgerEntry.Status.PENDING:
        # Swept entries already count toward the simulated portfolio, so an
        # edit to the purchase afterwards doesn't rewrite that history.
        return
    instance.roundup_entry = entry
    if instance.kind != Transaction.Kind.EXPENSE or instance.reverses_id is not None:
        reverse_roundup_for_transaction(instance)
        return
    if entry.eligible_amount == instance.amount:
        return
    new_amount = round_up_to_nearest(instance.amount, get_or_create_settings(instance.user).round_to)
    if new_amount <= 0:
        reverse_roundup_for_transaction(instance)
        return
    entry.eligible_amount = instance.amount
    entry.round_up_amount = new_amount
    entry.save(update_fields=["eligible_amount", "round_up_amount", "updated_at"])
