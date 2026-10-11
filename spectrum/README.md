# spectrum

Finovate's [Spectrum](https://photon.codes/docs/spectrum-ts) transport for iMessage.
This process receives messages, asks Django's assistant brain for a reply, and
delivers that reply over Spectrum. Django itself never sends iMessage.

## Setup

From your project Settings on the [Photon dashboard](https://app.photon.codes):

1. Copy `.env.example` to `.env`
2. Set `PROJECT_ID` and `PROJECT_SECRET`
3. Point `FINOVATE_URL` at a running Finovate server
4. Set the same bridge secret on both sides:
   - here: `ASSISTANT_BRIDGE_SECRET` (or reuse `PROJECT_SECRET`)
   - Django: `ASSISTANT_BRIDGE_SECRET` or `IMESSAGE_PROJECT_SECRET`

```bash
bun install
bun start
```

For a local TUI without Photon credentials:

```bash
SPECTRUM_PROVIDERS=terminal FINOVATE_URL=http://127.0.0.1:8000 bun start
```

Link a chat from Finovate Settings (one-time code), then text that code from
the Spectrum conversation.

## See also

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- Finovate messaging writeup: [`../docs/messaging-assistant.md`](../docs/messaging-assistant.md)
