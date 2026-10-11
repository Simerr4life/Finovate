"""Shared inbound chat routing for Spectrum webhook and Node bridge.

Both transports resolve a chat to a Finovate user (or redeem a one-time
link code), then run the same assistant brain. Delivery over iMessage is
the Node Spectrum adapter's job — Django only returns the reply text.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .linking import redeem_link_code
from .models import SpectrumDelivery
from .services import handle_incoming_message

User = get_user_model()

UNLINKED_REPLY = "This chat isn't linked to a Finovate account yet."
LINKED_REPLY = (
    "This chat is now linked to your Finovate account. "
    "Confirm it in Settings, then ask me about your budget or goals."
)


def already_delivered(delivery_id: str, message_id: str) -> bool:
    """Record a delivery attempt. Return True when this pair was seen before."""
    if not delivery_id or not message_id:
        return False
    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            _, created = SpectrumDelivery.objects.get_or_create(
                webhook_id=delivery_id[:255],
                message_id=message_id[:255],
            )
    except IntegrityError:
        return True
    return not created


def process_inbound_chat(
    chat_id: str,
    text: str,
    *,
    delivery_id: str = "",
    message_id: str = "",
) -> dict:
    """Route one inbound text message. Never raises for unknown chats.

    Returns a dict with keys used by both transports:
      ok, duplicate, reply, linked, error
    """
    chat_id = (chat_id or "").strip()
    text = (text or "").strip()
    if not chat_id or not text:
        return {"ok": False, "error": "missing chat_id or text"}

    if already_delivered(delivery_id, message_id):
        return {"ok": True, "duplicate": True, "reply": "", "linked": False}

    user = User.objects.filter(profile__photon_chat_id=chat_id).first()
    if user is None:
        linked = redeem_link_code(text, chat_id)
        if linked is None:
            return {"ok": True, "duplicate": False, "reply": UNLINKED_REPLY, "linked": False}
        return {"ok": True, "duplicate": False, "reply": LINKED_REPLY, "linked": True}

    reply = handle_incoming_message(user, text)
    return {"ok": True, "duplicate": False, "reply": reply, "linked": False}
