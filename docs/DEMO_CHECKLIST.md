# Pre-Demo Checklist

Run through this list 30 minutes before judging and again before recording the video. ☐ = to do.

## 1. Application and environment

- ☐ `git pull` the branch being demoed; `pip install -r requirements.txt`
- ☐ `python manage.py check` → "no issues"
- ☐ `python manage.py test` → 381 tests OK (≈ 2 min; run once on demo day)
- ☐ Deployed site, if used: production URL opens over HTTPS, `FINOVATE_DEBUG=false`, `FINOVATE_SECRET_KEY` set, `DATABASE_URL` set (otherwise data resets on cold start)
- ☐ No secrets visible: close `.env` files, terminals that echo keys, and the Vercel/Auth0 dashboards before sharing your screen

## 2. Authentication

- ☐ Auth0 variables set; `APP_BASE_URL` matches the origin in the browser
- ☐ Auth0 app settings: callback `<APP_BASE_URL>/callback`, logout `<APP_BASE_URL>/`, verification result URL `<APP_BASE_URL>/accounts/verify/result/`
- ☐ Demo account signed up **and email verified** in advance (avoid waiting on email live)
- ☐ Fallback ready: local walkthrough (USER_GUIDE option C) on the presenter laptop

## 3. Data

- ☐ `python manage.py seed_demo` and `seed_peachtree_demo` run on the demo database (or the signed-in demo account has comparable data)
- ☐ Round-ups **enabled and not paused** (Investments → Round-up settings) so the $4.35 → $0.65 step works
- ☐ A savings plan exists and is **Active** (Savings → Savings plan → Resume / Turn back on if needed)
- ☐ At least one custom goal (for example "Trip to Lisbon") for the contribution step
- ☐ A small CSV ready on the desktop for the import step (extended demo)
- ☐ Delete leftover practice transactions so the ledger looks clean

## 4. Providers (each optional; know your fallback)

| Provider | Check | Fallback if it fails |
|---|---|---|
| Auth0 | Live login works | Already signed in; describe the flow; show the screenshot |
| Photon Spectrum | `cd spectrum && bun start`; chat linked via Settings → Messaging; send `help` | `python manage.py chat_demo --username demo` in a large-font terminal |
| Twelve Data | Explore tab shows price cards | Skip Explore; say live prices need the provider key |
| Wi-Fi | Venue network works | Run locally; use a phone hotspot; play the recorded video |

## 5. Browser and layout

- ☐ Chrome or Edge, zoom 100–110%, bookmarks bar hidden, notifications off
- ☐ Tabs pre-opened: Dashboard, Transactions → Add, Investments, Savings plan, Financial Goals
- ☐ Dark mode toggle works (header moon/sun)
- ☐ Mobile view checked (DevTools 390 px) or screenshots 23–26 ready

## 6. Key paths (click through once)

- ☐ Dashboard loads; 1M chart range works
- ☐ Add transaction saves and appears in the list
- ☐ Investments ledger shows the new **Pending** round-up
- ☐ Savings plan shows scenario and split; Pause/Resume work
- ☐ Goal contribution saves; a withdrawal above the balance shows an error
- ☐ Propose → Approve works once; a second proposal of the same surplus is capped
- ☐ Chat: `I got paid $500` → `yes`; `withdraw $50` refused

## 7. Recording

- ☐ Screen recorder at 1080p; microphone tested; system sounds off
- ☐ Video length within the official limit (**confirm the limit in the Hacker Guide**)
- ☐ Say "sample data" and "simulated" on camera
- ☐ Upload to the required host; set visibility so judges can watch; copy the link into the submission

## 8. Backup assets

- ☐ `docs/assets/screenshots/submission/` copied to the laptop
- ☐ Recorded fallback video saved locally
- ☐ This repo's README open as a talking-points reference

## 9. Presenter transitions

Problem → dashboard → transaction → round-up → savings plan → goal → chat → close. One person drives, one narrates; agree on hand-off cues.

## 10. Final submission review

- ☐ Every **P0** row in [HACKATHON_REQUIREMENTS.md](HACKATHON_REQUIREMENTS.md) resolved or consciously accepted
- ☐ Repository link opens for someone signed out (if public access is required)
- ☐ Live demo link works in a private window
- ☐ Video link plays in a private window
- ☐ Tracks selected: Finance, plus only the sponsor tracks you can evidence
- ☐ Team members listed and registered
- ☐ Description text within the platform's character limits ([SUBMISSION.md](SUBMISSION.md))
