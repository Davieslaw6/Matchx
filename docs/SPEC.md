# MATCH X — Living Product and Engineering Specification

**Status:** Phase 0 specification baseline; implementation not yet verified.  
**Product:** Private, single-owner football analysis assistant for mobile and desktop browsers.

## 1. Product boundaries
- Initial competitions: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, UEFA Champions League, Europa League, Conference League, plus data-driven top-20 competition configuration.
- No subscriptions, billing, customer registration, multi-user administration, automated wager placement, bookmaker account automation, or bookmaker passwords.
- Persistent responsible-use notice: statistical estimates only, not advice or guarantees; comply with local law and bookmaker terms. Never describe selections as “safe”, “sure”, or “guaranteed”.
- Never fabricate sports data, probabilities, odds, results, API responses, or booking codes. Never promise profit.

## 2. Architecture (changes require an ADR)
- Monorepo: `frontend/`, `backend/`, `docs/`, `scripts/`, `docker-compose.yml`, `.github/workflows/ci.yml`.
- Frontend: Next.js App Router, React, strict TypeScript, Tailwind, shadcn/ui, Lucide, TanStack Query, Zod, generated OpenAPI client.
- Backend: Python 3.12, FastAPI, Pydantic v2, typed SQLAlchemy 2, Alembic, async httpx, structlog, pytest.
- Database: PostgreSQL 16 primary and CI database; optional documented SQLite mode with portable models.
- Data science: pandas, NumPy, SciPy, scikit-learn; XGBoost only if out-of-sample evaluation justifies it.
- Worker: separate APScheduler process; PostgreSQL advisory locks; CLI `python -m app.jobs run <job_name>`; no Redis/Celery.
- Browser talks only to Next.js origin; `/api/*` rewrites to FastAPI. Document Vercel frontend + separately hosted backend deployment.
- Secrets remain server-side in environment variables. Money/odds use Python Decimal and PostgreSQL NUMERIC. Persist timestamps in UTC; display in configured IANA timezone.

## 3. Owner authentication and security
- CLI-only owner provisioning: `create-owner`; no registration endpoint. CLI password reset: `reset-owner-password`.
- Argon2id password hashing; hashed random session tokens; HttpOnly, production Secure, SameSite=Lax cookies; double-submit CSRF on mutations; login rate limits and temporary lockout.
- Login required even on localhost by default. Refuse public-interface startup when no owner exists.
- Exact-origin CORS, CSP/security headers, ownership checks, parameterised queries, request IDs, structured secret-redacted logs, consistent error envelope `{code,message,details,request_id}`, no stack-trace leakage.
- Environment-based settings, complete `.env.example`, ignored `.env`, gitleaks in pre-commit/CI. Run ruff, mypy, bandit, pip-audit, npm audit. Include backup/restore scripts and restore-test documentation.
- Treat provider payloads, uploads, team news, OCR, and model output as untrusted data.

## 4. Persistence model
Required tables: `app_settings`, `conversations`, `messages`, `teams`, `competitions`, `fixtures`, `match_results`, `team_statistics`, `market_odds`, `predictions`, `prediction_evaluations`, `tickets`, `ticket_selections`, `uploaded_files`, `booking_code_jobs`, `data_sync_runs`, `model_registry`.
Additional tables: `sessions`, `team_aliases`, `idempotency_keys`, `provider_raw_payloads`, `api_quota_usage`, `ticket_revisions`.
- Alembic-only schema evolution; foreign keys, uniqueness, and query-path indexes; `alembic check` must report no drift.
- Fixtures unique by (provider, provider_fixture_id) plus canonical duplicate detection across providers using competition, season, teams and kickoff tolerance.
- Odds are append-only observations, never overwritten.
- Predictions are immutable, versioned, supersede prior runs, store feature snapshots, all market probabilities, data cutoff and timestamps. Live predictions must have cutoff and creation before kickoff.
- Ticket selection odds are snapshotted; every edit has a revision with before/after/actor/time. Provider data and owner edits stay separate.
- Retention configuration drives purge job. Export JSON/ZIP and deletion require confirmation.

