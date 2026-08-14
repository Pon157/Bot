"""
Хелпер для мест, где нужно опционально прикрепить фото к сообщению.

Использование простое: если для данного места указана ссылка на фото
(settings.*_photo_url) или путь к файлу на сервере — отправляем фото с текстом 
как подпись, иначе просто текст.
"""

from __future__ import annotations

import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

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
    иначе — обычное текстовое сообщение. 

    Работает как с URL-ссылками, так и с локальными файлами на сервере.
    """
    if photo_url:
        try:
            # Если это путь к существующему файлу на сервере
            if os.path.exists(photo_url) and os.path.isfile(photo_url):
                photo = FSInputFile(photo_url)
            else:
                photo = photo_url

            return await bot.send_photo(
                chat_id,
                photo=photo,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except Exception as exc:  # Ловим любой сбой отправки фото
            logger.warning(
                "send_text_or_photo: не удалось загрузить фото %s (%s), отправляю текстом",
                photo_url,
                exc,
            )

    return await bot.send_message(
        chat_id,
        text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
