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
- `/assistant/photon-webhook/` — a Django view that accepts a JSON POST
  and returns `{"reply": "..."}`. Tested with the Django test client
  (valid payload, unknown sender, missing fields, bad JSON, wrong secret).

**Unverified — the one real assumption in this feature:**
Photon's own published docs for the iMessage adapter
(`chat-adapter-imessage` skill) state plainly: *"This method is not
supported. The adapter does not use traditional webhooks for message
ingestion."* The primary integration path is a **Node.js SDK**
(`startGatewayListener()` / `adapter.postMessage(threadId, message)`),
not a REST webhook a Django view can receive directly.

The docs do mention an **optional self-hosted webhook** with a
`NativeWebhookPayload` shape (`guid`, `text`, `sender`, `chatId`, plus
other Basic Kit Message fields) — that's what `/assistant/photon-webhook/`
is built against. But no example request/response JSON or auth header
name was published alongside it, so three things are unverified until you
have a real Spectrum line to test against:

1. **Exact field names** in the incoming JSON (I used `chatId`/`text`;
   real payloads may differ or include more fields).
2. **Auth header/scheme** — the view checks a configurable
   `X-Photon-Webhook-Secret` header against `PHOTON_WEBHOOK_SECRET`, but
   Photon's actual signing scheme (if any) is undocumented here.
3. **Whether a webhook response is even how replies get sent.** If
   Spectrum requires the Node SDK's `postMessage()` for outbound
   messages, `/assistant/photon-webhook/`'s `{"reply": ...}` response body
   won't actually reach the user — you'd need a small Node.js sidecar
   that calls `startGatewayListener()`, forwards incoming text to this
   Django endpoint, and calls `postMessage()` with whatever this endpoint
   returns. That sidecar does not exist yet; it's the next piece if the
   webhook assumption turns out wrong.

**When you have a real Spectrum line:** send it one test message, check
what actually hits `/assistant/photon-webhook/` (or wherever Photon
actually sends to), and adjust `assistant/views.py::photon_webhook`
accordingly. The intent logic in `services.py` needs no changes either
way — only the transport adapter does.

## Linking a Finovate account to a chat

`Profile.photon_chat_id` holds the chat/sender id Photon identifies a
conversation by. It's empty until set — there's no UI for it yet (small
scope decision to avoid building a settings form for an unverified
field); set it directly via the Django admin or shell:

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
