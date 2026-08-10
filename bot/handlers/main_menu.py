from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import settings
from bot.keyboards.main_menu import (
    BTN_ADMINS_ONLINE,
    BTN_DIALOGS_HISTORY,
    BTN_REVIEWS_PANEL,
    BTN_STATISTICS,
)
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn
from bot.utils.emoji import ce

router = Router(name="main_menu")


def _webapp_button(text: str, url: str, emo) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(inline_btn(text, web_app=WebAppInfo(url=url), emo=emo, style="primary"))
    return builder


@router.message(F.text == BTN_STATISTICS)
async def show_statistics(message: Message) -> None:
    builder = _webapp_button("Открыть статистику", settings.online_webapp_url + "/stats", e.CHART)
    await message.answer(
        f"{ce(e.CHART)} Активность пользователей и администраторов — в мини-приложении:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(F.text == BTN_REVIEWS_PANEL)
async def show_reviews_panel(message: Message) -> None:
    builder = _webapp_button("Открыть отзывы", settings.reviews_webapp_url, e.SPARKLES)
    await message.answer(
        f"{ce(e.SPARKLES)} Панель отзывов об администраторах:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(F.text == BTN_ADMINS_ONLINE)
async def show_admins_online(message: Message) -> None:
    builder = _webapp_button("Кто сейчас онлайн", settings.online_webapp_url, e.GREEN_DOT)
    await message.answer(
        f"{ce(e.GREEN_DOT)} Администраторы, которые сейчас на связи:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.message(F.text == BTN_DIALOGS_HISTORY)
async def show_dialogs_history(message: Message) -> None:
    builder = _webapp_button("Открыть историю", settings.dialogs_webapp_url, e.CHAT)
    await message.answer(
        f"{ce(e.CHAT)} История твоих диалогов с администраторами:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
