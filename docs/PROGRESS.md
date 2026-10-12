# MATCH X Progress

## Current state
- Working branch: build/match-x-foundation; main has not intentionally been modified. Draft PR: https://github.com/Davieslaw6/Matchx/pull/1.
- Phase 2 repository implementation: SQLAlchemy 2 models, async Alembic environment and frozen explicit initial revision, CLI-only owner create/reset with Argon2id, opaque hashed sessions, CSRF checks, login throttling/lockout, standard API error envelopes, login UI and dashboard session guard.
- Authenticated paginated fixture explorer API and responsive frontend explorer are wired; anonymous access is expected to return 401.
- football-data.org v4 adapter, football-data.co.uk CSV results and historical 1X2 odds parser/import CLI, Unicode/RapidFuzz team resolver and provider sync service are implemented in the repository.
- Prediction code includes M0 Poisson calculations, M1 Dixon-Coles fitting, expanding-window decay selection, walk-forward evaluation/reporting, and a CLI that registers models and stores pre-kickoff predictions with data cutoffs and feature snapshots.
- Added unit/integration tests for auth/CSRF, schema contract, CSV parsing/import idempotency, provider payload validation/sync idempotency, team resolution, Dixon-Coles probability/cutoff invariants, AI tool allowlisting, ticket preview/confirm idempotency, screenshot validation and evaluation cutoff guards. Tests remain unexecuted.
- Frontend dependency ranges updated to Next.js 16.4, React 19.3, TypeScript 7, Node 24 CI; PostgreSQL 18 Compose, multi-stage backend/frontend images and ADR 0004 are added.
- Added TEST_REPORT.md and MODEL_REPORT.md with explicit NOT RUN / NOT GENERATED status.
- UNVERIFIED: no local test/build/migration execution, no confirmed CI run, no live provider request and no real historical model backtest. Do not treat the branch as production-ready.

## Phase checklist
| Phase | Status | Notes |
|---|---|---|
| 0 Specification | Baseline | Continue refining living spec. |
| 1 Foundation | Files added; execution pending | CI has been expanded but no run is confirmed. |
| 2 Data and access | Implemented in repository; verification pending | Login/session/CSRF code and UI exist; tests are unexecuted. |
| 3 Sports data | Partial implementation | Adapter, CSV importer, resolver, sync service and explorer API/UI exist. Raw provider bytes, quota/TTL cache, complete canonical cross-provider identity and scheduled jobs remain. |
| 4 Prediction | M0 + M1 code added; unverified | Dixon-Coles fitter, decay CV helper, walk-forward metrics, paired baselines and DB-backed report CLI added; no real historical backtest has been run. |
| 5 AI chat | Partial implementation | OpenAI Responses provider, allowlisted read-only data tools, bounded tool loop, numeric grounding check/retry/fallback and conversation UI added; live API key absent and tests unexecuted. |
| 6 Analysis/odds | Partial implementation | Fixture analysis UI/API shows stored predictions and odds observation precision; football-data.co.uk historical 1X2 odds are imported idempotently. Live odds provider, full odds market coverage and live freshness workflow remain. |
| 7 Tickets | Partial implementation | Draft create/add/remove/archive, signed two-minute confirmation, session binding, CSRF, required Idempotency-Key, revision history and CSV export. No split/optimizer, multiple export formats or wager placement. |
| 8 Screenshot import | Partial implementation | Validated image upload, immutable originals, SHA-256 deduplication, Tesseract OCR, conservative candidate extraction and explicit review/reject workflow. No automatic odds/ticket writes; screenshot-to-market linking remains. |
| 9 Booking codes | Explicitly blocked | Authenticated capability endpoint/UI returns unavailable with no configured providers; no codes are fabricated. A supported provider adapter, credentials and terms/licensing review are required. |
| 10 History/settings | Partial implementation | Paginated prediction history UI/API, post-match evaluation, strict pre-kickoff cutoff guards, one evaluation per prediction, Brier/log-loss/accuracy metrics and idempotent evaluation trigger. Settings/retention controls remain. |
| 11 Hardening | Partial implementation; unverified | Owner-only access, CSRF, Argon2id, login lockout, CSP/security headers, API rate limits, upload validation, idempotency and formula-safe CSV export are present. Automated security/E2E audits remain unexecuted. |
| 12 Documentation | In progress | Setup, provider, ADR, test and model status docs added; deployment/restore docs incomplete. |

## Immediate next actions
1. Obtain actual CI run results for draft PR #1 and fix all failures.
2. Execute Alembic upgrade/downgrade/check against PostgreSQL 18 to validate the frozen migration.
3. Persist raw provider payloads, add quota/TTL caching, improve cross-provider canonical fixture identity and schedule idempotent jobs.
4. Import sufficient historical results, run the walk-forward CLI and review a data-backed model report.
5. Review CI and migrations, then finish live odds/booking-provider integrations (requires supported provider credentials and terms review), screenshot-to-market linking, settings/retention and deployment/restore checks.
