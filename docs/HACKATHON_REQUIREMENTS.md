# Hacklanta 2026 — Requirements and Compliance Checklist

**Prepared:** 2026-10-11 · **Project:** Finovate · **Team:** Turn It Off and On Again

## ⚠️ Read this first: the official guide could not be read

The authoritative source is the Hacklanta 2026 Hacker Guide:
`https://aluminum-soprano-222.notion.site/Hacklanta-2026-Hacker-Guide-3b81ccc4ed5c80f4b717c0ccc4b5df54`

During preparation, the documentation environment's network policy **blocked** `notion.site`, `hacklanta.dev`, and `devpost.com` (HTTP 403 at the proxy / DNS failure). No copy of the guide exists in the repository. Therefore:

- **No requirement below is marked "Pass" on the basis of the guide.** Every guide-derived row is **Unverified** until someone with access fills in the exact wording.
- Rows are organized by the categories the team asked to be extracted. The *"What Finovate can show"* column is real evidence from the codebase; it is not a claim that the rule exists or is satisfied.
- **Action for the team (highest priority):** open the guide, paste each rule into the *Requirement* column, and update *Status*. Or export the Notion page (Markdown/PDF) into `docs/reference/` and ask for this file to be regenerated.

### Facts from public secondary sources (not the guide)

A web search returned the following about Hacklanta '26. Treat them as **unconfirmed** until checked against the guide:

| Fact | Secondary source | Confidence |
|---|---|---|
| Event runs **October 9–11, 2026** at Georgia State University, Atlanta | Search-result summary of an event listing | Medium |
| Four main tracks plus sponsor challenges | Same | Medium |
| A separate application at hacklanta.dev is required; Devpost registration alone does not make a participant eligible to submit or win | Same | Medium |
| Teams of up to **four** members | Same | Medium |

**If the October 9–11 dates are right, the submission deadline is today or has passed.** Confirm the exact deadline time immediately.

## Status legend

| Status | Meaning |
|---|---|
| **Pass** | Evidence shows the requirement is met *and* the requirement text was confirmed in the guide |
| **Likely pass** | Finovate has strong evidence for a requirement that is standard or stated by the team, but the guide wording is unconfirmed |
| **Partial** | Some evidence; gaps listed |
| **Fail** | Evidence shows it is not met |
| **Unverified** | Cannot be assessed without the guide or an external system |

## Requirements matrix

Columns: requirement · source · mandatory? · what Finovate must demonstrate · current status · evidence · remaining work · priority. "Owner" and "Deadline" are blank where the repository does not say.

### A. Eligibility and registration

| # | Requirement (category) | Source | Mandatory? | What Finovate must demonstrate | Status | Evidence | Remaining work | Priority |
|---|---|---|---|---|---|---|---|---|
| A1 | Team size limit | Guide — *not accessed*; secondary source says ≤ 4 | Unverified | Team roster within the limit | Unverified | Team name given by the team; member list not in repo | List members and confirm count | **P0** |
| A2 | Every member registered/accepted (hacklanta.dev application) | Secondary source | Likely mandatory | Each member accepted | Unverified | None in repo | Each member confirms acceptance | **P0** |
| A3 | Project created during the event / original work rules | Guide — not accessed | Unverified | Commit history within the hacking window | Likely pass (unverified) | All 49 commits are dated 2026-10-10 17:01 to 2026-10-11 (EDT), inside the reported event dates. The first commit ("Initial Push") already contains a large codebase, so its origin should be explained if asked | Read the rule. If pre-event work is allowed only with disclosure, disclose it | **P0** |
| A4 | Ownership / IP of submitted work | Guide — not accessed | Unverified | Team owns the code; third-party code is licensed | Unverified | Dependencies are open-source packages (see [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md)); the repo has **no LICENSE file** | Confirm the rule; add a license if required | P1 |

### B. Submission materials

