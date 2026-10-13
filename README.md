# footy-prediq — private football prediction app

One user, two modules: a **statistical prediction engine** (Dixon–Coles-style Poisson, Python) and an **AI chat** that can only
explain what the engine returns. Every probability comes from the engine; the chat layer flags any percentage it cannot match to
tool output.

## Structure
```
backend/   FastAPI + SQLAlchemy + Alembic + engine
  app/engine/    dixon_coles.py (fit/predict) · markets.py (all markets from ONE scoreline matrix) · backtest.py · validation.py
  app/data/      provider.py (football-data.org + API-Football adapters) · registry.py (runtime selection) · ingest.py
  app/chat/      llm.py (Anthropic / OpenAI-compatible) · tools.py (8 narrow tools) · orchestrator.py (+ figure guard)
  app/           fixtures.py (name resolution) · service.py (train/predict/evaluate) · security.py · main.py
  migrations/    Alembic (initial schema)        tests/  pytest suite
frontend/  Next.js 14 + React + TypeScript + Tailwind (dark, mobile-first); proxies /api/* to the backend
```

## Install
Requires Python 3.11+ and Node 20+.
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit (see below)
alembic upgrade head          # creates the schema (SQLite by default; set DATABASE_URL for PostgreSQL)
uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev                   # http://localhost:3000   (BACKEND_URL defaults to http://127.0.0.1:8000)
```

## Environment variables (backend/.env)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `sqlite:///./footy.db` (default) or `postgresql+psycopg://…` (install a driver) |
| `FOOTBALL_DATA_API_KEY` | football-data.org key (free: 12 competitions, 10 calls/min, delayed scores) |
| `API_FOOTBALL_API_KEY` | API-Football (api-sports.io) key (free plan ≈100 requests/day) |
| `DATA_PROVIDER` | default provider; changeable at runtime from the header selector |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` | chat model (`anthropic` or `openai`-compatible) |
| `ACCESS_TOKEN` | bearer token for every `/api/*` route. **If empty, only loopback clients are accepted.** |
| `ENABLED_LEAGUES` | default `PL,PD,SA,BL1,FL1` (add codes + API-Football ids in `provider.py` to extend) |
| `HALF_LIFE_DAYS`, `STALE_AFTER_HOURS`, `HTTP_TIMEOUT_S`, `MAX_RETRIES`, `CACHE_TTL_S`, `MIN_SECONDS_BETWEEN_REQUESTS` | model/IO tuning |

## Using it
1. Pick the **data source** in the header (only providers with a key are selectable).
2. **Settings → Sync data → Train** (per league or all). Data, models and predictions are stored **per provider**; after switching, sync and train again.
3. Ask in the Chat tab ("Analyze Arsenal vs Chelsea", "Upcoming PL matches with high over 1.5 probability"). History tab shows stored predictions and, once results arrive, log loss.
4. **Settings → Backtest** runs a walk-forward evaluation (each block predicted from earlier matches only) against a frequency baseline.
Retraining is a separate operation; chat never refits the model.

## Tests
```bash
cd backend && python -m pytest -q          # engine, providers (mocked HTTP), API, chat/tools/LLM clients, backtest, migrations
cd frontend && npx tsc --noEmit && npx next build
```
Test data is synthetic and clearly labelled as such. Nothing in the app substitutes demo data for live data.

## Deployment (private)
- Simplest and safest: run both on your own machine/VPS bound to localhost and reach them through an SSH tunnel or a private network (e.g. Tailscale).
- If the frontend is reachable from anywhere other than localhost, **set `ACCESS_TOKEN`** (and enter it in Settings); put HTTPS in front (Caddy/nginx).
- Run the backend with `uvicorn app.main:app --host 127.0.0.1 --port 8000`; the frontend with `npm run build && npm start` and `BACKEND_URL` pointing at it.
- Schedule training/sync (cron calling `POST /api/sync` then `POST /api/train/{code}` with the bearer token); never per chat request.
- Back up the database; predictions and results are kept for later evaluation.

## Known limitations (read before trusting any number)
- Goals-only model: no xG, injuries, lineups or odds are used. Probability ≠ value ≠ confidence; nothing is "safe".
- **Accuracy is unmeasured on real data.** Run Backtest after syncing real history and judge by log loss/Brier/calibration vs the baseline. Free API plans may expose little history, which makes estimates noisy early in a season (the app warns on thin samples).
- API field mappings (esp. API-Football) were written from provider documentation and mocked responses; verify with a first live sync.
- Optional scikit-learn/XGBoost model is intentionally not built until the baseline is evaluated on real data.
