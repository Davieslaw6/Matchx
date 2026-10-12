# MATCH X Progress

## Current state
- Working branch: build/match-x-foundation; main has not intentionally been modified.
- Specification, progress tracker, verification log and architecture decision records are present.
- FastAPI settings, security/request headers, liveness and database-readiness checks are present.
- SQLAlchemy 2 models cover required domain tables plus owner account, login attempts and booking-code selection status.
- Alembic async environment and initial schema revision added.
- CLI-only owner creation/password reset uses Argon2id; random session tokens are generated and only SHA-256 token hashes are stored.
- Authentication API supports login, session status, logout, HttpOnly session cookie, SameSite=Lax cookies, CSRF double-submit validation, database-backed per-IP failure windows and temporary lockout.
- Poisson baseline, derived market calculations, provider interface, frontend dashboard, Postgres Compose and CI configuration remain in place.
- UNVERIFIED: GitHub writes are confirmed, but local dependency installation, tests, builds, migrations and CI have not been executed.

## Phase checklist
| Phase | Status | Notes |
|---|---|---|
| 0 Specification | Initial baseline | Continue compliance review. |
| 1 Foundation | Files added; execution pending | CI exists; apps and database need runtime verification. |
| 2 Data and access | Implemented in repository; verification pending | ORM, Alembic, owner CLI, sessions, CSRF and login throttling added. Frontend login integration and adversarial tests remain. |
| 3 Sports data | Contract added | Provider implementations, quota/cache/sync jobs and resolver absent. |
| 4 Prediction | M0 prototype added | No M1 fit, backtest or real model report yet. |
| 5 AI chat | Not started | No provider/tool orchestration. |
| 6 Analysis/odds | Not started | No analysis API or populated sports data. |
| 7 Tickets | Models added | No ticket service, confirmation tokens, split/optimizer or exports. |
| 8 Screenshot import | Model only | No secure upload pipeline. |
| 9 Booking codes | Models only | No integration state machine or real integrations. |
| 10 History/settings | Models added | No evaluation/retention/export workflow. |
| 11 Hardening | Not started | Audits, route protection review and E2E not run. |
| 12 Documentation | In progress | Setup updated; deployment/restore/test report still incomplete. |

## Immediate next actions
1. Run CI and fix runtime/static-analysis failures.
2. Add auth integration tests and connect login UI.
3. Implement provider-backed ingestion, idempotent sync, team resolution and explorer endpoints.
4. Fit/evaluate Dixon–Coles only with real historical data and write a reproducible model report.