| # | Requirement (category) | Source | Mandatory? | What Finovate must demonstrate | Status | Evidence | Remaining work | Priority |
|---|---|---|---|---|---|---|---|---|
| B1 | Submission platform and procedure (likely Devpost) | Secondary source mentions Devpost | Unverified | A completed submission entry | Unverified | — | Confirm the platform; submit before the deadline | **P0** |
| B2 | Project title + short and long description, character limits | Guide — not accessed | Unverified | Text within limits | Partial | Ready text in short/medium/extended forms with counts: [SUBMISSION.md](SUBMISSION.md) | Trim to the official limits once known | **P0** |
| B3 | Public code repository link | Guide — not accessed | Unverified | Accessible repo | Partial | GitHub remote `Simerr4life/Finovate` exists; visibility (public/private) not verified | Confirm the repo is accessible to judges; merge final work to the default branch | **P0** |
| B4 | Demo video (length, hosting) | Guide — not accessed | Unverified | Video within limit | **Fail (not yet made)** | Script ready: [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Record, upload, and add the link | **P0** |
| B5 | Live deployment / demo link | Guide — not accessed | Unverified | Working URL | Unverified | `vercel.json`; a Vercel project named `finovate` exists; deployments and domains could not be read (403) | Confirm a working URL and that judges can sign in | P0 |
| B6 | Track selection at submission (Finance + sponsor tracks) | Guide — not accessed | Unverified | Tracks chosen correctly | Unverified | Track rationale: [JUDGE_READINESS.md](JUDGE_READINESS.md) | Select tracks on the platform | **P0** |
| B7 | Screenshots / images | Guide — not accessed | Unverified | Real screenshots | Likely pass | 27 real captures: [SCREENSHOT_CATALOG.md](SCREENSHOT_CATALOG.md) | Upload the chosen images | P1 |

### C. Judging and presentation

| # | Requirement (category) | Source | Mandatory? | What Finovate must demonstrate | Status | Evidence | Remaining work | Priority |
|---|---|---|---|---|---|---|---|---|
| C1 | Judging criteria and weights | Guide — not accessed | — | Coverage of each criterion | Unverified | A criteria map against *common* hackathon criteria (labeled as such): [JUDGE_READINESS.md](JUDGE_READINESS.md) | Replace with the official criteria | **P0** |
| C2 | Live presentation / expo format and time limit | Guide — not accessed | Unverified | Demo fits the slot | Partial | 60 s / 3 min / 5 min scripts | Choose the script that matches the official slot | P0 |
| C3 | Judging schedule | Guide — not accessed | Unverified | Team present on time | Unverified | — | Record the time and location | P0 |

### D. Tracks

| # | Requirement (category) | Source | Mandatory? | What Finovate must demonstrate | Status | Evidence | Remaining work | Priority |
|---|---|---|---|---|---|---|---|---|
| D1 | **Finance track** expectations | Guide — not accessed | — | A finance product solving a real problem | Likely pass (substance) | Budgeting, imports, savings engine, goals, round-ups, simulated investing ([FEATURE_REFERENCE.md](FEATURE_REFERENCE.md)) | Map to the official track wording | P0 |
| D2 | **Auth0** sponsor criteria | Guide — not accessed | Unverified | Real Auth0 use | Partial | Full Universal Login flow, callback, verification, Management API refresh, Post-Registration Action webhook, API token validation (`/api/me/`) — covered by mocked tests; **no live-tenant login was executed during documentation** | Do one recorded live login against the tenant; confirm the tenant is configured in production | **P0** |
| D3 | **GoDaddy** sponsor criteria | Guide — not accessed | Unverified | Real GoDaddy product use | **Unverified / weak** | Only the domain string `finovate.biz` in `finovate/settings.py`. No GoDaddy API, DNS record, or registrar proof in the repo. DNS lookup of `finovate.biz` failed from this environment | Produce evidence (registrar account, DNS pointing to the deployment) or do not claim the track | **P0** |
| D4 | **Photon** sponsor criteria | Guide — not accessed | Unverified | Real Photon Spectrum use | Partial | Signed webhook verification (`assistant/spectrum.py`), bridge endpoint, `spectrum/` adapter using `spectrum-ts` iMessage provider; in-process chat verified; **live iMessage round-trip not executed** | Record one live iMessage exchange | **P0** |

### E. Rules on tools, data and safety

| # | Requirement (category) | Source | Mandatory? | What Finovate must demonstrate | Status | Evidence | Remaining work | Priority |
|---|---|---|---|---|---|---|---|---|
| E1 | AI-generated code policy | Guide — not accessed | Unverified | Compliance and any required disclosure | Unverified | The repo contains AI-assistant config (`.cursor/`, `spectrum/CLAUDE.md`, `AGENTS.md`) and AI-co-authored commits | Read the policy; disclose AI use if required (draft text in [SUBMISSION.md](SUBMISSION.md#responsible-ai-and-financial-safety)) | **P0** |
| E2 | Third-party APIs, libraries, assets | Guide — not accessed | Unverified | Allowed use, credited | Likely pass | [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md) lists every service and library | Confirm nothing is disallowed | P1 |
| E3 | Restrictions on financial apps, user data, simulated transactions | Guide — not accessed | Unverified | No real money movement; honest labeling; data protection | Likely pass (substance) | Investing simulated and labeled on every page; withdrawals refused; [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | Confirm against the rule text | P1 |
| E4 | Code of conduct | Guide — not accessed | Unverified | — | Unverified | — | Read it | P2 |

## Items that could make the project ineligible

1. **Missing submission before the deadline** (B1/B4): the video is not recorded yet, and the deadline may be today.
2. **Registration** (A2): any member not accepted through hacklanta.dev may make the team ineligible, according to the secondary source.
3. **Pre-existing work** (A3): if the rules require that the project be started at the event, the commit history must be checked.
4. **Sponsor claims without evidence** (D3 GoDaddy especially): claiming a sponsor track without real use can be disqualifying or simply wasted. Only claim what can be shown.
5. **Undisclosed AI use** (E1), if disclosure is required.

## Recommendations (ours, not hackathon rules)

- Use the 3-minute demo as the default; it shows budgeting → plan → goals → round-ups → simulated investing → chat.
- Show the Auth0 login live or on video. It is the strongest sponsor evidence besides Photon.
- Pre-record a fallback video in case Wi-Fi or a provider fails during judging.
