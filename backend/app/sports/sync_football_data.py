"""Run a bounded football-data.org fixture/result sync window."""
import argparse
import asyncio
from datetime import date

from app.config import get_settings
from app.db import SessionLocal
from app.sports.football_data_org import FootballDataOrgProvider
from app.sports.sync import sync_provider_window

async def run(start: date, end: date, competition: str | None) -> None:
    token = get_settings().provider_api_key
    if token is None or not token.get_secret_value().strip():
        raise SystemExit("Set PROVIDER_API_KEY in backend/.env before syncing.")
    async with FootballDataOrgProvider(token.get_secret_value()) as provider:
        async with SessionLocal() as db:
            result = await sync_provider_window(provider, start, end, db, competition)
    print(result)

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync football-data.org fixtures/results.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--competition", help="Provider competition code, e.g. PL.")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must not precede --start")
    asyncio.run(run(args.start, args.end, args.competition))

if __name__ == "__main__":
    main()
