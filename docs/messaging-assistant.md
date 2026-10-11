# Messaging assistant (Photon/iMessage)

This documents the assistant feature added on top of Finovate's website:
a text-based interface that can report budget/portfolio status and make
confirmed changes to risk comfort, goal targets, income records, and
round-up pause state.

**Scope note:** the original Finovate project brief explicitly said not
to build iMessage/Photon integration "during this phase." The owner
explicitly asked to move forward with it anyway (having already installed
`@photon-ai/cli` and set up their own Photon account/login), so this
builds on that explicit, conscious override — not a default assumption.

## What's real vs. what's assumed

**Fully real and tested today, no Photon needed:**
- `assistant/intents.py` — keyword/regex intent recognition (no LLM, no
  external NLU — intentionally simple and offline).
- `assistant/services.py::handle_incoming_message(user, text)` — the
  entire brain: parses one message, enforces confirmation for any
  state-changing action, and calls the *same* service functions the
  website uses (`budgets.services`, `savings.services`,
  `investing.services`) so there's no duplicated business logic.
- `python manage.py chat_demo --username demo` — an interactive terminal
  loop against the real assistant logic. This is the recommended way to
  demo the feature; it has zero dependency on Photon actually working.
- `/assistant/photon-webhook/` — verifies Spectrum signatures and runs
  the assistant. `delivered` is false because this process does not send
  iMessage. Tested with signed fixtures, never a live Photon call.

**Photon Spectrum transport (verified against Stable docs):**

The provider is [Photon Spectrum](https://photon.codes/docs/integrations/chat-sdk),
not Proton Mail. Stable webhook docs:
[verifying signatures](https://photon.codes/docs/webhooks/verifying-signatures)
and [events](https://photon.codes/docs/webhooks/events).

`/assistant/photon-webhook/` accepts:

- Spectrum Cloud `messages` events (`event`, `space`, `message`), signed
  with `X-Spectrum-Signature` (`v0=` + HMAC-SHA256 of
  `v0:{timestamp}:{raw body}`), `X-Spectrum-Timestamp` (rejected when
  older than 5 minutes, HTTP 400), and deduped on
  `X-Spectrum-Webhook-Id` + `message.id`.
- The self-hosted `NativeWebhookPayload` fields `guid`, `text`,
  `sender`, and `chatId` from the chat-adapter-imessage skill.

The signing secret is `IMESSAGE_WEBHOOK_SECRET` (fallback
`PHOTON_WEBHOOK_SECRET`). Outside `DEBUG`, the endpoint rejects requests
when that secret is missing. Only text content with `direction` inbound
is passed to the assistant. Other content types are acknowledged and
ignored.

**Not implemented, because Photon does not document a Python send API:**
this process does not call `postMessage` or `thread.post`. The JSON
field `delivered` is always `false`. A reply in the response body is the
text the assistant computed; it is not an iMessage delivery receipt.
Sending that text over iMessage still requires the Node
`chat-adapter-imessage` client (`IMESSAGE_PROJECT_ID` and
`IMESSAGE_PROJECT_SECRET` for Spectrum Cloud). Do not treat `reply` as
proof the user received a message.

Link a chat by storing Spectrum `space.id` (or the legacy `chatId`) on
`Profile.photon_chat_id`. Tests sign requests locally and never call
Photon.

## Linking a Finovate account to a chat

`Profile.photon_chat_id` holds the Spectrum `space.id` (or the legacy
`chatId`). It stays empty until you set it in the Django admin or shell:

```python
user.profile.photon_chat_id = "<id from your Photon dashboard>"
user.profile.save()
```

## Supported intents

| You say (examples) | What happens |
|---|---|
| "how's my budget" | Reports each category's spent/limit for the active budget period. Read-only. |
| "how's my portfolio doing" | Reports simulated contributions/value/gain per bucket, stating they're simulated. Read-only. |
| "how's the market today" | Honest "no live feed" reply — Finovate has no live market data connection. Read-only. |
| "I got paid $500" | Proposes recording $500 income today. **Requires "yes" to confirm.** |
| "set my risk to high/medium/low" | Proposes updating `Profile.risk_comfort`. **Requires confirmation.** |
| "set my Trip goal to $2000" | Finds a goal by name fragment (asks for clarification if ambiguous) and proposes changing its target. **Requires confirmation.** |
| "pause round-ups" | Pauses immediately — no confirmation, since pausing automation is the safe direction. |
| "resume round-ups" | Proposes re-enabling round-ups. **Requires confirmation** — turning automation back on is the riskier direction. |
| "help" | Lists what the assistant can do. |

Any message outside these patterns gets an honest "I didn't understand
that" reply rather than a guess.

## Safety rules enforced

- Exactly one `PendingConfirmation` per user; it's always re-queried from
  the database rather than read off a cached model attribute, specifically
  because Django's reverse-OneToOne accessor caches on the Python
  instance — reusing a stale cached object was a real bug caught by the
  test suite (`test_pending_confirmation_is_fresh_not_stale_cached_relation`)
  and would otherwise silently resurface an already-resolved confirmation
  in any long-lived process (like `chat_demo`).
- No money-affecting or preference-changing intent executes without an
  explicit "yes" in a separate message.
- The webhook never reveals whether a `chatId` is registered — unknown
  senders get a generic "not linked" reply, not a 404/error that would
  help enumerate valid chat ids.
- `ConversationMessage` logs both directions for audit, but never logs
  anything beyond the message text itself (no extra account/balance
  fields bundled in).
