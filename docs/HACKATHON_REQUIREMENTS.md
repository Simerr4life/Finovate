# Hacklanta 2026 — Requirements and Compliance Checklist

**Source:** the official Hacklanta 2026 Hacker Guide (Notion export provided by the team on 2026-10-11). Rules excerpt: [reference/hacker-guide-excerpt.md](reference/hacker-guide-excerpt.md). Updated 2026-10-11 08:30 EDT.

## ⏰ Deadline

> **"Hacking ends at 9:00 AM on SUNDAY OCTOBER 11th. ALL MATERIALS MUST BE SUBMITTED BY THE END OF HACKING TIME. NO EXCEPTIONS!"** — Hacker Guide, *Submissions*

| Event (guide, *Summary*) | Time (EDT) |
|---|---|
| Hacking period | Fri Oct 9, 8:30 PM → **Sun Oct 11, 9:00 AM** |
| Judging Expo | Sun Oct 11, 9:30–11:30 AM, Student Center East State Ballroom |
| Closing Ceremony | Sun Oct 11, 12:45 PM, State Ballroom |

## Track selection

Guide: *"Teams may submit to only **ONE** main track and a **MAXIMUM of 3** side challenges."*

| Choice | Official name and prompt | Finovate fit | Status |
|---|---|---|---|
| **Main track** | **Fintech** — "rethink how money moves: payments, budgeting, investing, and the tools that make finances easier to manage." | Budgeting, savings planning, round-ups, simulated investing | ✅ Strong fit |
| Side challenge 1 | **MLH: Best Use of Auth0** | Universal Login, verification gate, Management API, Action webhook, API token validation | 🟠 Implemented and tested with mocks; show a live login in the demo |
| Side challenge 2 | **Photon: Agents in iMessage** — "Build an agent that lives in iMessage using Photon. Projects must integrate Spectrum, Photon's open source SDK." | `spectrum/` adapter built on `spectrum-ts` with the iMessage provider; confirmation-gated assistant | 🟠 Meets "integrate Spectrum"; live iMessage not verified here. The linked "Photon Guidelines" page was not in the export |
| Side challenge 3 | **MLH: Best Domain Name from GoDaddy Registry** | **finovate.biz** (`.biz` is a GoDaddy Registry TLD) serves the live app | ✅ Live per the team (DNS not reachable from the docs build environment) |
| Not eligible | Shock Tracker: Zero Data ("no accounts, tracking, profiles, or stored personal info") | Finovate requires accounts | ✗ Do not select |

## Requirements matrix

Status: **Pass** (evidence meets the rule) · **Partial** · **Fail** (not done yet) · **Team** (only the team can confirm).

### What to build (guide, *Requirements → What to Build*)