## 5. Sports-data layer
- Define provider interface for competitions, teams, date-range fixtures, results, standings, statistics, H2H, odds, injuries/suspensions and news. Capability flags include odds, xG, injuries, cards, corners; unsupported features return typed Unsupported, never empty success.
- Reference adapters: football-data.org and football-data.co.uk CSV history/closing odds. Optional API-Football adapter only after coverage, quota and licence review. Document provider setup/licensing/rate limits; live-unverified behaviour must be labelled UNVERIFIED.
- Timeouts, bounded exponential retries with jitter, Retry-After handling, circuit breaker, daily quota budget, per-data-type TTL cache.
- Save raw JSON with content hash and fetch metadata before strict Pydantic normalization. Reject invalid records with reasons; never silently coerce.
- Team resolution: Unicode NFKD/casefold/suffix normalization; aliases first, then rapidfuzz above configured threshold; ambiguous/low-confidence matches return candidate lists.
- Every sync writes counts/status/error summary to `data_sync_runs`; sync is idempotent.

## 6. Explorer and match analysis
- Explorer filters: date range, competition, team search, scheduled/live/finished/postponed/abandoned/cancelled status, favourites, pagination, prediction availability.
- Analysis shows teams/competition, localized kickoff, configurable recent form, goals for/against, home/away splits, H2H, xG/news/injuries only when provided, odds with observed time and staleness, prediction version/cutoff, statistical explanation and missing-data warnings.
- Never show fabricated or misleading placeholder numbers.

## 7. Prediction engine
- Pure-function package and thin service layer.
- M0: independent league-average Poisson with attack/defence strengths and home advantage.
- M1: Dixon–Coles, team attack/defence, home advantage, low-score rho, cross-validated exponential time decay, identifiability constraint, SciPy maximum likelihood.
- Optional M2 regularized logistic/gradient boosting on pre-kickoff features; adopt only when out-of-sample log-loss improvement has bootstrap confidence interval excluding zero; calibrate on held-out data. Same rule applies to XGBoost.
- Score grid capped (e.g. 0–10 goals each side), renormalized and retained mass asserted >0.9999. Derive 1X2, double chance, totals 0.5–4.5, BTTS and top-N correct scores from same grid.
- Property tests: 1X2 sum, over/under complements, BTTS complements, double-chance sums, nonnegative grid.
- Enforce minimum recent matches; promoted teams shrink toward league prior and show low confidence; insufficient data returns structured reason, not fabricated probabilities.
- Corners/cards only with provider history and separate negative-binomial model; otherwise Unsupported.
- Walk-forward expanding-window evaluation with strictly pre-cutoff data; benchmark uniform, league base rate, M0, M1, de-vigged closing market. Metrics: log loss, Brier, RPS, reliability/ECE, sharpness, sample size and bootstrap CIs. Never accuracy alone.
- Leakage test mutates/deletes post-cutoff data and requires byte-identical predictions. Fixed seeds and deterministic test. Registry stores version, hyperparameters, window, data hash, metrics, git SHA and creation time.
- `docs/MODEL_REPORT.md` must be generated from a real run and honestly report results, including failures to beat baselines.

## 8. Odds
- Raw implied probability = 1/decimal odds; overround and de-vigged probabilities via proportional normalization by default, optional power/Shin.
- Compare model vs market; large disagreement includes caution for model error/missing information.
- Theoretical EV = model probability × decimal odds − 1 only with valid prediction and fresh price; label theoretical, not profit.
- Configurable staleness thresholds tighten near kickoff. Track closing-line comparison when available.

