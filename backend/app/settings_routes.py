"""Read-only owner settings and operational capability status; never returns secrets."""
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_owner
from app.config import get_settings
from app.db import get_db
from app.models import DataSyncRun, OwnerAccount, Session

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

@router.get("")
async def read_settings(_: Session = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    await db.execute(text("SELECT 1"))
    owner_exists = await db.scalar(select(OwnerAccount.id).limit(1))
    runs = (await db.scalars(select(DataSyncRun).order_by(DataSyncRun.started_at.desc()).limit(10))).all()
    provider_key = settings.provider_api_key.get_secret_value().strip() if settings.provider_api_key else ""
    llm_key = settings.llm_api_key.get_secret_value().strip() if settings.llm_api_key else ""
    return {
        "environment": settings.environment,
        "database": "connected",
        "owner_account_exists": owner_exists is not None,
        "session_cookie_secure": settings.environment == "production",
        "secrets_returned": False,
        "providers": {
            "football_data_org_configured": bool(provider_key),
            "historical_csv_import": True,
            "live_odds_provider_configured": False,
            "booking_code_provider_configured": False,
        },
        "ai": {"configured": bool(llm_key), "model": settings.llm_model,
               "requests_per_hour": 30},
        "ocr": {"configured": shutil.which("tesseract") is not None,
                "supported_formats": ["image/png", "image/jpeg", "image/webp"],
                "max_image_bytes": 5 * 1024 * 1024, "max_pixels": 20_000_000},
        "recent_syncs": [{
            "job_name": run.job_name, "provider": run.provider, "status": run.status,
            "counts": run.counts, "error_summary": run.error_summary,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        } for run in runs],
    }
