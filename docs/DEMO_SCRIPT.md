# Demo Script

Every step below uses a feature verified on 2026-10-11 (see [TESTING_AND_VALIDATION.md](TESTING_AND_VALIDATION.md)). Steps that depend on credentials are marked **[needs config]**, each with a verified fallback. Say "simulated" whenever investing appears on screen.

**Setup assumed:** signed in as a user with sample data (`seed_demo` + `seed_peachtree_demo`). Numbers on screen depend on the date and your data; read them from the screen rather than from this script. Have a terminal open with `python manage.py chat_demo --username demo` as the messaging fallback.

**Data honesty line (say it once, early):** *"Everything you'll see uses sample data, and the investing side is a simulation: no bank or brokerage is connected, and no money moves."*

---

## 1. 60-second pitch

| Time | Narration | On screen | Judge takeaway |
|---|---|---|---|
| 0:00–0:10 | "Budgets, savings goals, and investing usually live in three apps that don't talk to each other, so people guess what's actually spare." | Landing page | The problem |
| 0:10–0:25 | "Finovate puts them in one place, built on one rule: every dollar has a purpose. Cash, goal money, pending round-ups, and investments are always separate numbers." | Dashboard | Core idea |
| 0:25–0:40 | "Our savings engine reads your income and bills, picks a scenario, and tells you exactly how much is safe to save, with its reasoning on screen." | Savings plan | Explainable |
| 0:40–0:52 | "Round-ups, investing, even text messages: nothing changes until you approve it." | Investing ledger → chat confirmation | User control |
| 0:52–1:00 | "Finovate. Make your money move, and always know why." | Logo | Close |

## 2. Recommended 3-minute demo

| Time | Narration | Action | Expected result | Takeaway |
|---|---|---|---|---|
| 0:00–0:15 | Problem + data honesty line | Landing page | — | Context, honesty |
| 0:15–0:35 | "Signing in uses Auth0. Finovate never sees a password, and accounts are tied to Auth0's user ID, never just an email." | **[needs config]** Get started → Continue with Auth0. *Fallback:* already signed in; mention it and show Settings → Security & privacy | Lands on dashboard | Auth0 track, security |
| 0:35–1:00 | "The dashboard separates total cash, this month's flow, and what's safe to save. The chart is built only from recorded transactions." | Dashboard; switch the chart to **1M** | Daily points render | Clarity, separated money |
| 1:00–1:20 | "Adding a coffee: $4.35." | Transactions → **Add transaction**, expense, 4.35 → Save | Row appears | Real persistence |
| 1:20–1:40 | "Because round-ups are on, that purchase now has a $0.65 round-up, marked **Pending**, not invested. A sweep only happens within my cash reserve and cap." | Investments → Round-up ledger | "+$0.65 · Pending" entry at the top | Transparent pending state |
| 1:40–2:05 | "Here's the savings plan. Income minus bills minus a safety buffer is my safe-to-save. The engine picked this scenario and split it across Rainy Day, Investment, and Regular Savings, and it explains why." | Savings → Savings plan | Scenario, split, "How we read your numbers" | Explainable engine |
| 2:05–2:25 | "Goals show the pace needed: weekly, monthly, yearly. Milestones at 25, 50, 75, and 100%." | Financial Goals → a goal → add a $25 contribution | Progress updates; milestone message if one is crossed | Goals |
| 2:25–2:50 | "Same brain over text. Recording income asks first." | **[needs config]** iMessage via Photon. *Fallback:* `chat_demo` terminal: `I got paid $500` → `yes`; `withdraw $50` | Confirmation prompt, then recorded; withdrawal refused | Photon track, consent |
| 2:50–3:00 | "Finovate: clear numbers, explained decisions, and you approve every change." | Dashboard (new income visible) | Website reflects the chat change | One shared backend |

## 3. Extended 5-minute presentation

Use the 3-minute flow and add:

| Insert after | Time | Narration | Action | Takeaway |
|---|---|---|---|---|
| Dashboard | +0:40 | "Bring your own data: upload a bank CSV. We auto-detect columns, skip duplicates, and flag rows we can't read instead of guessing." | Settings → Statement imports → Import a statement → a CSV → choose account → review | Real import, data integrity |
| Import | +0:25 | "Statements reconcile: computed deposits, withdrawals, and ending balance are checked against what the statement claims." | Statements → Peachtree demo | Accounting rigor |
| Round-ups | +0:30 | "Proposals need approval. Here's the investable surplus: cash minus my reserve, goal money, and a month of bills. I propose an amount; it stays pending until I approve it, and I can't propose the same surplus twice." | Investments → Propose → Approve | Guardrails |
| Plan | +0:25 | "If I pause recommendations, adding a debt or recalculating doesn't silently turn them back on." | Pause → Debts → add a card at 24% APR → back to plan: still Paused | Control |
| Close | +0:20 | Mobile view and dark mode | Resize or show screenshots 22–26 | Polish |

## 4. Closing pitch (≈30 s)

"Most finance apps either show you numbers or move your money. Finovate explains the numbers and never moves anything without your yes. We separate cash from goals from investments, show every assumption, and use the same logic on the web and over iMessage. Next come a read-only bank connection, notification delivery, and a brokerage partner behind the approval flow we already built. That's Finovate: make your money move, and always know why."

## What not to say

- Don't say trades were "executed," money was "invested," or a bank is "connected."
- Don't claim the bundled market sample is live data, or that Explore works without the Twelve Data key.
- Don't claim GoDaddy integration unless the team has shown evidence ([THIRD_PARTY_SERVICES.md §3](THIRD_PARTY_SERVICES.md#3-godaddy)).
- Don't promise returns; the calculator is hypothetical.
