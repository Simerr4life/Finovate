"""Inbound Photon Spectrum (iMessage) webhook.

Signature checks follow Photon's Stable webhook docs:
https://photon.codes/docs/webhooks/verifying-signatures

The HTTP response acknowledges the delivery. It does not mean Spectrum
delivered a reply over iMessage. Sending still requires the Node
chat-adapter-imessage client, which this Django process does not call.
"""

import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import SpectrumDelivery
from .linking import redeem_link_code
from .services import handle_incoming_message
from .spectrum import parse_inbound, verify_signature, webhook_secret

logger = logging.getLogger(__name__)
User = get_user_model()


def _reject(reason: str):
    if reason in {"stale_timestamp", "malformed_timestamp", "missing_headers"}:
        return JsonResponse({"error": reason}, status=400)
    return JsonResponse({"error": "unauthorized"}, status=401)


@csrf_exempt
@require_POST
def photon_webhook(request):
    secret = webhook_secret(settings)
    raw = request.body or b""
    signature = request.headers.get("X-Spectrum-Signature", "")
    timestamp = request.headers.get("X-Spectrum-Timestamp", "")
    legacy = request.headers.get("X-Photon-Webhook-Secret", "")

    if signature or timestamp:
        if not secret:
            logger.error("Spectrum webhook received a signature but no webhook secret is configured")
            return JsonResponse({"error": "webhook secret is not configured"}, status=503)
        reason = verify_signature(raw, timestamp, signature, secret)
        if reason:
            logger.info("spectrum webhook rejected reason=%s", reason)
            return _reject(reason)
    elif secret:
        if not legacy or not hmac_equal(legacy, secret):
            return JsonResponse({"error": "unauthorized"}, status=401)
    elif not settings.DEBUG:
        logger.error("Spectrum webhook is not configured: set IMESSAGE_WEBHOOK_SECRET")
        return JsonResponse({"error": "webhook secret is not configured"}, status=503)

    try:
        payload = json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    parsed = parse_inbound(payload)
    webhook_id = request.headers.get("X-Spectrum-Webhook-Id", "")
    message_id = parsed.get("message_id") or ""

    if parsed.get("skip"):
        return JsonResponse({"ok": True, "handled": False, "delivered": False})

    chat_id = parsed.get("chat_id") or ""
    text = parsed.get("text") or ""
    if not chat_id or not text:
        return JsonResponse({"error": "missing chatId/sender or text"}, status=400)

    if webhook_id and message_id and _already_delivered(webhook_id, message_id):
        logger.info("spectrum webhook duplicate webhook_id=%s", webhook_id)
        return JsonResponse({"ok": True, "duplicate": True, "delivered": False})

    user = User.objects.filter(profile__photon_chat_id=chat_id).first()
    if user is None:
        linked = redeem_link_code(text, chat_id)
        if linked is None:
            return JsonResponse({
                "reply": "This chat isn't linked to a Finovate account yet.",
                "delivered": False,
            })
        return JsonResponse({
            "reply": (
                "This chat is now linked to your Finovate account. "
                "Confirm it in Settings. This server does not send iMessage."
            ),
            "delivered": False,
        })

    reply = handle_incoming_message(user, text)
    logger.info("spectrum webhook accepted webhook_id=%s", webhook_id or "none")
    return JsonResponse({"reply": reply, "delivered": False})


def hmac_equal(provided: str, secret: str) -> bool:
    if len(provided) != len(secret):
        return False
    import hmac
    return hmac.compare_digest(provided, secret)


def _already_delivered(webhook_id: str, message_id: str) -> bool:
    try:
        with transaction.atomic():
            _, created = SpectrumDelivery.objects.get_or_create(
                webhook_id=webhook_id[:255],
                message_id=message_id[:255],
            )
    except IntegrityError:
        return True
    return not created
