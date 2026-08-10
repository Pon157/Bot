from aiogram.types import InlineKeyboardMarkup

from bot.utils import emoji as e
from bot.utils.buttons import inline_btn

CB_MODE_NICKNAME = "appeal:mode:nickname"
CB_MODE_FAVORITES = "appeal:mode:favorites"
CB_MODE_FASTEST = "appeal:mode:fastest"
CB_MODE_AI = "appeal:mode:ai"
CB_ADMIN_PREFIX = "appeal:admin:"  # + telegram_id
CB_CANCEL = "appeal:cancel"


def choose_mode_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [inline_btn("По псевдониму администратора", callback_data=CB_MODE_NICKNAME, emo=e.SEARCH, style="primary")],
        [inline_btn("Из любимых администраторов", callback_data=CB_MODE_FAVORITES, emo=e.STAR, style="primary")],
        [inline_btn("Кто быстрее ответит", callback_data=CB_MODE_FASTEST, emo=e.ZAP, style="primary")],
        [inline_btn("Подбор ИИ", callback_data=CB_MODE_AI, emo=e.SPARKLES, style="primary")],
        [inline_btn("Отменить", callback_data=CB_CANCEL, emo=e.CROSS, style="danger")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admins_list_keyboard(admins: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    """
    admins: список (telegram_id, nickname, is_online)
    Онлайн-админы подсвечиваются зелёным style, оффлайн — обычным primary.
    """
    rows = []
    for admin_id, nickname, is_online in admins:
        style = "success" if is_online else "primary"
        emo = e.GREEN_DOT if is_online else e.RED_DOT
        rows.append(
            [inline_btn(nickname, callback_data=f"{CB_ADMIN_PREFIX}{admin_id}", emo=emo, style=style)]
        )
    rows.append([inline_btn("Отменить", callback_data=CB_CANCEL, emo=e.CROSS, style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
