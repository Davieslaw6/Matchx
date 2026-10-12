# MATCH X

Private, single-owner football analysis assistant. Runtime status and gaps are recorded in docs/PROGRESS.md. Do not treat unverified modules as production-ready.

## Current implementation
- FastAPI API with liveness/readiness endpoints, standardized error envelopes and security headers.
- Single-owner login/logout/session endpoints, Argon2id owner credentials, hashed sessions, CSRF validation and login throttling.
- SQLAlchemy 2 persistence models and Alembic migration environment.
- Authenticated paginated fixture explorer API and mobile-responsive explorer page.
- football-data.org v4 adapter for competitions, teams, fixtures/results and standings; unsupported capabilities are explicit.
- football-data.co.uk CSV parser/import CLI for historical results and validated historical 1X2 odds, with timestamp-precision metadata and idempotent snapshot upserts.
- Unicode-normalized team resolver with RapidFuzz candidate scoring.
- Independent Poisson scoreline grid, Dixon–Coles maximum-likelihood model, time-decay selection, chronological walk-forward backtests, calibration/market-baseline metrics and prediction generation CLI. Real-data fitting/backtest has not been executed.
- Fixture analysis UI/API for stored predictions, expected goals, scorelines, odds snapshots and source provenance.
- Grounded AI chat with an OpenAI Responses adapter, allowlisted read-only tools, bounded tool calls, numeric/date grounding checks, saved conversations and an hourly request limit.
- Ticket manager with draft create/add/remove/archive, signed preview-confirm flow, session binding, required idempotency keys, audit revisions and CSV export; no wager placement.
- Screenshot upload with PNG/JPEG/WEBP validation, immutable original storage, OCR candidate extraction, duplicate detection and manual review; OCR never writes odds or tickets.
- Prediction history with paginated stored forecasts, post-match 1X2 evaluation, Brier/log-loss/accuracy summaries, strict pre-kickoff cutoff guards and idempotent evaluation requests.
- PostgreSQL 18, backend and frontend Docker images; CI workflow includes lint, security/dependency checks, tests and container builds (runs have not yet been verified).

The prediction package includes a trained-model fitter and backtest runner, but no real-data training or backtest has been executed in this authoring environment. No prediction performance claims are made.

## Requirements
- Python 3.12+
- Node.js 24 LTS+
- Docker Compose

## Local development (SQLite)

1. Copy `backend/.env.example` to `backend/.env` and set `SESSION_SECRET` to a generated random value.
2. From `backend/`, create a Python 3.12+ virtual environment and run `python -m pip install -e ".[dev]"`.
3. From `backend/`, run `alembic upgrade head`.
4. From `backend/`, run `python -m app.owner_cli create-owner` and enter a strong password.
5. Start the API from `backend/`: `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
6. In another terminal, run `npm install` and `npm run dev` from `frontend/`.
7. Open `http://localhost:3000`.

The default local database is SQLite. The Docker deployment below uses PostgreSQL 18. Local screenshot OCR also requires the Tesseract executable; the backend container includes it.

## Local deployment with Docker

1. Copy `.env.example` to `.env`.
2. Generate two URL-safe secrets with `openssl rand -hex 32`; place one in `POSTGRES_PASSWORD` and one in `SESSION_SECRET`. Do not commit `.env`.
3. Build images and start only the database: `docker compose build && docker compose up -d postgres`.
4. Apply migrations and create the owner before starting the public-bound backend: `docker compose run --rm -it --no-deps backend sh -c "alembic upgrade head && python -m app.owner_cli create-owner"`.
5. Start the application: `docker compose up -d backend frontend`.
6. Open `http://localhost:3000`.

The backend is not published to the host; the frontend is bound to loopback only. The Docker deployment uses production cookie/security settings. Add an LLM key to `.env` and recreate the backend to enable AI chat. A live odds-provider integration is not configured.

## Import data
For historical CSV results, download a football-data.co.uk CSV in accordance with its current terms and run from backend/:

    python -m app.sports.csv_import path/to/results.csv --competition-code E0 --season 2025-2026

For the grounded AI chat, set LLM_API_KEY in backend/.env. LLM_MODEL selects the model and LLM_BASE_URL defaults to the OpenAI Responses API endpoint. If the key is missing, chat returns an explicit configuration error. Tools are allowlisted and read-only; ticket mutation and wager placement are not exposed to the model.

For a bounded football-data.org sync, set PROVIDER_API_KEY in backend/.env and run:

    python -m app.sports.sync_football_data --start 2026-10-01 --end 2026-10-14 --competition PL

After importing enough historical results, generate pre-kickoff predictions for an internal competition UUID (requires at least 65 completed pre-cutoff matches):

    python -m app.prediction.generate_predictions --competition-id YOUR_COMPETITION_UUID

Then run a chronological backtest for that competition:

    python -m app.prediction.backtest_cli --competition-id YOUR_COMPETITION_UUID --cutoff 2026-10-01

The backtest writes docs/MODEL_REPORT.md and docs/model_backtest_latest.json with the data hash, cutoffs, baselines, metrics and bootstrap intervals. It exits with an explicit insufficient-data error when a valid walk-forward run cannot be produced. Provider coverage, quota and licence terms must be checked against current official documentation. Live provider calls and the backtest have not been verified. The importer does not fabricate kickoff times for date-only CSV rows.

The default configuration uses SQLite for local development. Set DATABASE_URL=sqlite+aiosqlite:///./matchx-dev.db explicitly if desired. PostgreSQL is the primary/CI database. Use Alembic for schema changes; do not use metadata.create_all() as an application startup shortcut.

For a public-interface bind, set OWNER_EXISTS=true only after provisioning the owner; startup also checks the owner record in the database. Use HTTPS and a unique strong secret. New data routes must explicitly use require_owner; mutation routes must also use require_csrf. Do not expose this build publicly until the remaining security gates are complete.

## Verification
From backend/: pytest -q, ruff check app tests, and alembic check after migration setup.
From frontend/: npm run lint, npm run typecheck, npm run test, and npm run build.
These commands have not been executed in the authoring environment. Consult docs/VERIFICATION_LOG.md.

## Current limitations
The frontend login and fixture explorer are wired to the API. Provider sync is not yet scheduled and quota/TTL caching is absent. Raw football-data.org JSON is retained during sync. Cross-provider canonical fixture resolution is conservative. Real-data model fitting/backtest execution, live odds-provider ingestion, complete ticket optimization, screenshot-to-market linking, booking-code integration, deployment/restore automation and full security audits remain incomplete. Historical football-data.co.uk 1X2 odds can be imported, and draft tickets require preview, signed confirmation and an idempotency key.
