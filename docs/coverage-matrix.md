# Documentation coverage matrix

**Last reviewed:** 2026-10-11

| Feature | Doc page | Screenshot | Tests exist | Verified vs code | Status |
|---|---|---|---|---|---|
| Landing | user-guide/landing-and-navigation.md | raw+annotated+mobile | partial | Yes | Complete |
| Login/Signup UI | authentication/README.md | raw+annotated+mobile | Yes (accounts) | Yes | Complete (IdP config-dependent runtime) |
| Dashboard | features/dashboard.md | raw+annotated+mobile | Yes | Yes | Complete |
| Insights | features/insights.md | raw | partial | Yes | Complete |
| Transactions | features/transactions.md | raw+annotated+mobile | Yes | Yes | Complete |
| Statements | user-guide/transactions.md | raw | Yes | Yes | Complete |
| CSV import | features/csv-import.md | raw+annotated | Yes | Yes | Complete |
| Budgets | features/budgets.md | raw | Yes | Yes | Complete |
| Savings index/pools/goals | features/savings-goals.md | raw+mobile | Yes | Yes | Complete |
| Savings plan/debts | features/savings-plan.md | raw+annotated | Yes | Yes | Complete |
| Investing | features/investing.md | raw+annotated+mobile | Yes | Yes | Complete |
| Market data / historical | features/market-data.md | raw | Yes | Yes | Complete |
| Settings/theme | user-guide/settings.md | raw+annotated+dark+mobile | Yes | Yes | Complete |
| Onboarding/manual setup | features/manual-setup.md | raw | Yes | Yes | Complete |
| Messaging assistant | features/messaging-assistant.md | n/a (no page) | Yes | Yes | Complete (webhook; no UI shot) |
| API /api/me | api/README.md | n/a | Yes | Yes | Complete |
| Database/architecture | database/, architecture/ | diagrams | n/a | Yes | Complete |
| DOCX deliverable | deliverables/*.docx | embedded | n/a | Yes | Complete |
| PPT deliverable | deliverables/*.pptx | embedded | n/a | Yes | Complete |

### Screenshot checklist gaps (optional follow-up)

- Form validation error states (transaction add invalid)
- Import preview populated mid-wizard
- Auth0 Universal Login hosted page (third-party; not captured)
- Order approve confirmation flash messages
