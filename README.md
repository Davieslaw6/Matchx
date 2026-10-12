# MATCH X

Private, single-owner football analysis assistant. Runtime status and gaps are recorded in docs/PROGRESS.md. Do not treat unverified modules as production-ready.

## Current implementation
- FastAPI API with liveness/readiness endpoints, standardized error envelopes and security headers.
- Single-owner login/logout/session endpoints, Argon2id owner credentials, hashed sessions, CSRF validation and login throttling.
- SQLAlchemy 2 persistence models and Alembic migration environment.
- Authenticated paginated fixture explorer API and mobile-responsive explorer page.
- football-data.org v4 adapter for competitions, teams, fixtures/results and standings; unsupported capabilities are explicit.
- football-data.co.uk CSV parser/import CLI for historical results and a provider sync service with audit records.
- Unicode-normalized team resolver with RapidFuzz candidate scoring.
- Initial pure Poisson scoreline-grid and derived market calculation package with invariant tests.
- PostgreSQL 16 Compose service and CI workflow.

The prediction package is a baseline calculation, not a trained or backtested production model. No prediction performance claims are made.

## Requirements
- Python 3.12+
- Node.js 24 LTS+
- Docker Compose

## Local setup
1. Copy backend/.env.example to backend/.env; set a unique random SESSION_SECRET.
2. Start PostgreSQL after setting a local password: POSTGRES_PASSWORD=choose-a-local-password docker compose up -d postgres.
3. From backend/, create a Python 3.12 virtual environment and run python -m pip install -e ".[dev]".
4. From backend/, run alembic upgrade head to create the schema.
5. From backend/, run python -m app.owner_cli create-owner and enter a strong password. Rotate it later with python -m app.owner_cli reset-owner-password.
6. Start the API from backend/: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000.
7. In another terminal, run npm install then npm run dev from frontend/.
8. Open http://localhost:3000 and sign in with the owner password.

## Import data
For historical CSV results, download a football-data.co.uk CSV in accordance with its current terms and run from backend/:

    python -m app.sports.csv_import path/to/results.csv --competition-code E0 --season 2025-2026

For a bounded football-data.org sync, set PROVIDER_API_KEY in backend/.env and run:

    python -m app.sports.sync_football_data --start 2026-10-01 --end 2026-10-14 --competition PL

Provider coverage, quota and licence terms must be checked against current official documentation. Live provider calls have not been verified. The importer does not fabricate kickoff times for date-only CSV rows.

The default configuration uses SQLite for local development. Set DATABASE_URL=sqlite+aiosqlite:///./matchx-dev.db explicitly if desired. PostgreSQL is the primary/CI database. Use Alembic for schema changes; do not use metadata.create_all() as an application startup shortcut.

For a public-interface bind, set OWNER_EXISTS=true only after provisioning the owner; startup also checks the owner record in the database. Use HTTPS and a unique strong secret. New data routes must explicitly use require_owner; mutation routes must also use require_csrf. Do not expose this build publicly until the remaining security gates are complete.

## Verification
From backend/: pytest -q, ruff check app tests, and alembic check after migration setup.
From frontend/: npm run lint, npm run typecheck, npm run test, and npm run build.
These commands have not been executed in the authoring environment. Consult docs/VERIFICATION_LOG.md.

## Current limitations
The frontend login and fixture explorer are wired to the API. Provider sync is not yet scheduled and raw provider bytes are not yet retained. Cross-provider canonical fixture resolution is conservative. Dixon–Coles fitting/backtesting, AI orchestration, odds ingestion, ticket mutation confirmation, secure screenshot import, booking-code integration, deployment/restore automation and full security audits remain incomplete.