| # | Requirement (guide wording or summary) | Mandatory | Finovate evidence | Status | Remaining work | Priority |
|---|---|---|---|---|---|---|
| R1 | "An original, working project built during the official Hacklanta hacking period" | Yes | All 49 commits dated Oct 10 17:01 EDT – Oct 11 (inside Fri 8:30 PM – Sun 9:00 AM); 381 passing tests | Pass | Be ready to explain the large first commit ("Initial Push") | P0 |
| R2 | Fits a track or challenge | Yes | Fintech | Pass | — | — |
| R3 | Open-source libraries, APIs, frameworks, AI tools, starter templates allowed; **"Disclose anything that existed before Hacklanta."** | Yes | Disclosure section in [SUBMISSION.md](SUBMISSION.md#disclosure-built-before-hacklanta--not-ours) (Figma Make layout, libraries, APIs, dataset, AI assistants) | Pass (text ready) | Paste into Devpost | **P0** |
| R4 | "The main design, development, and integration must happen during the event." | Yes | Commit history | Team | Team confirms | P0 |
| R5 | Not a previously completed or reused project; must not misrepresent how it was built | Yes | Disclosure is honest; investing labeled simulated | Team | Team confirms | P0 |

### What to submit (guide, *Requirements → What to Submit* and *Submission Instructions*)

| # | Requirement | Mandatory | Evidence | Status | Remaining work | Priority |
|---|---|---|---|---|---|---|
| S1 | Submit through **Devpost** (hacklanta.devpost.com) by 9:00 AM | Yes | — | **Fail (not yet)** | Submit now | **P0** |
| S2 | Project title and description; **write-up outlining ideation and development process**, on the Devpost page | Yes | [SUBMISSION.md → Devpost write-up](SUBMISSION.md#devpost-write-up-paste-into-the-description-covers-ideation-and-development-process) | Pass (text ready) | Paste | **P0** |
| S3 | The problem and who it serves | Yes | Write-up *Inspiration*, *Who it's for* | Pass | — | — |
| S4 | Team roster (**max 4**) | Yes | Harold Aghedo (captain), Micheal White | Pass | Enter on Devpost | P0 |
| S5 | Main track and any side challenges | Yes | Table above | Pass | Select on Devpost | **P0** |
| S6 | **Public** GitHub repo with all the code and a useful README | Yes | https://github.com/Simerr4life/Finovate is public; README and fixes on `main` | Pass | — | — |
| S7 | Working demo link **or** clear run instructions | Yes (either) | https://finovate.biz plus README *Run it locally* | Pass | — | — |
| S8 | **2–3 minute** demo video, **public** (YouTube/Google Drive, etc.) | Yes | [DEMO_SCRIPT.md](DEMO_SCRIPT.md) (video version) | **Fail (not recorded)** | Record, upload as Public/Anyone-with-link, paste the URL | **P0** |
| S9 | Technologies, APIs, datasets, sponsor tools used | Yes | "Built with" + disclosure in SUBMISSION | Pass | Paste | P0 |
| S10 | Disclosure of anything made before Hacklanta | Yes | See R3 | Pass | Paste | P0 |
| S11 | Test credentials or special instructions for judges | If applicable | "Instructions for judges" in SUBMISSION | Pass | Add judge test-account details if you deploy with Auth0 | P1 |
| S12 | **All links must stay accessible throughout judging** | Yes | — | Team | Don't make the repo or video private; keep any deployment up through 11:30 AM | P0 |
| S13 | **Google Form** with Devpost link, project name, team members' details, track, challenge(s); "You MUST submit this form and upload your project on Devpost" | Yes | Form link in Discord | **Fail (not yet)** | One member submits after Devpost | **P0** |
| S14 | Only **one** member submits Devpost and the form | Yes | — | Team | Pick the submitter | P0 |

### Judging (guide, *Judging*)

| # | Item | Finovate preparation |
|---|---|---|
| J1 | Format: **3-minute pitch + 2-minute Q&A** at a table with 2 judges | 3-minute script and Q&A answers in [JUDGE_READINESS.md](JUDGE_READINESS.md) |
| J2 | Criteria (sample questions): track prompt fit · polish of prototype/demo · presentation effectiveness · clear, compelling use case | Mapped in [JUDGE_READINESS.md](JUDGE_READINESS.md) |
| J3 | Expo 9:30–11:30 AM; demoing earns 200 points | Have a laptop ready, signed in, with sample data |

### Conduct

| # | Item | Status |
|---|---|---|
| C1 | MLH Code of Conduct applies | Team |
| C2 | Discord is the required communication channel (Google Form link announced there) | Team |

## Items that could make the project ineligible

1. **Missing the 9:00 AM Devpost submission** (S1), or the **Google Form** (S13).
2. **Private repo or private video** (S6, S8, S12).
3. **No video** (S8).
4. **Missing disclosure** of pre-existing work (R3): the Figma Make layout, dataset, and AI tools.
5. **More than one main track or more than three challenges** (track rule).

## Sponsor-challenge evidence

Details: [THIRD_PARTY_SERVICES.md](THIRD_PARTY_SERVICES.md). For GoDaddy, the MLH challenge judges the domain name: `finovate.biz` (GoDaddy Registry operates `.biz`) serves the live app.
