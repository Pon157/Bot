from aiogram.types import ReplyKeyboardMarkup, WebAppInfo

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.buttons import kb_btn

# Тексты кнопок — константы, чтобы фильтровать по ним в хендлерах без опечаток
BTN_PROFILE = "Профиль"
BTN_DIALOGS_HISTORY = "История диалогов"
BTN_EDIT_QUESTIONNAIRE = "Изменить анкету"
BTN_FAVORITE_ADMINS = "Любимые администраторы"
BTN_STATISTICS = "Статистика"
BTN_REVIEWS_PANEL = "Панель отзывов"
BTN_ADMINS_ONLINE = "Администрация онлайн"
BTN_CREATE_APPEAL = "Создать обращение"


def main_menu_keyboard(has_active_appeal: bool) -> ReplyKeyboardMarkup:
    rows = [
        [
            kb_btn(BTN_PROFILE, emo=e.EYES, style="primary"),
            kb_btn(BTN_DIALOGS_HISTORY, emo=e.CHAT, style="primary"),
        ],
        [
            kb_btn(BTN_EDIT_QUESTIONNAIRE, emo=e.PENCIL, style="primary"),
            kb_btn(BTN_FAVORITE_ADMINS, emo=e.STAR, style="primary"),
        ],
        [
            kb_btn(BTN_STATISTICS, emo=e.CHART, style="primary"),
            kb_btn(BTN_REVIEWS_PANEL, emo=e.SPARKLES, style="primary"),
        ],
        [
            kb_btn(BTN_ADMINS_ONLINE, emo=e.GREEN_DOT, style="primary"),
        ],
    ]
    if not has_active_appeal:
        rows.append([kb_btn(BTN_CREATE_APPEAL, emo=e.FIRE, style="success")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


WELCOME_TEXT = (
    "{fire} <b>Спокойный рассвет</b> {sparkles}\n\n"
    "Здесь тихо, тепло и всегда есть кому ответить.\n"
    "Это место, где можно выдохнуть, поговорить и получить поддержку —\n"
    "без спешки и без осуждения.\n\n"
    "{globe} Наш канал: {channel}\n"
    "{chat} Бот с анкетами: {anketa}\n\n"
    "Выбирай, с чего начнём {eyes}"
)


def welcome_text() -> str:
    from bot.utils.emoji import ce, FIRE, SPARKLES, GLOBE, CHAT, EYES

    return WELCOME_TEXT.format(
        fire=ce(FIRE),
        sparkles=ce(SPARKLES),
        globe=ce(GLOBE),
        chat=ce(CHAT),
        eyes=ce(EYES),
        channel=settings.channel_url,
        anketa=settings.anketa_bot_url,
    )

