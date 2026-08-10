from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import Admin, Appeal, AppealMessage, AppealStatus

router = APIRouter()


class AppealSummary(BaseModel):
    appeal_id: int
    admin_nickname: str
    status: str
    created_at: str
    closed_at: str | None


class MessageOut(BaseModel):
    direction: str
    content_type: str
    text_preview: str | None
    is_deleted: bool
    is_edited: bool
    created_at: str
    media_url: str | None  # заполняется через /api/dialogs/media/{message_pk}


@router.get("", response_model=list[AppealSummary])
async def list_dialogs(
    session: AsyncSession = Depends(get_session), tg_user: dict = Depends(get_current_telegram_user)
):
    result = await session.execute(
        select(Appeal).where(Appeal.user_id == tg_user["id"]).order_by(Appeal.created_at.desc())
    )
    appeals = result.scalars().all()
    out = []
    for a in appeals:
        nickname = "—"
        if a.primary_admin_id:
            admin_res = await session.execute(select(Admin).where(Admin.telegram_id == a.primary_admin_id))
            admin = admin_res.scalar_one_or_none()
            nickname = admin.nickname if admin else "—"
        out.append(
            AppealSummary(
                appeal_id=a.id,
                admin_nickname=nickname,
                status=a.status.value if isinstance(a.status, AppealStatus) else a.status,
                created_at=a.created_at.isoformat(),
                closed_at=a.closed_at.isoformat() if a.closed_at else None,
            )
        )
    return out


@router.get("/{appeal_id}/messages", response_model=list[MessageOut])
async def dialog_messages(
    appeal_id: int,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    appeal_res = await session.execute(select(Appeal).where(Appeal.id == appeal_id, Appeal.user_id == tg_user["id"]))
    appeal = appeal_res.scalar_one_or_none()
    if appeal is None:
        return []

    result = await session.execute(
        select(AppealMessage).where(AppealMessage.appeal_id == appeal_id).order_by(AppealMessage.created_at)
    )
    messages = result.scalars().all()
    return [
        MessageOut(
            direction=m.direction.value if hasattr(m.direction, "value") else m.direction,
            content_type=m.content_type,
            text_preview=m.text_preview,
            is_deleted=m.is_deleted,
            is_edited=m.is_edited,
            created_at=m.created_at.isoformat(),
            # media_url отдаётся отдельным подписанным эндпоинтом /media/{id}, чтобы не
            # тянуть тяжёлые файлы Telegram напрямую в список сообщений
            media_url=f"/api/dialogs/media/{m.id}" if m.content_type != "text" else None,
        )
        for m in messages
    ]


@router.get("/media/{message_pk}")
async def get_media(message_pk: int, session: AsyncSession = Depends(get_session)):
    """
    Проксирует реальный файл из Telegram по сохранённому file_id, чтобы в мини-аппе
    медиа отображалось нативно (img/video/audio), а не как ссылка-заглушка.
    """
    result = await session.execute(select(AppealMessage).where(AppealMessage.id == message_pk))
    msg = result.scalar_one_or_none()
    if msg is None or not msg.file_id:
        raise HTTPException(status_code=404, detail="Медиа не найдено")

    async with httpx.AsyncClient() as client:
        file_resp = await client.get(
            f"https://api.telegram.org/bot{settings.bot_token}/getFile",
            params={"file_id": msg.file_id},
        )
        file_resp.raise_for_status()
        file_path = file_resp.json()["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"

        async def stream():
            async with client.stream("GET", file_url) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk

        return StreamingResponse(stream(), media_type="application/octet-stream")
