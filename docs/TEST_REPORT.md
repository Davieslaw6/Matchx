# MATCH X Test Report

**Status: UNVERIFIED — no test commands have been executed in the available authoring environment.**

This report is a checklist, not a claim of successful verification. GitHub content-write operations are not test execution.

| Gate | Command / evidence | Status |
|---|---|---|
| Backend lint | ruff check app tests | NOT RUN |
| Backend security scan | bandit -r app | NOT RUN |
| Python dependency audit | pip-audit | NOT RUN |
| Empty-database migration | alembic upgrade head against PostgreSQL 16 | NOT RUN |
| Migration drift | alembic check | NOT RUN |
| Backend unit/integration tests | pytest -q --cov=app.prediction | NOT RUN |
| Frontend dependency audit | npm audit --audit-level=high | NOT RUN |
| Frontend lint | npm run lint | NOT RUN |
| Frontend type check | npm run typecheck | NOT RUN |
| Frontend tests | npm run test | NOT RUN |
| AI grounding/tool orchestration tests | pytest tests/test_ai_grounding.py tests/test_ai_provider.py | NOT RUN |
| Historical odds parser/import tests | pytest tests/test_football_data_odds.py tests/test_csv_odds_import.py | NOT RUN |
| Ticket preview/confirm/idempotency tests | pytest tests/test_ticket_routes.py | NOT RUN |
| Screenshot image validation/OCR parser tests | pytest tests/test_screenshot_ocr.py | NOT RUN |
| Production frontend build | npm run build | NOT RUN |
| Live provider calls | bounded football-data.org sync | NOT RUN |
| Model backtest/leakage evaluation | reproducible walk-forward run | NOT RUN |

## Required follow-up
Run the GitHub Actions checks on the draft pull request, record the actual run URLs and outputs here, fix all failures, and update each status only from observed results.
