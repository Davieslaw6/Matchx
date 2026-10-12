"""Explicit provider capability status. No external booking-code provider is configured."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_owner
from app.db import get_db
from app.models import Session

router = APIRouter(prefix="/api/v1/booking-codes", tags=["booking-codes"])

@router.get("/capabilities")
async def booking_code_capabilities(
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    return {
        "status": "unavailable",
        "providers": [],
        "booking_code_generation_enabled": False,
        "automated_wager_placement": False,
        "reason": "No supported booking-code provider adapter and credentials are configured.",
        "policy": "MATCH X will not invent booking codes or claim a ticket was accepted by a bookmaker.",
    }
