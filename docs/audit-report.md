# Documentation audit report

**Date:** 2026-10-11
**Version:** 1.0.0

## Completed work

1. Full codebase route/model/feature inventory
2. `/docs` hierarchical documentation system
3. Per-feature specifications with UI, workflow, logic, implementation, errors, tests
4. Real screenshot capture (desktop, mobile, annotated) from local demo data
5. Architecture / ER / auth Mermaid diagrams
6. API, database, security, integrations, deployment, testing guides
7. Coverage matrix
8. Packaged **DOCX** and **PPTX** deliverables

## Features verified against source

Dashboard, transactions, statements, imports, budgets, savings goals/pools, savings plan engine, debts, investing (simulated), market data, insights, settings/themes, auth flows (code-level), assistant webhook, `/api/me/`, Vercel deployment hooks.

## Defects / discrepancies discovered (reported, not “fixed for docs”)

1. Root README still says “35 tests” and mentions Tailwind/Chart.js CDN stack; current UI is primarily `finovate.css` custom design and test count is much higher.
2. README identity wording has minor internal tension (Auth0-required vs local login mentions); implementation uses Auth0 and/or Supabase; `seed_demo` is not website login when IdPs are expected.
3. Bank/brokerage env keys unused (placeholders) — correctly labeled coming soon / simulated.
4. Notification delivery not implemented despite settings toggles.
5. Spectrum Bun sidecar is echo-only relative to Django assistant logic.
6. Review modal “save plan” is client-only hide/show (`finovate.js`), does not persist.
7. Transaction/ledger pagination absent.

## Known limitations of this documentation pass

- Screenshots used Django `force_login` session for the `demo` fixture because Auth0/Supabase were not configured in the capture environment.
- Auth0 hosted Universal Login UI not captured (external).
- Some mid-wizard import preview / validation-error screenshots listed as follow-up in coverage matrix.
- DOCX/PPT are comprehensive guides, not a live searchable web portal (Markdown tree is the navigable portal substitute without adding a heavy docs framework).

## Outstanding tasks

1. Capture validation-error and import-preview screenshots when convenient
2. Refresh root README stack/test-count wording in a separate non-docs PR if desired
3. Optional: MkDocs/Sphinx portal if product owners want search UI beyond Markdown + DOCX/PPT
