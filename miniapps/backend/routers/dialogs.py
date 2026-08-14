from __future__ import annotations

import mimetypes

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.utils.permissions import is_head_or_owner
from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import Admin, Appeal, AppealMessage, AppealStatus

router = APIRouter()

_FALLBACK_MIME_BY_CONTENT_TYPE = {
    "photo": "image/jpeg",
    "video": "video/mp4",
    "video_note": "video/mp4",
    "animation": "video/mp4",
    "voice": "audio/ogg",
    "audio": "audio/mpeg",
    "sticker": "image/webp",
}


async def _resolve_target_user_id(
    session: AsyncSession, requester_id: int, view_as_user_id: int | None
) -> int:
    """
    Обычно пользователь смотрит только свои диалоги (view_as_user_id=None).
    Если передан view_as_user_id — это запрос от /seedialogs: разрешаем только
    владельцу и хед-админам, иначе 403 (даже если это просто левый параметр
    в URL, подставленный руками — раз уж мы всё равно это дублируем на бэкенде,
    а не только скрываем в интерфейсе).
    """
    if view_as_user_id is None:
        return requester_id

    if requester_id == settings.owner_id:
        return view_as_user_id

    admin_res = await session.execute(select(Admin).where(Admin.telegram_id == requester_id))
    requester_admin = admin_res.scalar_one_or_none()
    if requester_admin is not None and is_head_or_owner(requester_admin, requester_id):
        return view_as_user_id

    raise HTTPException(status_code=403, detail="Просмотр чужих диалогов доступен только владельцу и хед-админам")


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
    view_as_user_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    user_id = await _resolve_target_user_id(session, tg_user["id"], view_as_user_id)
    result = await session.execute(
        select(Appeal).where(Appeal.user_id == user_id).order_by(Appeal.created_at.desc())
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
    view_as_user_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    user_id = await _resolve_target_user_id(session, tg_user["id"], view_as_user_id)
    appeal_res = await session.execute(select(Appeal).where(Appeal.id == appeal_id, Appeal.user_id == user_id))
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

    Раньше всегда отдавался Content-Type: application/octet-stream — из-за этого
    <video>/<audio> вообще отказывались проигрывать файл (нужен корректный
    MIME), а <img> полагался на угадывание браузером по содержимому, что не
    всегда срабатывает. Теперь MIME определяется по расширению настоящего
    файла Telegram (file_path из getFile), это надёжнее.
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

        guessed_type, _ = mimetypes.guess_type(file_path)
        media_type = guessed_type or _FALLBACK_MIME_BY_CONTENT_TYPE.get(msg.content_type, "application/octet-stream")

        async def stream():
            async with client.stream("GET", file_url) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk

        return StreamingResponse(stream(), media_type=media_type)

