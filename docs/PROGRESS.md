# MATCH X Progress

## Current state
- Working branch: build/match-x-foundation; main has not intentionally been modified. Draft PR: https://github.com/Davieslaw6/Matchx/pull/1.
- Phase 2 repository implementation: SQLAlchemy 2 models, async Alembic environment and frozen explicit initial revision, CLI-only owner create/reset with Argon2id, opaque hashed sessions, CSRF checks, login throttling/lockout, standard API error envelopes, login UI and dashboard session guard.
- Authenticated paginated fixture explorer API and responsive frontend explorer are wired; anonymous access is expected to return 401.
- football-data.org v4 adapter, football-data.co.uk CSV result parser/import CLI, Unicode/RapidFuzz team resolver and provider sync service are implemented in the repository.
- Prediction code includes M0 Poisson calculations and an M1 Dixon-Coles fitter with sum-to-zero strength constraints, low-score rho correction, strict pre-cutoff training and expanding-window time-decay selection.
- Added unit/integration tests for auth/CSRF, schema contract, CSV parsing/import idempotency, provider payload validation/sync idempotency, team resolution and Dixon-Coles probability/cutoff invariants.
- Frontend dependency ranges updated to Next.js 16.4, React 19.3, TypeScript 7, Node 24 CI; ADR 0004 records rationale.
- Added TEST_REPORT.md and MODEL_REPORT.md with explicit NOT RUN / NOT GENERATED status.
- UNVERIFIED: no local test/build/migration execution, no confirmed CI run, no live provider request and no real historical model backtest. Do not treat the branch as production-ready.

## Phase checklist
| Phase | Status | Notes |
|---|---|---|
| 0 Specification | Baseline | Continue refining living spec. |
| 1 Foundation | Files added; execution pending | CI has been expanded but no run is confirmed. |
| 2 Data and access | Implemented in repository; verification pending | Login/session/CSRF code and UI exist; tests are unexecuted. |
| 3 Sports data | Partial implementation | Adapter, CSV importer, resolver, sync service and explorer API/UI exist. Raw provider bytes, quota/TTL cache, complete canonical cross-provider identity and scheduled jobs remain. |
| 4 Prediction | M0 + M1 code added; unverified | Dixon-Coles fitter and decay CV helper added; no real backtest, market baseline, leakage execution or report results. |
| 5 AI chat | Not started | No LLM/tool orchestration. |
| 6 Analysis/odds | Partial | Explorer available; detailed analysis, odds ingestion and freshness handling absent. |
| 7 Tickets | Models only | No ticket service, confirmation tokens, split/optimizer or exports. |
| 8 Screenshot import | Model only | No secure upload pipeline. |
| 9 Booking codes | Models only | No integration state machine or real integrations. |
| 10 History/settings | Models added | No evaluation/retention/export workflow. |
| 11 Hardening | Not started | Audits and E2E are configured but unexecuted. |
| 12 Documentation | In progress | Setup, provider, ADR, test and model status docs added; deployment/restore docs incomplete. |

## Immediate next actions
1. Obtain actual CI run results for draft PR #1 and fix all failures.
2. Execute Alembic upgrade/downgrade/check against PostgreSQL 16 to validate the frozen migration.
3. Persist raw provider payloads, add quota/TTL caching, improve cross-provider canonical fixture identity and schedule idempotent jobs.
4. Load historical results from the database, run the real walk-forward evaluation and generate a data-backed model report.
5. Continue analysis/odds, tickets, AI, screenshot, booking-code, settings and deployment phases.
