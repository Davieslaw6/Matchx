from contextlib import asynccontextmanager
from uuid import uuid4
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from app.auth import router as auth_router
from app.config import get_settings
from app.db import engine, SessionLocal
from app.models import OwnerAccount

settings = get_settings()
settings.validate_public_bind()
log = structlog.get_logger()

@asynccontextmanager
async def lifespan(_: FastAPI):
    public_bind = settings.host not in {"127.0.0.1", "::1", "localhost"}
    if public_bind:
        async with SessionLocal() as db:
            owner = await db.scalar(select(OwnerAccount.id).limit(1))
            if owner is None:
                raise RuntimeError("Public startup refused: no owner account exists in the database.")
    yield
    await engine.dispose()

app = FastAPI(title="MATCH X API", version="0.2.0",
              description="Private, single-owner football analysis assistant API.",
              docs_url="/docs" if settings.environment != "production" else None, redoc_url=None,
              lifespan=lifespan)
app.include_router(auth_router)
app.add_middleware(CORSMiddleware, allow_origins=[settings.allowed_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"])

@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_request_error", request_id=request_id, path=request.url.path)
        response = JSONResponse(status_code=500, content={"code":"internal_error",
            "message":"An internal error occurred.", "details":None, "request_id":request_id})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response

@app.get("/api/v1/health/live", tags=["health"])
async def liveness():
    return {"status":"ok", "service":"match-x-api"}

@app.get("/api/v1/health/ready", tags=["health"])
async def readiness():
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status":"ready", "checks":{"database":"ok", "provider":"not_configured"}}
    except Exception:
        log.exception("readiness_database_check_failed")
        return JSONResponse(status_code=503, content={"status":"degraded",
            "checks":{"database":"unavailable", "provider":"not_configured"}})

@app.get("/api/v1/health", tags=["health"])
async def health():
    return {"status":"ok", "service":"match-x-api", "readiness":"check /api/v1/health/ready"}
