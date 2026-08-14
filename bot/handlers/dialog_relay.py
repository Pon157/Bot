from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, MessageReactionUpdated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.main_menu import (
    BTN_ADMINS_ONLINE,
    BTN_CREATE_APPEAL,
    BTN_DIALOGS_HISTORY,
    BTN_EDIT_QUESTIONNAIRE,
    BTN_FAVORITE_ADMINS,
    BTN_PROFILE,
    BTN_REVIEWS_PANEL,
    BTN_STATISTICS,
)
from bot.services.appeals import close_appeal
from bot.services.relay import (
    find_mirror,
    get_active_appeal_by_topic,
    get_active_appeal_by_user,
    get_pending_appeal_by_user,
    relay_topic_to_user,
    relay_user_to_topic,
)
from bot.services import games as games_service
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AppealMessage, AppealParticipant

router = Router(name="dialog_relay")
logger = logging.getLogger(__name__)

# Тексты кнопок главного меню — этот хендлер ловит ЛЮБОЕ приватное сообщение,
# поэтому нажатия на кнопки меню нужно явно пропускать, а не полагаться только
# на порядок регистрации роутеров (см. bot/handlers/__init__.py).
_MAIN_MENU_BUTTON_TEXTS = {
    BTN_PROFILE,
    BTN_DIALOGS_HISTORY,
    BTN_EDIT_QUESTIONNAIRE,
    BTN_FAVORITE_ADMINS,
    BTN_STATISTICS,
    BTN_REVIEWS_PANEL,
    BTN_ADMINS_ONLINE,
    BTN_CREATE_APPEAL,
}


# ─────────── пользователь закрывает своё обращение ───────────