## 9. Ticket manager
- Create/add/remove/edit market/outcome/odds/bookmaker, sort, draft, duplicate, split, analyse and export CSV/JSON/text.
- Exact Decimal product; round only display to two decimals. Validate odds >1, fixture bettable, market exists, duplicates, contradictory same-fixture selections; warn on multiple selections from one match.
- All modifications are preview + confirmation token + confirmed apply, with ticket revision. Never silently mutate original.
- Deterministic split strategies: balanced count, combined-odds target, model-probability ordering. Property test multiset conservation unless explicit remove/duplicate.
- Optimizer enforces max combined odds/selections, min model probability, preferred competitions, allowed markets and max uncertainty; explain each removal and violated constraint. No “safe” language. Combined probability only with explicit independence caveat or omitted.
- Neutralize CSV injection for cells starting =, +, - or @. Mutations require Idempotency-Key persisted in table.

## 10. Screenshot import
- PNG/JPEG/WebP only; verify magic bytes, size (default max 8 MB), pixel dimensions/decompression bombs. Re-encode via Pillow to strip metadata; random filename outside public directory; content hash deduplication.
- Vision model via configured LLM provider; optional Tesseract fallback. Pydantic output validates teams, fixture, market, outcome, odds, visible booking reference and per-field confidence.
- Match via normal team resolver; return matched/uncertain/unmatched. Mandatory human review before ticket creation. OCR/image instructions are untrusted.
- Tests use Pillow synthetic images and mocked vision including prompt-injection text.

## 11. Booking-code integration
- BookmakerIntegration capability interface: resolve_code, search_market, check_availability, create_code. Register by bookmaker ID.
- Default ManualIntegration reports unsupported and offers manual entry/export.
- Job states: submitted, resolved, mapped, previewed, confirmed, created, failed; selection statuses: mapped, odds_changed, unavailable, unsupported.
- Report created only with real integration confirmation identifier; otherwise state exact reason. No scraping or credentials. Document authorised-access and terms requirements. Fake integration tests cover all paths, partial mapping and changed odds.

## 12. AI assistant
- LLMProvider abstraction for OpenAI-compatible, Anthropic or local endpoint; configure through environment; keys never reach frontend.
- Pydantic tool registry: resolve_team, search_fixtures, get_team_form, get_head_to_head, get_odds, get_prediction, run_prediction (reuse stored live prediction), list_tickets, propose_ticket_change (preview only), analyze_ticket, parse_screenshot.
- Model cannot apply changes directly, execute code, fetch arbitrary URLs or read arbitrary files. Only UI-triggered confirmation endpoint applies changes.
- Bounded tool loop, per-tool timeout, structured provider errors, grounding verifier for every number/date/probability. Regenerate once on mismatch, then use data-grounded template.
- Label/wrap provider text, OCR and news as data. Ask one concise clarification with candidates for ambiguous team/date.
- Persist conversations/messages, token-budget history and summarise old turns. Stream via SSE.
- At least 30 deterministic mock-LLM utterance tests with expected tool sequences in CI; live evaluation optional and excluded from CI.

## 13. API and UI
- `/api/v1` routes for chat, fixtures list/detail/analysis/predictions, team form, odds, tickets CRUD/split/analyse/image import, booking-codes/convert, prediction history and health; plus login/logout/session, settings, owner-only job trigger and sync status.
- Cursor/page pagination with max page size; request IDs, structured errors, OpenAPI examples, rate limits by route group. Health separates liveness from readiness (database/provider).
- Pages: AI Chat, Match Explorer, Match Analysis, Ticket Manager, Prediction History, Personal Settings, Login.
- Mobile-first bottom nav; dark default/light option with CSS variable tokens; WCAG AA, keyboard accessibility, focus management and ARIA chart labels.
- Shared probability bars, odds chips, freshness badges, missing-data alerts, confirmation/diff dialogs, empty/skeleton/error states. Charts for calibration, form, probabilities, model-market comparison.
- All data through generated typed backend client. Demo data only with DEMO_MODE, separately stored and visibly bannered. Kickoff formatted with Intl and configured timezone; odds format setting decimal/fractional/American.

