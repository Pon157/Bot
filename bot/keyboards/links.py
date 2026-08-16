from aiogram.types import InlineKeyboardMarkup, WebAppInfo

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn


def resources_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [inline_btn("Наш канал", url=settings.channel_url, emo=e.GLOBE, style="primary")],
        [inline_btn("Бот с анкетами", url=settings.anketa_bot_url, emo=e.CHAT, style="primary")],
        [inline_btn("Техническая поддержка", url=settings.tech_bot_url, emo=e.CHAT, style="primary")],
        [
            inline_btn(
                "Отзывы",
                web_app=WebAppInfo(url=settings.reviews_webapp_url),
                emo=e.SPARKLES,
                style="primary",
            ),
            inline_btn(
                "Онлайн администрации",
                web_app=WebAppInfo(url=settings.online_webapp_url),
                emo=e.GREEN_DOT,
                style="primary",
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

