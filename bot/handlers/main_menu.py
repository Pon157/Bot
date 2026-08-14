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
from bot.utils.media import send_text_or_photo

router = Router(name="main_menu")


def _webapp_btn(text: str, base_url: str, emo) -> InlineKeyboardBuilder:
    """
    Открывает мини-аппу. initData передаётся браузером Telegram автоматически
    через window.Telegram.WebApp.initData — дополнительно кодировать в URL не нужно.
    """
    builder = InlineKeyboardBuilder()
    builder.row(inline_btn(text, web_app=WebAppInfo(url=base_url), emo=emo, style="primary"))
    return builder


@router.message(F.text == BTN_STATISTICS)
async def show_statistics(message: Message) -> None:
    url = settings.online_webapp_url.rstrip("/") + "/stats.html"
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.CHART)} Активность пользователей и администраторов — в мини-приложении:",
        photo_url=settings.stats_photo_url,
        reply_markup=_webapp_btn("Открыть статистику", url, e.CHART).as_markup(),
    )


@router.message(F.text == BTN_REVIEWS_PANEL)
async def show_reviews_panel(message: Message) -> None:
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.SPARKLES)} Панель отзывов об администраторах:",
        photo_url=settings.reviews_photo_url,
        reply_markup=_webapp_btn("Открыть отзывы", settings.reviews_webapp_url, e.SPARKLES).as_markup(),
    )


@router.message(F.text == BTN_ADMINS_ONLINE)
async def show_admins_online(message: Message) -> None:
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.GREEN_DOT)} Администраторы, которые сейчас на связи:",
        photo_url=settings.online_photo_url,
        reply_markup=_webapp_btn("Кто сейчас онлайн", settings.online_webapp_url, e.GREEN_DOT).as_markup(),
    )


@router.message(F.text == BTN_DIALOGS_HISTORY)
async def show_dialogs_history(message: Message) -> None:
    await send_text_or_photo(
        message.bot,
        message.chat.id,
        f"{ce(e.CHAT)} История твоих диалогов с администраторами:",
        photo_url=settings.dialogs_photo_url,
        reply_markup=_webapp_btn("Открыть историю", settings.dialogs_webapp_url, e.CHAT).as_markup(),
    )

