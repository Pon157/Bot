from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn
from bot.utils.emoji import ce
from bot.utils.media import send_text_or_photo
from db.models import User

CB_ACCEPT_AGREEMENT = "accept_agreement"

AGREEMENT_TEXT = (
    "{shield} <b>Пользовательское соглашение</b>\n\n"
    "Прежде чем продолжить, ознакомься с правилами общения в боте:\n"
    "— общение с администраторами ведётся уважительно;\n"
    "— бот не является заменой профессиональной психологической помощи;\n"
    "— переписка может использоваться модераторами для разбора спорных ситуаций.\n\n"
    "Нажимая «Принимаю», ты подтверждаешь согласие с правилами."
)


class AgreementMiddleware(BaseMiddleware):
    """Требует принятия соглашения перед любым другим действием, кроме самой кнопки принятия."""

    def __init__(self, sessionmaker: async_sessionmaker):
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        if event.callback_query and event.callback_query.data == CB_ACCEPT_AGREEMENT:
            return await handler(event, data)

        user_event = event.message or event.callback_query
        if user_event is None or user_event.from_user is None:
            return await handler(event, data)

        # Соглашение актуально только для личных сообщений — сообщения в группе
        # поддержки (в т.ч. в топиках диалогов) не должны блокироваться этим
        # мидлварём, иначе ответ администратора пользователю может "потеряться".
        # ВАЖНО: у CallbackQuery нет своего .chat — чат нужно брать из
        # callback_query.message.chat (и он может отсутствовать).
        chat_type = event.message.chat.type if event.message else (
            event.callback_query.message.chat.type if event.callback_query.message else "private"
        )
        if chat_type != "private":
            return await handler(event, data)

        user: User | None = data.get("db_user")
        if user is None:
            async with self.sessionmaker() as session:
                result = await session.execute(
                    select(User).where(User.telegram_id == user_event.from_user.id)
                )
                user = result.scalar_one_or_none()

        # новый пользователь — создание учётки произойдёт в хендлере /start,
        # здесь просто не блокируем самый первый /start
        if user is None:
            return await handler(event, data)

        if user.agreement_accepted_at is None:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [inline_btn("Принимаю", callback_data=CB_ACCEPT_AGREEMENT, emo=e.CHECK, style="success")]
                ]
            )
            text = ce(e.SHIELD)  # плейсхолдер, реальный текст форматируем ниже
            text = AGREEMENT_TEXT.format(shield=ce(e.SHIELD))
            if event.message:
                await send_text_or_photo(
                    event.message.bot, event.message.chat.id, text,
                    photo_url=settings.agreement_photo_url, reply_markup=markup,
                )
            elif event.callback_query:
                await event.callback_query.answer()
                await send_text_or_photo(
                    event.callback_query.message.bot, event.callback_query.message.chat.id, text,
                    photo_url=settings.agreement_photo_url, reply_markup=markup,
                )
            return

        return await handler(event, data)

