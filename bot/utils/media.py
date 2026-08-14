"""
Хелпер для мест, где нужно опционально прикрепить фото к сообщению.

Использование простое: если для данного места указана ссылка на фото
(settings.*_photo_url) — отправляем фото с текстом как подпись, иначе просто
текст. Ссылки могут быть добавлены/изменены в любой момент через .env, без
изменения кода — так пользователь сможет сам загрузить нужные фотографии
через хостинг картинок и просто прописать прямую ссылку на них.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def send_text_or_photo(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    photo_url: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) -> Message:
    """
    Отправляет фото с подписью text (если photo_url задан и валиден),
    иначе — обычное текстовое сообщение. Если Telegram не смог загрузить
    фото по ссылке (битая ссылка, 404 и т.п.), тихо откатываемся на
    текстовое сообщение, чтобы это не ломало сценарий для пользователя.
    """
    if photo_url:
        try:
            return await bot.send_photo(
                chat_id,
                photo=photo_url,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            logger.warning("send_text_or_photo: не удалось загрузить фото %s (%s), отправляю текстом", photo_url, exc)

    return await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
