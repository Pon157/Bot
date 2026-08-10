from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from db.models import Admin, Appeal, AppealMessage, AppealStatus, MessageDirection


def _extract_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.video:
        return message.video.file_id
    if message.voice:
        return message.voice.file_id
    if message.audio:
        return message.audio.file_id
    if message.document:
        return message.document.file_id
    if message.sticker:
        return message.sticker.file_id
    if message.video_note:
        return message.video_note.file_id
    if message.animation:
        return message.animation.file_id
    return None


async def relay_user_to_topic(session: AsyncSession, bot: Bot, message: Message, appeal: Appeal) -> None:
    copied = await message.copy_to(settings.support_group_id, message_thread_id=appeal.topic_id)
    session.add(
        AppealMessage(
            appeal_id=appeal.id,
            direction=MessageDirection.USER_TO_ADMIN,
            sender_id=message.from_user.id,
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
            mirror_chat_id=settings.support_group_id,
            mirror_message_id=copied.message_id,
            content_type=message.content_type,
            text_preview=(message.text or message.caption or "")[:500],
            file_id=_extract_file_id(message),
        )
    )
    await session.commit()


async def relay_topic_to_user(session: AsyncSession, bot: Bot, message: Message, appeal: Appeal) -> None:
    copied = await message.copy_to(appeal.user_id)
    session.add(
        AppealMessage(
            appeal_id=appeal.id,
            direction=MessageDirection.ADMIN_TO_USER,
            sender_id=message.from_user.id,
            source_chat_id=message.chat.id,
            source_message_id=message.message_id,
            mirror_chat_id=appeal.user_id,
            mirror_message_id=copied.message_id,
            content_type=message.content_type,
            text_preview=(message.text or message.caption or "")[:500],
            file_id=_extract_file_id(message),
        )
    )
    await session.commit()

    # обновляем "последняя активность" у админа — используется для онлайн-статуса
    result = await session.execute(select(Admin).where(Admin.telegram_id == message.from_user.id))
    admin = result.scalar_one_or_none()
    if admin:
        from datetime import datetime, timezone

        admin.last_message_at = datetime.now(timezone.utc)
        await session.commit()


async def find_mirror(
    session: AsyncSession, appeal_id: int, source_chat_id: int, source_message_id: int
) -> AppealMessage | None:
    result = await session.execute(
        select(AppealMessage).where(
            AppealMessage.appeal_id == appeal_id,
            AppealMessage.source_chat_id == source_chat_id,
            AppealMessage.source_message_id == source_message_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_appeal_by_user(session: AsyncSession, user_id: int) -> Appeal | None:
    result = await session.execute(
        select(Appeal).where(Appeal.user_id == user_id, Appeal.status == AppealStatus.ACTIVE)
    )
    return result.scalar_one_or_none()


async def get_active_appeal_by_topic(session: AsyncSession, topic_id: int) -> Appeal | None:
    result = await session.execute(
        select(Appeal).where(Appeal.topic_id == topic_id, Appeal.status == AppealStatus.ACTIVE)
    )
    return result.scalar_one_or_none()
