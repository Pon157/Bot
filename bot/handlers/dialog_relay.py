from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, MessageReactionUpdated
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services.relay import (
    find_mirror,
    get_active_appeal_by_topic,
    get_active_appeal_by_user,
    relay_topic_to_user,
    relay_user_to_topic,
)
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AppealParticipant, AppealStatus

router = Router(name="dialog_relay")


# ---------------------------- личка пользователя -> топик ----------------------------

@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def user_message_to_topic(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    # хендлер общий для всех private-сообщений вне FSM-состояний (регистрируется после onboarding/appeal_create,
    # поэтому FSM-состояния уже перехватили своё выше по цепочке роутеров)
    if db_admin is not None:
        return  # у админов личка бота не является диалогом с пользователем

    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        return  # нет активного диалога — просто игнорируем (не мусорим ответами вне контекста)

    await relay_user_to_topic(session, message.bot, message, appeal)


# ---------------------------- топик -> личка пользователя ----------------------------

@router.message(
    F.chat.id == settings.support_group_id,
    F.message_thread_id.is_not(None),
    ~F.text.startswith("/"),
)
async def admin_message_to_user(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        return  # пишут не админы (например, случайный участник группы) — не пересылаем

    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return

    result = await session.execute(
        select(AppealParticipant).where(
            AppealParticipant.appeal_id == appeal.id, AppealParticipant.admin_id == db_admin.telegram_id
        )
    )
    participant = result.scalar_one_or_none()
    if participant is None:
        await message.reply(
            f"{ce(e.NO_ENTRY)} Ты не подключён к этому диалогу. Попроси принявшего администратора "
            f"выполнить /add {db_admin.nickname}"
        )
        return

    await relay_topic_to_user(session, message.bot, message, appeal)


# ---------------------------- редактирование ----------------------------

@router.edited_message(F.chat.type == "private")
async def user_edited_message(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is not None:
        return
    appeal = await get_active_appeal_by_user(session, message.from_user.id)
    if appeal is None:
        return
    mirror = await find_mirror(session, appeal.id, message.chat.id, message.message_id)
    if mirror is None or not mirror.mirror_chat_id:
        return
    try:
        if message.text:
            await message.bot.edit_message_text(
                message.text, chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id
            )
        elif message.caption:
            await message.bot.edit_message_caption(
                chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id, caption=message.caption
            )
        mirror.is_edited = True
        await session.commit()
    except Exception:
        pass


@router.edited_message(F.chat.id == settings.support_group_id)
async def admin_edited_message(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None or message.message_thread_id is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    mirror = await find_mirror(session, appeal.id, message.chat.id, message.message_id)
    if mirror is None or not mirror.mirror_chat_id:
        return
    try:
        if message.text:
            await message.bot.edit_message_text(
                message.text, chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id
            )
        elif message.caption:
            await message.bot.edit_message_caption(
                chat_id=mirror.mirror_chat_id, message_id=mirror.mirror_message_id, caption=message.caption
            )
        mirror.is_edited = True
        await session.commit()
    except Exception:
        pass


# ---------------------------- реакции ----------------------------

@router.message_reaction()
async def relay_reaction(reaction: MessageReactionUpdated, session: AsyncSession, db_admin: Admin | None) -> None:
    """
    Зеркалим реакции в обе стороны. Aiogram отдаёт полный новый набор реакций
    в reaction.new_reaction — ставим тот же набор на зеркальное сообщение.
    """
    if reaction.chat.type == "private":
        appeal = await get_active_appeal_by_user(session, reaction.chat.id)
    else:
        if reaction.message_id is None:
            return
        # определяем топик через уже известный appeal по source_message_id ниже
        appeal = None

    # ищем appeal по зеркалу сообщения вне зависимости от направления
    from db.models import AppealMessage

    result = await session.execute(
        select(AppealMessage).where(
            AppealMessage.source_chat_id == reaction.chat.id,
            AppealMessage.source_message_id == reaction.message_id,
        )
    )
    mirror = result.scalar_one_or_none()
    if mirror is None or not mirror.mirror_chat_id:
        return

    try:
        await reaction.bot.set_message_reaction(
            chat_id=mirror.mirror_chat_id,
            message_id=mirror.mirror_message_id,
            reaction=reaction.new_reaction,
        )
    except Exception:
        pass


# ---------------------------- удаление ----------------------------
# Telegram Bot API не присылает событие удаления сообщений пользователем напрямую;
# отслеживать это можно только если сообщение удаляет САМ бот по команде администратора
# (см. admin_moderation.py -> /delete), либо через периодический опрос (не входит в MVP).
