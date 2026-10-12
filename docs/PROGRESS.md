# MATCH X Progress

## Current state
- Working branch: build/match-x-foundation; main has not intentionally been modified.
- Phase 2 repository implementation: SQLAlchemy 2 models, async Alembic environment/initial revision, CLI-only owner create/reset with Argon2id, opaque hashed sessions, CSRF checks, login failure windows/temporary lockout, standard API error envelopes and login UI.
- Authenticated fixture explorer endpoint and responsive frontend explorer are wired; anonymous requests are expected to receive 401.
- football-data.org v4 adapter implemented for competitions, teams, date-range fixtures/results and standings. Unsupported odds/xG/injuries/cards/corners/H2H/news capabilities are explicit.
- football-data.co.uk CSV result parser and CLI import validate scores/results and preserve date-only records without inventing kickoff times.
- Provider sync service records data_sync_runs and upserts normalized fixtures/results by provider IDs.
- Team resolver uses Unicode NFKD/casefold normalization, aliases, RapidFuzz matching and explicit ambiguous/unmatched outcomes.
- Added mocked provider tests and SQLite-backed tests for auth, import idempotency and sync idempotency.
- Frontend dependency ranges updated to Next.js 16.4, React 19.3, TypeScript 7 and Node 24 CI based on current official release information.
- UNVERIFIED: repository writes are confirmed, but no local dependency installation, tests, builds, migrations, live provider calls or CI results have been executed.

## Phase checklist
| Phase | Status | Notes |
|---|---|---|
| 0 Specification | Baseline | Refine living spec as modules are completed. |
| 1 Foundation | Files added; execution pending | Runtime and CI verification still required. |
| 2 Data and access | Implemented in repository; verification pending | UI and backend login/session flow added; integration tests authored but unexecuted. |
| 3 Sports data | Partial implementation | football-data.org adapter, historical CSV import, team resolver, provider sync service, fixture API/UI added. Raw payload retention, cache/quota controls, cross-provider canonical identity and scheduled jobs remain. |
| 4 Prediction | M0 prototype added | No M1 fit, walk-forward backtest or real model report. |
| 5 AI chat | Not started | No provider/tool orchestration. |
| 6 Analysis/odds | Partial | Explorer available; analysis API, odds ingestion and freshness handling absent. |
| 7 Tickets | Models added | No ticket service, confirmation tokens, split/optimizer or exports. |
| 8 Screenshot import | Model only | No secure upload pipeline. |
| 9 Booking codes | Models only | No integration state machine or real integrations. |
| 10 History/settings | Models added | No evaluation/retention/export workflow. |
| 11 Hardening | Not started | Audits, E2E and route-protection review not executed. |
| 12 Documentation | In progress | Setup/provider docs updated; deployment/restore/test report incomplete. |

## Immediate next actions
1. Trigger CI and fix observed lint/type/test/build failures.
2. Complete sync raw-payload retention, quota/cache and canonical duplicate resolution.
3. Implement attack/defence strength estimation and Dixon–Coles fitting only against real historical data.
4. Build analysis, odds, ticket and AI services; preserve explicit unsupported/insufficient-data states.
