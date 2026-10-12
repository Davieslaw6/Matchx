# MATCH X Progress

## Current state
- Working branch: `build/match-x-foundation`.
- Initial specification, verification log and architecture decision records are present.
- Initial backend settings, health endpoints and middleware, test starter, Next.js dashboard, same-origin rewrite, PostgreSQL 16 compose service and environment example are present.
- Added pure independent-Poisson scoreline grid and derived market probabilities, typed unsupported/insufficient-data results, and sports-data provider contract.
- Backend package dependencies now include async SQLite driver and prediction/test tooling.
- **UNVERIFIED:** no local runtime is attached to the GitHub connector. Dependency installation, tests, builds, migrations, live providers, and security scans have not been executed.

## Phase checklist
| Phase | Status | Notes |
|---|---|---|
| 0 Specification | Initial baseline | Full compliance review still required. |
| 1 Foundation | Files added; execution pending | Backend/frontend build and database startup need local execution. |
| 2 Data and access | Not started | ORM, Alembic, owner CLI, sessions, CSRF and rate limiting absent. |
| 3 Sports data | Contract added | Provider implementations, quota/cache/sync jobs and resolver absent. |
| 4 Prediction | M0 prototype added | No M1 fit, backtest or real model report yet. |
| 5 AI chat | Not started | No provider/tool orchestration. |
| 6 Analysis/odds | Not started | No persistence or analysis API. |
| 7 Tickets | Not started | No ticket service. |
| 8 Screenshot import | Not started | No secure upload pipeline. |
| 9 Booking codes | Not started | No integration state machine. |
| 10 History/settings | Not started | No evaluation/retention/export. |
| 11 Hardening | Not started | Audits and E2E not run. |
| 12 Documentation | In progress | Setup and deployment docs need completion. |