@router.message(Command("close"), F.chat.type == "private")
async def user_close_appeal(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return  # у админов своя команда /close — в топике
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        await message.reply(f"{ce(e.INFO)} У тебя нет активного диалога, который можно было бы закрыть.")
        return
    await close_appeal(session, message.bot, appeal, message.from_user.id, reason="закрыто пользователем")


# ─────────── личка пользователя → топик ───────────

@router.message(F.chat.type == "private")
async def user_message_to_topic(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    # Команды обрабатываются выше по цепочке роутеров (onboarding/appeal_create/etc.)
    # Сюда долетают только сообщения без активного FSM-состояния.
    if db_admin is not None:
        logger.debug("dialog_relay: skip — %s is an admin, not relaying own private message", message.from_user.id)
        return  # сообщения самих админов в личке — не диалог с пользователем

    # Фильтруем команды вручную (нельзя использовать ~Command() в хендлере без фильтра Command())
    if message.text and message.text.startswith("/"):
        return

    # Не перехватываем нажатия на кнопки главного меню — они обрабатываются
    # в main_menu.py / profile.py / appeal_create.py.
    if message.text in _MAIN_MENU_BUTTON_TEXTS:
        return

    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        pending = await get_pending_appeal_by_user(session, message.from_user.id)
        if pending is not None:
            # Раньше сюда попадали сообщения, отправленные ДО того, как кто-то
            # принял обращение (пока оно ещё "висит" в общем топике без своего
            # треда) — и они молча терялись: get_active_appeal_by_user ищет
            # только ACTIVE, а отдельного топика для PENDING ещё не существует.
            # Теперь дублируем такие сообщения в общий топик, чтобы админы их
            # видели, и явно предупреждаем пользователя, что диалог ещё не начат.
            await relay_user_to_topic(
                session, message.bot, message, pending, thread_id=settings.support_topic_id
            )
            await message.reply(
                f"{ce(e.INFO)} Обращение №{pending.id} пока не принято ни одним администратором — "
                "сообщение продублировано в общий топик, но диалог ещё не начался. "
                "Как только кто-то примет обращение, дальнейшая переписка будет идти напрямую."
            )
        else:
            # Ни ACTIVE, ни PENDING обращения нет вообще — сообщение действительно
            # некуда пересылать. Логируем, чтобы это было видно в логах, а не
            # выглядело как "сообщение просто пропало без следа".
            logger.info(
                "dialog_relay: у пользователя %s нет ни активного, ни ожидающего обращения — "
                "сообщение не переслано (chat_id=%s, message_id=%s)",
                message.from_user.id, message.chat.id, message.message_id,
            )
        return

    if message.text and await games_service.try_handle_guess(message.bot, session, appeal, message.from_user.id, message.text):
        return  # это был ход в игре (виселица/угадай число), а не обычное сообщение

    await relay_user_to_topic(session, message.bot, message, appeal)


# ─────────── топик → личка пользователя ───────────

@router.message(F.chat.type.in_({"group", "supergroup"}), F.message_thread_id.is_not(None))
async def admin_message_to_user(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if message.chat.id != settings.support_group_id:
        return
    if db_admin is None:
        logger.debug(
            "dialog_relay: сообщение в топике %s от %s проигнорировано — отправитель не найден в таблице admins",
            message.message_thread_id, message.from_user.id,
        )
        return
    if message.text and message.text.startswith("/"):
        return  # команды в топике — не пересылаем

    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        logger.info(
            "dialog_relay: нет ACTIVE обращения для топика %s — сообщение админа %s не переслано пользователю",
            message.message_thread_id, db_admin.telegram_id,
        )
        return

    # проверяем, что этот админ участник диалога
    result = await session.execute(
        select(AppealParticipant).where(
            AppealParticipant.appeal_id == appeal.id,
            AppealParticipant.admin_id == db_admin.telegram_id,
        )
    )
    if result.scalar_one_or_none() is None:
        await message.reply(
            f"{ce(e.NO_ENTRY)} Ты не подключён к этому диалогу. "
            f"Попроси ответственного администратора выполнить /add {db_admin.nickname}"
        )
        return

    if message.text and await games_service.try_handle_guess(message.bot, session, appeal, message.from_user.id, message.text):
        return  # ход в игре — не пересылаем как обычное сообщение

    await relay_topic_to_user(session, message.bot, message, appeal)


# ─────────── редактирование сообщений в обе стороны ───────────

@router.edited_message(F.chat.type == "private")
async def user_edited(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        return
    mirror = await find_mirror(session, appeal.id, message.chat.id, message.message_id)
    if not mirror or not mirror.mirror_chat_id:
        return
    try:
        if message.text:
            await message.bot.edit_message_text(message.text, chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id)
        elif message.caption is not None:
            await message.bot.edit_message_caption(chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id, caption=message.caption)
        mirror.is_edited = True
        await session.commit()
    except Exception:
        pass


@router.edited_message(F.chat.type.in_({"group", "supergroup"}))
async def admin_edited(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None or message.message_thread_id is None:
        return
    if message.chat.id != settings.support_group_id:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    mirror = await find_mirror(session, appeal.id, message.chat.id, message.message_id)
    if not mirror or not mirror.mirror_chat_id:
        return
    try:
        if message.text:
            await message.bot.edit_message_text(message.text, chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id)
        elif message.caption is not None:
            await message.bot.edit_message_caption(chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id, caption=message.caption)
        mirror.is_edited = True
        await session.commit()
    except Exception:
        pass


# ─────────── реакции ───────────

@router.message_reaction()
async def relay_reaction(reaction: MessageReactionUpdated, session: AsyncSession) -> None:
    result = await session.execute(
        select(AppealMessage).where(
            AppealMessage.source_chat_id == reaction.chat.id,
            AppealMessage.source_message_id == reaction.message_id,
        )
    )
    mirror = result.scalar_one_or_none()
    if not mirror or not mirror.mirror_chat_id:
        return
    try:
        await reaction.bot.set_message_reaction(
            chat_id=mirror.mirror_chat_id,
            message_id=mirror.mirror_message_id,
            reaction=reaction.new_reaction,
        )
    except Exception:
        pass

