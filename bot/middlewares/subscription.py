from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import InlineKeyboardMarkup, TelegramObject, Update

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn
from bot.utils.emoji import ce

# события, которые не должны блокироваться проверкой подписки (иначе не на что жать «Я подписался»)
CB_CHECK_SUBSCRIPTION = "check_subscription"


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot):
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        if not settings.required_channels:
            return await handler(event, data)

        # не блокируем саму кнопку проверки подписки
        if event.callback_query and event.callback_query.data == CB_CHECK_SUBSCRIPTION:
            return await handler(event, data)

        user_event = event.message or event.callback_query
        if user_event is None or user_event.from_user is None:
            return await handler(event, data)

        user_id = user_event.from_user.id
        not_subscribed = []
        for channel in settings.required_channels:
            try:
                member = await self.bot.get_chat_member(channel.chat_id, user_id)
                if member.status in ("left", "kicked"):
                    not_subscribed.append(channel)
            except Exception:
                # если бот не админ канала / канал недоступен — не блокируем пользователя из-за нашей ошибки
                continue

        if not_subscribed:
            rows = []
            for ch in not_subscribed:
                link = ch.invite_link or f"https://t.me/{ch.chat_id.lstrip('@')}"
                rows.append([inline_btn(ch.title, url=link, emo=e.GLOBE, style="primary")])
            rows.append(
                [inline_btn("Я подписался", callback_data=CB_CHECK_SUBSCRIPTION, emo=e.CHECK, style="success")]
            )
            markup = InlineKeyboardMarkup(inline_keyboard=rows)

            text = (
                f"{ce(e.WARNING)} Чтобы пользоваться ботом, подпишись на наши ресурсы:"
            )
            if event.message:
                await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
            elif event.callback_query:
                await event.callback_query.answer()
                await event.callback_query.message.answer(text, reply_markup=markup, parse_mode="HTML")
            return

        return await handler(event, data)
