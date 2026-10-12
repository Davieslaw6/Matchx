"""Owner-only screenshot import and manual review endpoints."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import PurePath

import pytesseract
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth import require_csrf, require_owner
from app.db import get_db
from app.imports.screenshot_ocr import (
    MAX_IMAGE_BYTES, ImageValidationError, extract_candidates, extract_ocr_text, validate_image,
)
from app.models import ScreenshotImport, Session

router = APIRouter(prefix="/api/v1/imports/screenshots", tags=["screenshot-imports"])

class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern="^(accept|reject)$")
    notes: str | None = Field(default=None, max_length=2000)

def _filename(value: str | None) -> str:
    raw = (value or "screenshot").replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", raw).strip(" .")
    return (cleaned or "screenshot")[:160]

def _public(item: ScreenshotImport, *, include_text: bool = False) -> dict:
    value = {"id": item.id, "filename": item.filename, "mime_type": item.mime_type,
             "sha256_prefix": item.sha256[:12], "byte_size": len(item.image_data),
             "status": item.status, "parsed_data": item.parsed_data,
             "error_message": item.error_message,
             "created_at": item.created_at.isoformat(),
             "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
             "review_notes": item.review_notes}
    if include_text:
        value["ocr_text"] = item.ocr_text
    return value

@router.post("")
async def upload_screenshot(
    file: UploadFile = File(...),
    _: Session = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail={"code":"image_too_large","message":"Image exceeds the 5 MiB limit."})
    try:
        validate_image(data, file.content_type or "")
    except ImageValidationError as exc:
        raise HTTPException(status_code=415, detail={"code":"unsupported_image","message":str(exc)}) from exc
    digest = hashlib.sha256(data).hexdigest()
    existing = await db.scalar(select(ScreenshotImport).where(ScreenshotImport.sha256 == digest))
    if existing:
        return _public(existing, include_text=True)
    await db.rollback()

    status, error, text = "needs_review", None, ""
    try:
        text = (await run_in_threadpool(extract_ocr_text, data))[:20000]
    except pytesseract.TesseractNotFoundError:
        status, error = "ocr_unavailable", "OCR engine is not installed on this backend."
    except (RuntimeError, OSError):
        status, error = "ocr_failed", "OCR failed or exceeded its execution time limit."
    except Exception:
        status, error = "ocr_failed", "OCR failed. The original image was retained for manual review."

    parsed = extract_candidates(text)
    item = ScreenshotImport(filename=_filename(file.filename), mime_type=file.content_type or "",
        sha256=digest, image_data=data, status=status, ocr_text=text, parsed_data=parsed,
        error_message=error)
    db.add(item)
    try:
        await db.commit()
        await db.refresh(item)
    except IntegrityError:
        await db.rollback()
        duplicate = await db.scalar(select(ScreenshotImport).where(ScreenshotImport.sha256 == digest))
        if duplicate:
            return _public(duplicate, include_text=True)
        raise HTTPException(status_code=409, detail={"code":"image_import_conflict","message":"Image import conflicted with another request."})
    return _public(item, include_text=True)

@router.get("")
async def list_screenshot_imports(
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(select(ScreenshotImport).order_by(ScreenshotImport.created_at.desc()).limit(100))).all()
    return {"items": [_public(item) for item in rows]}

@router.get("/{import_id}")
async def get_screenshot_import(
    import_id: str,
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ScreenshotImport, import_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code":"import_not_found","message":"Screenshot import not found."})
    return _public(item, include_text=True)

@router.post("/{import_id}/review")
async def review_screenshot_import(
    import_id: str,
    body: ReviewBody,
    _: Session = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ScreenshotImport, import_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code":"import_not_found","message":"Screenshot import not found."})
    if item.status in {"reviewed", "rejected"}:
        raise HTTPException(status_code=409, detail={"code":"import_already_reviewed","message":"This screenshot has already been reviewed."})
    item.status = "reviewed" if body.decision == "accept" else "rejected"
    item.review_notes = body.notes
    item.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _public(item, include_text=True)
