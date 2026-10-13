import hmac
from fastapi import Depends, HTTPException, Request
from .config import Settings, get_settings

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def require_access(request: Request, cfg: Settings = Depends(get_settings)) -> None:
    """Token required if ACCESS_TOKEN set; otherwise only loopback clients are allowed."""
    if cfg.access_token:
        auth = request.headers.get("authorization", "")
        supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, cfg.access_token):
            raise HTTPException(401, "Invalid or missing access token")
        return
    host = request.client.host if request.client else ""
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip") or ""
    forwarded_remote = any(h.strip() and h.strip() not in LOCAL_HOSTS for h in fwd.split(","))
    if host not in LOCAL_HOSTS or forwarded_remote:
        raise HTTPException(403, "No ACCESS_TOKEN configured: remote access is disabled")
