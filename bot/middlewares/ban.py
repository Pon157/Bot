from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import User


class BanMiddleware(BaseMiddleware):
    """Блокирует любое взаимодействие для забаненных пользователей."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        user_event = event.message or event.callback_query
        if user_event is None or user_event.from_user is None:
            return await handler(event, data)

        telegram_id = user_event.from_user.id

        async with self.sessionmaker() as session:
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one_or_none()

        if user and user.is_banned:
            text = (
                f"{ce(e.NO_ENTRY)} Вы заблокированы в этом боте.\n"
                f"Причина: {user.ban_reason or 'не указана'}"
            )
            if event.message:
                await event.message.answer(text, parse_mode="HTML")
            elif event.callback_query:
                await event.callback_query.answer(
                    "Вы заблокированы в этом боте", show_alert=True
                )
            return  # обрываем цепочку

        data["db_user"] = user
        return await handler(event, data)
