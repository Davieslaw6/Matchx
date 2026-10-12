from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import (
    Base, Competition, Fixture, IdempotencyKey, MarketOdds, OwnerAccount,
    Team, Ticket, TicketRevision, TicketSelection,
)

@pytest.mark.asyncio
async def test_ticket_actions_require_preview_confirmation_and_are_idempotent(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tickets.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as db:
        home = Team(provider="test", provider_team_id="home", name="Home FC")
        away = Team(provider="test", provider_team_id="away", name="Away FC")
        competition = Competition(provider="test", provider_competition_id="league", name="Test League")
        db.add_all([home, away, competition])
        await db.flush()
        fixture = Fixture(provider="test", provider_fixture_id="fixture-1",
            competition_id=competition.id, home_team_id=home.id, away_team_id=away.id,
            match_date=date.today(), kickoff_at=now + timedelta(days=2), status="scheduled")
        db.add(fixture)
        await db.flush()
        odds = MarketOdds(fixture_id=fixture.id, provider="test", bookmaker="TestBook",
            market="1X2", outcome="home", decimal_odds=Decimal("2.10"),
            observed_at=now - timedelta(minutes=5))
        db.add_all([odds, OwnerAccount(id=1, password_hash=PasswordHasher().hash("a-very-long-test-password"))])
        await db.commit()
        fixture_id, odds_id = fixture.id, odds.id

    async def override_db():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            login = await client.post("/api/v1/auth/login", json={"password":"a-very-long-test-password"})
            assert login.status_code == 200
            csrf = client.cookies.get("matchx_csrf")
            headers = {"X-CSRF-Token": csrf}

            create_preview = await client.post("/api/v1/tickets/preview", headers=headers,
                json={"action":"create_ticket","payload":{"name":"Weekend draft","notes":None}})
            assert create_preview.status_code == 200
            token = create_preview.json()["confirmation_token"]
            confirmed = await client.post("/api/v1/tickets/confirm", headers=headers,
                json={"confirmation_token":token})
            assert confirmed.status_code == 200
            ticket_id = confirmed.json()["ticket_id"]
            replay = await client.post("/api/v1/tickets/confirm", headers=headers,
                json={"confirmation_token":token})
            assert replay.status_code == 200
            assert replay.json() == confirmed.json()

            add_preview = await client.post("/api/v1/tickets/preview", headers=headers,
                json={"action":"add_selection","payload":{"ticket_id":ticket_id,"fixture_id":fixture_id,"market_odds_id":odds_id}})
            assert add_preview.status_code == 200
            add_token = add_preview.json()["confirmation_token"]
            added = await client.post("/api/v1/tickets/confirm", headers=headers,
                json={"confirmation_token":add_token})
            assert added.status_code == 200
            repeated = await client.post("/api/v1/tickets/confirm", headers=headers,
                json={"confirmation_token":add_token})
            assert repeated.json() == added.json()

            detail = await client.get(f"/api/v1/tickets/{ticket_id}")
            assert detail.status_code == 200
            assert detail.json()["selection_count"] == 1
            assert detail.json()["combined_decimal_odds"] == "2.10000"

            selection_id = detail.json()["selections"][0]["id"]
            remove_preview = await client.post("/api/v1/tickets/preview", headers=headers,
                json={"action":"remove_selection","payload":{"ticket_id":ticket_id,"selection_id":selection_id}})
            assert remove_preview.status_code == 200
            removed = await client.post("/api/v1/tickets/confirm", headers=headers,
                json={"confirmation_token":remove_preview.json()["confirmation_token"]})
            assert removed.status_code == 200

            async with factory() as db:
                assert await db.scalar(select(func.count(Ticket.id))) == 1
                assert await db.scalar(select(func.count(TicketSelection.id))) == 0
                assert await db.scalar(select(func.count(TicketRevision.id))) == 3
                assert await db.scalar(select(func.count(IdempotencyKey.key))) == 3
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
