from aiogram.types import InlineKeyboardMarkup

from bot.utils import emoji as e
from bot.utils.buttons import inline_btn

CB_ACCEPT_PREFIX = "appeal:accept:"  # + appeal_id


def accept_keyboard(appeal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[inline_btn("Принять обращение", callback_data=f"{CB_ACCEPT_PREFIX}{appeal_id}", emo=e.CHECK, style="success")]]
    )
