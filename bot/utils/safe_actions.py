"""
Обёртки над методами Bot API, которые часто падают с ожидаемыми и безопасными
для игнорирования ошибками — чтобы не City "message is not modified" не
всплывало исключением и не роняло хендлер.

Telegram возвращает ошибку "message is not modified", когда мы пытаемся
отредактировать сообщение на текст/клавиатуру, которые уже стоят в чате
(например, пользователь дважды подряд нажал одну и ту же кнопку, или два
апдейта пришли почти одновременно и оба хендлера решили отредактировать
сообщение одинаковым образом). Это не ошибка логики — просто нечего менять,
поэтому такие исключения нужно тихо проглатывать.
"""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

_IGNORABLE = ("message is not modified", "message to edit not found")


def _is_ignorable(exc: TelegramBadRequest) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _IGNORABLE)


async def safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
    **kwargs,
) -> Message | None:
    """message.edit_text(...), которое не падает на 'message is not modified'."""
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode, **kwargs)
    except TelegramBadRequest as exc:
        if _is_ignorable(exc):
            logger.debug("safe_edit_text: игнорируем ожидаемую ошибку: %s", exc)
            return None
        raise


async def safe_edit_reply_markup(
    message: Message,
    reply_markup: InlineKeyboardMarkup | None,
) -> Message | None:
    try:
        return await message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if _is_ignorable(exc):
            logger.debug("safe_edit_reply_markup: игнорируем ожидаемую ошибку: %s", exc)
            return None
        raise


async def safe_edit_message_text(
    bot,
    text: str,
    *,
    chat_id: int,
    message_id: int,
    parse_mode: str | None = "HTML",
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs,
):
    try:
        return await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs,
        )
    except TelegramBadRequest as exc:
        if _is_ignorable(exc):
            logger.debug("safe_edit_message_text: игнорируем ожидаемую ошибку: %s", exc)
            return None
        raise


async def safe_answer_callback(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    """callback.answer(...), которое не падает, если запрос уже устарел."""
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        logger.debug("safe_answer_callback: игнорируем ошибку: %s", exc)
