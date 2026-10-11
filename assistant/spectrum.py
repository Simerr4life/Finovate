"""Photon Spectrum Cloud webhook verification and payload parsing.

The provider is Photon Spectrum (iMessage), documented at
https://photon.codes/docs/webhooks/verifying-signatures (Stable).
Outbound sends are handled by the Node adapter in `spectrum/`, which
calls `/assistant/bridge/` and delivers with Spectrum's reply APIs.
"""

import hashlib
import hmac
import time
from typing import Any

REPLAY_TOLERANCE_SECONDS = 300


def webhook_secret(settings) -> str:
    return (getattr(settings, "IMESSAGE_WEBHOOK_SECRET", "") or getattr(settings, "PHOTON_WEBHOOK_SECRET", "") or "")


def verify_signature(raw_body: bytes, timestamp: str, signature: str, secret: str, now: float | None = None) -> str:
    """Return "" when the signature is valid, otherwise a reason code.

    Reasons: missing_headers, malformed_timestamp, stale_timestamp, invalid_signature.
    Stale timestamps are a 400; signature mismatches are a 401. See the
    Stable verifying-signatures page.
    """
    if not timestamp or not signature:
        return "missing_headers"
    try:
        stamp = int(timestamp)
    except (TypeError, ValueError):
        return "malformed_timestamp"
    current = time.time() if now is None else now
    if abs(current - stamp) > REPLAY_TOLERANCE_SECONDS:
        return "stale_timestamp"
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return "invalid_signature"
    base = f"v0:{timestamp}:{body_text}".encode()
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    if len(expected) != len(signature) or not hmac.compare_digest(expected, signature):
        return "invalid_signature"
    return ""


def parse_inbound(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract a text message, or mark the delivery as something to ignore.

    Supports the Spectrum `messages` event and the self-hosted
    NativeWebhookPayload fields (guid, text, sender, chatId) from the
    chat-adapter-imessage skill. Unknown content types are ignored rather
    than treated as commands.
    """
    if payload.get("event") == "messages":
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        message_id = str(message.get("id") or "")
        direction = message.get("direction")
        if direction not in (None, "inbound"):
            return {"skip": True, "message_id": message_id}
        content = message.get("content") if isinstance(message.get("content"), dict) else {}
        if content.get("type") not in (None, "text"):
            return {"skip": True, "message_id": message_id}
        space = payload.get("space") if isinstance(payload.get("space"), dict) else {}
        if not space and isinstance(message.get("space"), dict):
            space = message["space"]
        sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
        chat_id = str(space.get("id") or sender.get("id") or "")
        text = content.get("text") or ""
        return {"skip": False, "chat_id": chat_id, "text": text if isinstance(text, str) else "", "message_id": message_id}

    text = payload.get("text")
    chat_id = payload.get("chatId") or payload.get("sender") or ""
    return {
        "skip": False,
        "chat_id": str(chat_id),
        "text": text if isinstance(text, str) else "",
        "message_id": str(payload.get("guid") or ""),
    }
