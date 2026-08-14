"""
Обёртки над InlineKeyboardButton / KeyboardButton с поддержкой Bot API 9.4:
- icon_custom_emoji_id — премиум-эмодзи на кнопке (отображается ВМЕСТО иконки, не дублируется в тексте)
- style — цвет кнопки: "primary" (синий), "success" (зелёный), "danger" (красный)

ВАЖНО: aiogram 3.15.x может ещё не содержать эти поля в Pydantic-моделях кнопок.
Сабклассы с extra="allow" добавляют их прозрачно — при официальной поддержке
можно будет убрать сабклассы и передавать поля напрямую.
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
        # icon_custom_emoji_id рисует иконку на кнопке сам — fallback в текст НЕ добавляем
        extra["icon_custom_emoji_id"] = emo.custom_id
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
        # icon_custom_emoji_id рисует иконку на кнопке сам — текст кнопки остаётся чистым,
        # именно поэтому F.text == BTN_XXX (где BTN_XXX без эмодзи) корректно работает
        extra["icon_custom_emoji_id"] = emo.custom_id
    if style is not None:
        extra["style"] = style
    return StyledKeyboardButton(text=text, web_app=web_app, **extra)

