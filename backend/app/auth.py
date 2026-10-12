"""Single-owner authentication: opaque hashed sessions, Argon2id, CSRF and DB-backed throttling."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import LoginAttempt, OwnerAccount, Session

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
COOKIE_NAME = "matchx_session"
CSRF_COOKIE_NAME = "matchx_csrf"
SESSION_TTL = timedelta(hours=12)
FAILURE_WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)
MAX_FAILURES = 5

class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=1024)

def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def _aware(value: datetime) -> datetime:
    # SQLite can return naive datetimes even when the column is timezone-aware.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def _ip_key(request: Request) -> str:
    # Do not trust X-Forwarded-For unless a trusted-proxy policy is configured.
    ip = request.client.host if request.client else "unknown"
    secret = get_settings().session_secret.get_secret_value().encode()
    return hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest()

async def require_owner(request: Request, db: AsyncSession = Depends(get_db)) -> Session:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 200:
        raise HTTPException(status_code=401, detail={"code":"authentication_required","message":"Sign in to continue."})
    session = await db.scalar(select(Session).where(Session.token_hash == _digest(token)))
    now = datetime.now(timezone.utc)
    if not session or _aware(session.expires_at) <= now:
        if session:
            await db.delete(session)
            await db.commit()
        raise HTTPException(status_code=401, detail={"code":"session_expired","message":"Session expired. Sign in again."})
    session.last_seen_at = now
    await db.commit()
    return session

def require_csrf(request: Request, session: Session = Depends(require_owner)) -> Session:
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    header = request.headers.get("X-CSRF-Token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail={"code":"csrf_failed","message":"CSRF validation failed."})
    if not hmac.compare_digest(_digest(cookie), session.csrf_hash):
        raise HTTPException(status_code=403, detail={"code":"csrf_failed","message":"CSRF validation failed."})
    return session

@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    key = _ip_key(request)
    attempt = await db.get(LoginAttempt, key)
    if attempt and attempt.locked_until and _aware(attempt.locked_until) > now:
        raise HTTPException(status_code=429, detail={"code":"login_rate_limited","message":"Too many failed attempts. Try again later."})
    owner = await db.scalar(select(OwnerAccount).limit(1))
    valid = False
    if owner:
        try:
            valid = _hasher.verify(owner.password_hash, body.password)
        except (InvalidHashError, VerifyMismatchError, VerificationError):
            valid = False
    if not valid:
        if not attempt or now - _aware(attempt.window_started_at) > FAILURE_WINDOW:
            attempt = LoginAttempt(key_hash=key, failures=0, window_started_at=now)
            db.add(attempt)
        attempt.failures += 1
        if attempt.failures >= MAX_FAILURES:
            attempt.locked_until = now + LOCKOUT
        await db.commit()
        raise HTTPException(status_code=401, detail={"code":"invalid_credentials","message":"Invalid credentials."})
    if attempt:
        await db.delete(attempt)
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    session = Session(token_hash=_digest(raw_token), csrf_hash=_digest(csrf_token),
                      expires_at=now + SESSION_TTL, last_seen_at=now)
    db.add(session)
    await db.commit()
    secure = get_settings().environment == "production"
    response.set_cookie(COOKIE_NAME, raw_token, max_age=int(SESSION_TTL.total_seconds()),
                        httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE_NAME, csrf_token, max_age=int(SESSION_TTL.total_seconds()),
                        httponly=False, secure=secure, samesite="lax", path="/")
    return {"authenticated": True, "expires_at": session.expires_at.isoformat()}

@router.get("/session")
async def session_status(session: Session = Depends(require_owner)):
    return {"authenticated": True, "expires_at": session.expires_at.isoformat()}

@router.post("/logout")
async def logout(response: Response, session: Session = Depends(require_csrf), db: AsyncSession = Depends(get_db)):
    await db.delete(session)
    await db.commit()
    secure = get_settings().environment == "production"
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", httponly=False, secure=secure, samesite="lax")
    return {"authenticated": False}