## 14. Background jobs
Separate idempotent jobs: fixture_sync, odds_refresh, result_import, prediction_evaluation, model_training, retention_purge. Advisory lock prevents overlap; each records data_sync_runs, respects quotas and supports configurable schedule, CLI and owner-only API trigger. Upcoming predictions are generated before kickoff by job, never per chat request.

## 15. Quality gates and tests
- Backend pytest/pytest-asyncio, Hypothesis, respx, freezegun. Cover security, idempotency, locks, quotas, CSV injection, image bombs, DST and leakage.
- Migration from empty DB, downgrade and alembic drift check.
- Frontend Vitest/React Testing Library; Playwright critical flows: login, explorer, analysis, ticket create/edit/split/export, screenshot review/confirmation, mock chat.
- Measure coverage; >=90% line coverage for prediction and ticket packages.
- CI: lint, type checks, tests, migrations and audits. Save real results to `docs/TEST_REPORT.md`.
- Never claim a test passes unless it was executed.

## 16. Required living docs and ADRs
- `docs/SPEC.md`: this specification, refined as implementation proceeds.
- `docs/PROGRESS.md`: phase checklist/status, blockers and next action.
- `docs/VERIFICATION_LOG.md`: commands, actual outputs, failures and fixes. Do not label remote API reads as local test execution.
- `docs/adr/NNNN-title.md`: context, decision, consequences for significant technical decisions.
- Also: `docs/MODEL_REPORT.md`, `docs/TEST_REPORT.md`, `docs/api-setup.md`, `docs/architecture.md`, `docs/deployment.md`, `docs/troubleshooting.md`, README, backup/restore documentation.

## 17. Phased delivery and exit criteria
- P0 Specification: spec, ADRs, repo layout, requirement-to-phase checklist.
- P1 Foundation: repo tooling, Postgres compose, CI, settings/logging/health; both apps start.
- P2 Data/access: models, migrations, auth, sessions, CSRF/rate limits; migrations pass and anonymous protected access fails.
- P3 Sports data: adapters, CSV import, sync jobs, resolver, explorer API; mocked sync idempotent/deduplicating.
- P4 Prediction: M0/M1, backtest; invariants/leakage pass and real model report generated.
- P5 AI/chat: providers, tools, grounding, SSE; 30-utterance mock eval passes.
- P6 Analysis/odds: endpoints/UI; missing/stale states verified.
- P7 Tickets: editor, previews, revisions, split, optimizer, exports; Decimal/split properties pass.
- P8 Screenshot: safe upload, extraction, review; adversarial/malformed tests pass.
- P9 Booking codes: interface/manual fallback/fake tests; no unsupported success.
- P10 History/settings: evaluation, calibration, settings, export/delete/retention; unresolved and backtest records separated.
- P11 Hardening: security, E2E, EXPLAIN; gates green or explicitly documented.
- P12 Documentation: architecture, provider setup, deployment, troubleshooting, backups, README and test report.
- At each phase start re-read SPEC.md; at each phase end run tests, fix failures, log evidence and continue without asking approval unless blocked by missing credential/access.
- Definition of done: all specified modules implemented, CI locally green or failures documented, leakage/property tests pass, model report based on real backtest, no unsafe certainty wording or false conversion success.

## 18. Environment and deployment documentation checklist
Document every variable in `.env.example`, including database URL, environment/debug, bind host/port, allowed origin, secret/session/CSRF settings, owner/auth throttling, timezone, provider credentials and quotas, retry/cache limits, LLM provider/base URL/model/key/timeouts/token budget, upload limits/storage, job schedules, demo mode, odds staleness and retention. No secrets committed. Provide local, private self-hosted and Vercel frontend + separate backend/database instructions.

## 19. Final report contract
Final report must include feature summary, repository tree, database setup, all environment variables, provider/LLM setup, frontend/backend/worker commands, test command/result/failures table, deployment instructions, limitations, VERIFIED vs UNVERIFIED with reasons, integrations needing credentials and each incomplete feature's exact cause.
