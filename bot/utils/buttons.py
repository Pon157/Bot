"""
Обёртки над InlineKeyboardButton / KeyboardButton с поддержкой Bot API 9.4:
- icon_custom_emoji_id — премиум-эмодзи на кнопке
- style — цвет кнопки: "primary" (синий), "success" (зелёный), "danger" (красный)

ВАЖНО: на момент написания этого кода актуальная стабильная версия aiogram
(3.15.x) может ещё не содержать полей `style`/`icon_custom_emoji_id` в своих
Pydantic-моделях кнопок. Чтобы не блокироваться на апстриме, ниже сделаны
тонкие сабклассы, которые добавляют эти поля сами (aiogram основан на pydantic
и лишние поля с `model_config = ConfigDict(extra="allow")` не ломают сериализацию).
Как только в aiogram завезут официальную поддержку — эти обёртки можно заменить
прямыми kwargs `style=...`, `icon_custom_emoji_id=...` и выкинуть этот файл.
"""

from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardButton, KeyboardButton
from pydantic import ConfigDict

from bot.utils.emoji import Emo

ButtonStyle = Literal["primary", "success", "danger"]


class StyledInlineButton(InlineKeyboardButton):
    model_config = ConfigDict(extra="allow")


class StyledKeyboardButton(KeyboardButton):
    model_config = ConfigDict(extra="allow")


def inline_btn(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app=None,
    emo: Emo | None = None,
    style: ButtonStyle | None = None,
) -> StyledInlineButton:
    extra = {}
    if emo is not None:
        extra["icon_custom_emoji_id"] = emo.custom_id
        text = f"{emo.fallback} {text}"
    if style is not None:
        extra["style"] = style
    return StyledInlineButton(
        text=text,
        callback_data=callback_data,
        url=url,
        web_app=web_app,
        **extra,
    )


def kb_btn(
    text: str,
    *,
    web_app=None,
    emo: Emo | None = None,
    style: ButtonStyle | None = None,
) -> StyledKeyboardButton:
    extra = {}
    if emo is not None:
        extra["icon_custom_emoji_id"] = emo.custom_id
        text = f"{emo.fallback} {text}"
    if style is not None:
        extra["style"] = style
    return StyledKeyboardButton(text=text, web_app=web_app, **extra)
