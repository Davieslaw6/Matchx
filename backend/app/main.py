from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()
settings.validate_public_bind()
log = structlog.get_logger()

app = FastAPI(
    title="MATCH X API",
    version="0.1.0",
    description="Private, single-owner football analysis assistant API.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_request_error", request_id=request_id, path=request.url.path)
        response = JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "An internal error occurred.",
                "details": None,
                "request_id": request_id,
            },
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    return response


@app.get("/api/v1/health/live", tags=["health"])
async def liveness():
    return {"status": "ok", "service": "match-x-api"}


@app.get("/api/v1/health/ready", tags=["health"])
async def readiness():
    # Database/provider probes are added with the persistence and provider phases.
    return {"status": "degraded", "checks": {"database": "not_configured", "provider": "not_configured"}}


@app.get("/api/v1/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "match-x-api", "readiness": "not_verified"}
