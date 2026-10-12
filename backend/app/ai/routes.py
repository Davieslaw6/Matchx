"""Owner-only AI chat endpoints. Conversation mutations require CSRF validation."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import LLMProviderError, OpenAIResponsesProvider
from app.auth import require_csrf, require_owner
from app.config import get_settings
from app.db import get_db
from app.models import ApiQuotaUsage, Conversation, Message, Session

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

CHAT_REQUESTS_PER_HOUR = 30

async def _consume_chat_quota(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    hour = now.replace(minute=0, second=0, microsecond=0)
    usage = await db.scalar(select(ApiQuotaUsage).where(
        ApiQuotaUsage.provider == "llm_chat", ApiQuotaUsage.period_start == hour
    ).with_for_update())
    if usage and usage.calls >= CHAT_REQUESTS_PER_HOUR:
        await db.rollback()
        raise HTTPException(status_code=429, detail={
            "code":"ai_rate_limit", "message":"AI request limit reached for this hour. Try again later."
        })
    if usage is None:
        db.add(ApiQuotaUsage(provider="llm_chat", period_start=hour, calls=1))
    else:
        usage.calls += 1
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        usage = await db.scalar(select(ApiQuotaUsage).where(
            ApiQuotaUsage.provider == "llm_chat", ApiQuotaUsage.period_start == hour
        ).with_for_update())
        if usage is None or usage.calls >= CHAT_REQUESTS_PER_HOUR:
            raise HTTPException(status_code=429, detail={
                "code":"ai_rate_limit", "message":"AI request limit reached for this hour. Try again later."
            })
        usage.calls += 1
        await db.commit()

class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=5000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)

@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=50),
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
    )).all()
    return {"items": [{"id": item.id, "title": item.title,
                       "created_at": item.created_at.isoformat(),
                       "updated_at": item.updated_at.isoformat()} for item in rows]}

@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail={"code":"conversation_not_found","message":"Conversation not found."})
    rows = (await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc()).limit(200)
    )).all()
    return {"id": conversation.id, "title": conversation.title,
            "messages": [{"id": message.id, "role": message.role, "content": message.content,
                          "created_at": message.created_at.isoformat(),
                          "metadata": message.metadata_json} for message in rows]}

@router.post("/chat")
async def chat(
    body: ChatBody,
    _: Session = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    try:
        provider = OpenAIResponsesProvider(settings)
    except LLMProviderError as exc:
        raise HTTPException(status_code=503, detail={
            "code":"llm_not_configured", "message":str(exc)
        }) from exc

    history: list[dict[str, str]] = []
    if body.conversation_id:
        existing_conversation = await db.get(Conversation, body.conversation_id)
        if existing_conversation is None:
            raise HTTPException(status_code=404, detail={
                "code":"conversation_not_found", "message":"Conversation not found."
            })
        old_messages = (await db.scalars(
            select(Message).where(Message.conversation_id == body.conversation_id)
            .order_by(Message.created_at.desc()).limit(19)
        )).all()
        history = [{"role": item.role, "content": item.content}
                   for item in reversed(old_messages) if item.role in {"user", "assistant"}]
        await db.rollback()
    history.append({"role": "user", "content": body.message})
    history = history[-20:]
    await _consume_chat_quota(db)
    try:
        result = await provider.answer(history, db)
    except LLMProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail={
            "code":"llm_provider_error", "message":str(exc)
        }) from exc

    now = datetime.now(timezone.utc)
    if body.conversation_id is None:
        title = " ".join(body.message.split())[:80] or "New conversation"
        conversation = Conversation(title=title)
        db.add(conversation)
        await db.flush()
    else:
        conversation = await db.get(Conversation, body.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail={
                "code":"conversation_not_found", "message":"Conversation not found."
            })
        conversation.updated_at = now
    user_message = Message(conversation_id=conversation.id, role="user", content=body.message,
                           metadata_json={})
    assistant_message = Message(
        conversation_id=conversation.id, role="assistant", content=result.text,
        metadata_json={"model": result.model, "tool_calls": result.tool_calls, "sources": result.sources},
    )
    db.add_all([user_message, assistant_message])
    await db.commit()
    return {
        "conversation_id": conversation.id,
        "answer": result.text,
        "model": result.model,
        "tool_calls": result.tool_calls,
        "sources": result.sources,
        "created_at": now.isoformat(),
    }
