# MATCH X

Private, single-owner football analysis assistant. Runtime status and gaps are recorded in docs/PROGRESS.md. Do not treat unverified modules as production-ready.

## Current implementation
- FastAPI API with liveness/readiness endpoints, security headers, and login/logout/session endpoints.
- SQLAlchemy 2 persistence models for domain entities, owner credentials, sessions and login throttling.
- Alembic migration environment and initial schema revision.
- CLI-only owner provisioning/reset with Argon2id password hashes.
- Responsive Next.js dashboard with same-origin API rewrite.
- PostgreSQL 16 local Compose service.
- Initial pure Poisson scoreline-grid and derived market calculation package with invariant tests.
- Capability-aware sports-data provider interface.

The prediction package is a baseline calculation, not a trained or backtested production model. No prediction performance claims are made.

## Requirements
- Python 3.12+
- Node.js 22+
- Docker Compose

## Local setup
1. Copy backend/.env.example to backend/.env and set a unique random SESSION_SECRET.
2. Start PostgreSQL after setting a local password: POSTGRES_PASSWORD=choose-a-local-password docker compose up -d postgres.
3. From backend/, create a Python 3.12 virtual environment and run python -m pip install -e ".[dev]".
4. From backend/, run alembic upgrade head to create the schema.
5. From backend/, run python -m app.owner_cli create-owner and enter a strong password when prompted. Rotate it later with python -m app.owner_cli reset-owner-password.
6. Start the API from backend/: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000.
7. In another terminal, run npm install then npm run dev from frontend/.
8. Open http://localhost:3000.

The default configuration uses SQLite for local development. Set DATABASE_URL=sqlite+aiosqlite:///./matchx-dev.db explicitly if desired. PostgreSQL is the primary/CI database. Use Alembic for schema changes; do not use metadata.create_all() as an application startup shortcut.

For a public-interface bind, set OWNER_EXISTS=true only after provisioning the owner; startup also checks the owner record in the database. Use HTTPS and a unique strong secret. Authentication helpers exist, but new data routes must explicitly use require_owner; mutation routes must also use require_csrf. Do not expose this build publicly until the remaining security gates and UI login flow are complete.

## Tests
From backend/: pytest -q, ruff check app tests, and alembic check after migration setup.
From frontend/: npm run typecheck and npm run build.
These commands have not been executed in the authoring environment. Consult docs/VERIFICATION_LOG.md before relying on results.

## Current limitations
Authentication endpoints are implemented but not integrated into the frontend login page. Sports provider adapters, live analysis API, trained/backtested Dixon–Coles model, LLM orchestration, ticket mutation confirmation, secure screenshot import and deployment hardening remain incomplete.
