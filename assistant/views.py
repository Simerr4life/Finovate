"""Inbound Photon Spectrum transports.

1. `/assistant/photon-webhook/` — Spectrum Cloud / self-hosted webhooks
   (signature verified). Returns reply JSON; does not send iMessage.
2. `/assistant/bridge/` — called by the Node Spectrum adapter in
   `spectrum/`, which both receives and sends over iMessage.
"""

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .routing import process_inbound_chat
from .spectrum import parse_inbound, verify_signature, webhook_secret

logger = logging.getLogger(__name__)


def _reject(reason: str):
    if reason in {"stale_timestamp", "malformed_timestamp", "missing_headers"}:
        return JsonResponse({"error": reason}, status=400)
    return JsonResponse({"error": "unauthorized"}, status=401)


def hmac_equal(provided: str, secret: str) -> bool:
    if len(provided) != len(secret):
        return False
    import hmac

    return hmac.compare_digest(provided, secret)


def bridge_secret(settings_obj) -> str:
    return (
        getattr(settings_obj, "ASSISTANT_BRIDGE_SECRET", "")
        or getattr(settings_obj, "IMESSAGE_PROJECT_SECRET", "")
        or ""
    )


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

    result = process_inbound_chat(
        parsed.get("chat_id") or "",
        parsed.get("text") or "",
        delivery_id=webhook_id,
        message_id=message_id,
    )
    if not result.get("ok"):
        return JsonResponse({"error": result.get("error") or "bad_request"}, status=400)
    if result.get("duplicate"):
        logger.info("spectrum webhook duplicate webhook_id=%s", webhook_id)
        return JsonResponse({"ok": True, "duplicate": True, "delivered": False})

    logger.info("spectrum webhook accepted webhook_id=%s", webhook_id or "none")
    return JsonResponse({"reply": result["reply"], "delivered": False, "linked": result.get("linked", False)})


@csrf_exempt
@require_POST
def spectrum_bridge(request):
    """JSON bridge for the Node Spectrum adapter.

    Auth: `X-Finovate-Bridge-Secret` must match `ASSISTANT_BRIDGE_SECRET`
    (or `IMESSAGE_PROJECT_SECRET` as a fallback). Outside DEBUG, a missing
    secret rejects every call.
    """
    expected = bridge_secret(settings)
    provided = request.headers.get("X-Finovate-Bridge-Secret", "")
    if expected:
        if not provided or not hmac_equal(provided, expected):
            return JsonResponse({"error": "unauthorized"}, status=401)
    elif not settings.DEBUG:
        logger.error("Spectrum bridge is not configured: set ASSISTANT_BRIDGE_SECRET")
        return JsonResponse({"error": "bridge secret is not configured"}, status=503)

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    result = process_inbound_chat(
        str(payload.get("chat_id") or payload.get("space_id") or ""),
        str(payload.get("text") or ""),
        delivery_id=str(payload.get("delivery_id") or "bridge"),
        message_id=str(payload.get("message_id") or ""),
    )
    if not result.get("ok"):
        return JsonResponse({"error": result.get("error") or "bad_request"}, status=400)
    if result.get("duplicate"):
        return JsonResponse({"ok": True, "duplicate": True, "reply": ""})
    return JsonResponse({
        "ok": True,
        "duplicate": False,
        "reply": result["reply"],
        "linked": result.get("linked", False),
    })
