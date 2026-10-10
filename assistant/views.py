"""Webhook receiver for Photon's Spectrum (iMessage) self-hosted "optional
webhook" delivery mode.

IMPORTANT — this is the one part of the assistant that's unverified
against the real Photon service. The payload shape below
(guid/text/sender/chatId) comes from Photon's published
chat-adapter-imessage documentation, but no example request/response JSON
or auth header name was published alongside it. Once you have a real
Spectrum line, you'll likely need to adjust:
  - the exact field names in the incoming JSON
  - the auth header name/scheme (currently checks X-Photon-Webhook-Secret)
  - whether Photon expects the reply in the HTTP response body at all, or
    requires a separate outbound call (the primary documented path uses
    a Node.js adapter's postMessage(), which this Django view can't call
    directly)
See docs/messaging-assistant.md for the full writeup.
"""

import json

from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import handle_incoming_message

User = get_user_model()


@csrf_exempt
@require_POST
def photon_webhook(request):
    if settings.PHOTON_WEBHOOK_SECRET:
        provided = request.headers.get("X-Photon-Webhook-Secret", "")
        if provided != settings.PHOTON_WEBHOOK_SECRET:
            return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid JSON"}, status=400)

    chat_id = payload.get("chatId") or payload.get("sender") or ""
    text = payload.get("text") or ""

    if not chat_id or not text:
        return JsonResponse({"error": "missing chatId/sender or text"}, status=400)

    user = User.objects.filter(profile__photon_chat_id=chat_id).first()
    if user is None:
        # Deliberately generic: don't confirm/deny whether a chat id is
        # registered to anything, and don't 500 on an unrecognized sender.
        return JsonResponse({"reply": "This chat isn't linked to a Finovate account yet."})

    reply = handle_incoming_message(user, text)
    return JsonResponse({"reply": reply})
