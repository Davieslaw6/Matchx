import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base, OwnerAccount

@pytest.mark.asyncio
async def test_owner_login_session_and_csrf_logout(tmp_path):
    database_path = tmp_path / "auth-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(OwnerAccount(id=1, password_hash=PasswordHasher().hash("a-very-long-test-password")))
        await db.commit()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            anonymous = await client.get("/api/v1/auth/session")
            assert anonymous.status_code == 401
            bad_login = await client.post("/api/v1/auth/login", json={"password": "wrong"})
            assert bad_login.status_code == 401
            assert bad_login.json()["code"] == "invalid_credentials"

            login = await client.post("/api/v1/auth/login", json={"password": "a-very-long-test-password"})
            assert login.status_code == 200
            assert "matchx_session" in client.cookies
            assert "matchx_csrf" in client.cookies

            session = await client.get("/api/v1/auth/session")
            assert session.status_code == 200
            csrf = client.cookies.get("matchx_csrf")
            logout = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
            assert logout.status_code == 200
            assert logout.json()["authenticated"] is False
            assert (await client.get("/api/v1/auth/session")).status_code == 401
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
