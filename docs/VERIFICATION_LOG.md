# MATCH X Verification Log

Only executed operations are listed. GitHub file-write success confirms that repository content was committed; it does not prove code execution or test success.

## 2026-10-12 — Repository implementation
- Re-read docs/SPEC.md at the start of phases 2, 3 and 4.
- GitHub branch reads/writes succeeded for source and documentation paths.
- Phase 2: SQLAlchemy models, async Alembic environment, frozen explicit initial schema revision, CLI owner provisioning/reset, Argon2id, hashed session tokens, CSRF double-submit validation, DB-backed login throttling, standard API errors, authenticated fixture API, login UI and dashboard session guard.
- Phase 3: football-data.org adapter with bounded retry handling and explicit unsupported capabilities; football-data.co.uk CSV parsing/import CLI; Unicode/RapidFuzz team resolver; provider fixture/result sync service with data_sync_runs; paginated authenticated fixture API and explorer UI.
- Phase 4: added Dixon-Coles maximum-likelihood fitting with sum-to-zero attack/defence strengths, rho correction, strict pre-cutoff training, score-grid normalization checks, and expanding-window time-decay selection. Added synthetic tests for probability invariants, insufficient data, cutoff leakage and time-decay selection. These tests are authored but NOT executed.
- Updated frontend dependency ranges to Next.js 16.4, React 19.3, TypeScript 7 and CI Node 24; ADR 0004 records official release references. Compatibility remains unverified.
- Added docs/TEST_REPORT.md and docs/MODEL_REPORT.md explicitly marked NOT RUN / NOT GENERATED.
- Opened draft PR #1 (not merged): https://github.com/Davieslaw6/Matchx/pull/1.
- Checked workflow runs via the available commit-associated query; it returned no runs. This is not proof that no workflow exists, only that no run was returned by that query. No CI result has been confirmed.
- Replaced the initial metadata-driven migration with explicit create/drop operations so the historical revision no longer changes with future model edits. Migration upgrade/downgrade/drift checks remain NOT RUN.
- NOT RUN: Python compile/import, dependency installation, Ruff, Bandit, pip-audit, Alembic upgrade/downgrade/check, PostgreSQL/SQLite integration execution, npm install, ESLint, TypeScript check, Vitest, production build, npm audit, live provider calls or model backtests.
- Known implementation gaps: quota/TTL cache and scheduled jobs are absent; cross-provider canonical fixture identity is conservative; real historical backtest/report results and analysis/odds/ticket/AI/screenshot/booking integrations remain incomplete.
- No tests are represented as passing.
