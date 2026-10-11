# Finovate Documentation

**Version:** 1.0.0
**Last reviewed:** 2026-10-11
**Audience:** End users, developers, administrators, and contributors

Finovate is a personal-finance web application for tracking spending, planning budgets, working toward savings goals, reviewing a personalized savings plan, and previewing **simulated** round-up / ETF investing. Identity is provided by Auth0 and/or Supabase Auth when configured. This documentation describes **verified implementation behavior** from the source code in this repository.

## How to use this documentation

| Role | Start here |
|---|---|
| New end user | [Getting started](getting-started.md) → [User guide](user-guide/README.md) |
| Developer | [Overview](overview.md) → [Architecture](architecture/README.md) → [Development](development/README.md) |
| Admin / deployer | [Deployment](deployment/README.md) → [Security](security/README.md) → [Integrations](integrations/README.md) |
| QA | [Testing](testing/README.md) → [Coverage matrix](coverage-matrix.md) |

## Contents

1. [Product overview](overview.md)
2. [Getting started](getting-started.md)
3. [Feature inventory](feature-inventory.md)
4. [User guide](user-guide/README.md)
5. [Features](features/README.md)
6. [Workflows](workflows/README.md)
7. [Authentication](authentication/README.md)
8. [Account management](account-management/README.md)
9. [Interface](interface/README.md)
10. [API](api/README.md)
11. [Database](database/README.md)
12. [Architecture](architecture/README.md)
13. [Security](security/README.md)
14. [Integrations](integrations/README.md)
15. [Troubleshooting](troubleshooting.md)
16. [Development](development/README.md)
17. [Deployment](deployment/README.md)
18. [Testing](testing/README.md)
19. [Glossary](glossary.md)
20. [Coverage matrix](coverage-matrix.md)
21. [Audit report](audit-report.md)
22. [Changelog](CHANGELOG.md)

## Packaged deliverables

| Format | Path |
|---|---|
| Word document | [deliverables/Finovate-Complete-Documentation.docx](deliverables/Finovate-Complete-Documentation.docx) |
| PowerPoint | [deliverables/Finovate-Visual-Feature-Guide.pptx](deliverables/Finovate-Visual-Feature-Guide.pptx) |

## Screenshots

Real application screenshots (synthetic `demo` data) under `assets/screenshots/`:

- `raw/` — unmodified captures
- `annotated/` — numbered callouts
- `mobile/` — mobile viewport captures

## Honest boundaries

- Investing is **simulated**; no brokerage is connected.
- Bank connection is a **placeholder** (“coming soon”).
- Notification events are **recorded**, not delivered externally.
- Django does **not** send iMessage; Spectrum inbound webhooks are verified.
- Website login requires Auth0 and/or Supabase Auth; `seed_demo` is a fixture for commands and local verification, not a public password login when those providers are expected.
