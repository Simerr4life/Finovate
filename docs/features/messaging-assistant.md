# Messaging assistant

**Last reviewed:** 2026-10-11

## 1. Feature overview

- **Purpose:** Answer finance questions / gated actions via Spectrum webhook.
- **Intended users:** Users who linked messaging in Settings
- **Permissions:** Authenticated user owning the data (unless noted)
- **Dependencies / prerequisites:** Webhook secret; link code; Spectrum project
- **Related:** See [feature inventory](../feature-inventory.md)



## 2. User interface walkthrough

No primary web page — Settings messaging link + webhook. See [messaging-assistant.md](../messaging-assistant.md).

## 3. Step-by-step workflow

Issue link code → user texts code → chat binds `photon_chat_id` → intents handled → confirmations for sensitive actions.

## 4. Business logic

Keyword/regex intents in `assistant/intents.py`; reject withdraw invention etc.

## 5. Technical implementation

`assistant/views.py`, `services.py`, `spectrum.py`, models PendingConfirmation, MessagingLinkCode.

## 6. Errors and edge cases

Bad signature → reject. Idempotent delivery keys. Django replies `delivered: false`.

## 7. Testing and acceptance criteria

`assistant/tests.py`; local `manage.py chat_demo`.
