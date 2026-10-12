# MATCH X

Private, single-owner football analysis assistant. The application is being developed in phases; current runtime status and gaps are recorded in [docs/PROGRESS.md](docs/PROGRESS.md). Do not treat unverified modules as production-ready.

## Current implementation
- FastAPI API with liveness/readiness endpoints and request/security headers.
- Responsive Next.js dashboard with same-origin `/api/*` rewrite.
- PostgreSQL 16 local Compose service.
- Initial pure Poisson scoreline-grid and derived market calculation package with invariant tests.
- Capability-aware sports-data provider interface.

The prediction package is a baseline calculation, not a trained or backtested production model. No prediction performance claims are made.

## Requirements
- Python 3.12+
- Node.js 22+
- Docker Compose (for PostgreSQL 16)

## Local setup
1. Copy `backend/.env.example` to `backend/.env` and set a strong random `SESSION_SECRET`. The example is development-only.
2. Start PostgreSQL after setting the required password: `POSTGRES_PASSWORD=choose-a-local-password docker compose up -d postgres`.
3. In a Python 3.12 virtual environment, run `python -m pip install -e ".[dev]"` from `backend/`.
4. Start API from `backend/`: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
5. In a second terminal, run `npm install` then `npm run dev` from `frontend/`.
6. Open http://localhost:3000. The dashboard checks API liveness through the same-origin rewrite.

For local SQLite mode, use `DATABASE_URL=sqlite+aiosqlite:///./matchx-dev.db`. Persistence/migrations are not implemented yet, so this is only a configuration placeholder at this phase.

## Tests
From `backend/`: `pytest -q` and `ruff check app tests`.
From `frontend/`: `npm run typecheck` and `npm run build`.
These commands have not been executed in the authoring environment. Consult [the verification log](docs/VERIFICATION_LOG.md) before relying on results.

## Configuration
See [backend/.env.example](backend/.env.example). Never commit `.env` or expose provider/LLM credentials in frontend variables.

## Security and deployment
Authentication, database migrations, provider adapters, LLM orchestration, ticket mutation confirmation, secure screenshot import and deployment hardening are not complete. Do not expose this early build to a public interface. The backend refuses a non-loopback bind unless `OWNER_EXISTS=true`, but owner provisioning/authentication is not yet implemented; this setting is not a substitute for actual authentication.

## Documentation
- [Specification](docs/SPEC.md)
- [Progress](docs/PROGRESS.md)
- [Verification log](docs/VERIFICATION_LOG.md)
- [Provider setup status](docs/api-setup.md)
- [ADR directory](docs/adr/)
