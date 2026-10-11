# Account management

**Last reviewed:** 2026-10-11

## Profile

Auto-created on User create (`accounts/signals.py`). Stores preferences, theme, Auth0/Supabase ids, messaging fields, manual setup estimates, onboarding flag.

## Settings lifecycle

See [user-guide/settings.md](../user-guide/settings.md).

## Notification events

Types include budget_warning, goal_milestone, roundup_paused, account_created, welcome, system. **Recorded only** — no email/push/SMS sender.

## Connected accounts

`ConnectedAccountPlaceholder` — metadata statuses only; no credentials stored.
