from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.models import Admin


class AdminContextMiddleware(BaseMiddleware):
    """
    Кладёт в data:
      - is_admin: bool
      - db_admin: Admin | None
    Должна регистрироваться ДО AntiSpamMiddleware, чтобы антиспам мог не троттлить админов.
    """

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_event = getattr(event, "message", None) or getattr(event, "callback_query", None)
        user_id = user_event.from_user.id if user_event and user_event.from_user else None

        db_admin = None
        if user_id is not None:
            async with self.sessionmaker() as session:
                result = await session.execute(
                    select(Admin).where(Admin.telegram_id == user_id, Admin.is_active.is_(True))
                )
                db_admin = result.scalar_one_or_none()

        data["is_admin"] = db_admin is not None
        data["db_admin"] = db_admin
        return await handler(event, data)

