# ADR 0001 — Preserve the MATCH X Monorepo and Fixed Stack

- **Status:** Accepted
- **Date:** 2026-10-12

## Context
MATCH X is a private, single-owner football analysis assistant with strict security, sports-data provenance, reproducible prediction evaluation and auditable ticket edits. The build brief specifies a fixed monorepo architecture and asks that changes require an ADR.

## Decision
Use `frontend/` for Next.js App Router + strict TypeScript and `backend/` for Python 3.12 + FastAPI, Pydantic v2, SQLAlchemy 2, Alembic and PostgreSQL 16. Keep `docs/`, `scripts/`, `docker-compose.yml` and GitHub Actions CI in the repository. Use one APScheduler worker process with PostgreSQL advisory locks; do not add Redis or Celery. The browser communicates through the Next.js origin and its `/api/*` rewrite. Treat PostgreSQL as primary; SQLite is optional and documented.

## Consequences
- Frontend and backend require separate dependency/tooling and test pipelines.
- Generated API types should derive from backend OpenAPI.
- Provider/LLM credentials remain server-side.
- Local startup, CI and deployment documentation must align with this topology.
- Any architecture change requires a subsequent ADR and must preserve product/security constraints.
- No implementation or runtime behaviour is verified by this decision alone.
