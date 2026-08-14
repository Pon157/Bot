from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services.points import award_points
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, Appeal, AppealMessage, AppealStatus, MessageDirection, User


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


async def relay_user_to_topic(
    session: AsyncSession, bot: Bot, message: Message, appeal: Appeal, thread_id: int | None = None
) -> None:
    """
    thread_id позволяет переопределить тред, в который копируется сообщение —
    используется, чтобы дублировать сообщения по ещё не принятому (PENDING)
    обращению в общий топик (appeal.topic_id для такого обращения ещё None).
    """
    target_thread_id = thread_id if thread_id is not None else appeal.topic_id
    copied = await message.copy_to(settings.support_group_id, message_thread_id=target_thread_id)
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
    # Подпись "Ответ от {ник}" — чтобы пользователь не путался, если в диалоге
    # ему отвечает несколько разных администраторов подряд. Шлём отдельным
    # коротким сообщением перед самим ответом (а не пытаемся вписать текст
    # внутрь исходного сообщения) — это безопаснее: copy_to() умеет
    # переопределять только caption у медиа, а не текст обычных сообщений, и
    # переписывать чужие entities (жирный/ссылки и т.п.) вручную — источник
    # лишних багов. Два бабла в чате — приемлемая цена за надёжность.
    admin_res = await session.execute(select(Admin).where(Admin.telegram_id == message.from_user.id))
    admin = admin_res.scalar_one_or_none()
    signature = f"{ce(e.CHAT)} <b>Ответ от {admin.nickname}:</b>" if admin else None

    try:
        if signature:
            await bot.send_message(appeal.user_id, signature, parse_mode="HTML")
        copied = await message.copy_to(appeal.user_id)
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — не роняем обработку, а фиксируем
        # это в БД (используется в /blocked_stats у владельца).
        result = await session.execute(select(User).where(User.telegram_id == appeal.user_id))
        user = result.scalar_one_or_none()
        if user is not None and not user.is_blocked:
            user.is_blocked = True
            user.blocked_at = datetime.now(timezone.utc)
            await session.commit()
        await message.reply(
            f"{ce(e.WARNING)} Не удалось доставить сообщение — пользователь заблокировал бота."
        )
        return

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

    # обновляем "последняя активность" у админа — используется для онлайн-статуса,
    # плюс баллы за вехи по сообщениям и сброс штрафных флагов за неактив
    # (admin уже получен выше — для подписи "Ответ от ...")
    if admin:
        admin.last_message_at = datetime.now(timezone.utc)
        # раз снова активен — штрафные флаги за прошлый простой больше не актуальны
        admin.penalized_inactive_3d = False
        admin.penalized_inactive_6d = False

        admin.total_messages_sent += 1
        if admin.total_messages_sent % 500 == 0:
            await award_points(session, admin, +3, f"{admin.total_messages_sent} сообщений в боте")

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


async def get_pending_appeal_by_user(session: AsyncSession, user_id: int) -> Appeal | None:
    result = await session.execute(
        select(Appeal).where(Appeal.user_id == user_id, Appeal.status == AppealStatus.PENDING)
    )
    return result.scalar_one_or_none()


async def get_active_appeal_by_topic(session: AsyncSession, topic_id: int) -> Appeal | None:
    result = await session.execute(
        select(Appeal).where(Appeal.topic_id == topic_id, Appeal.status == AppealStatus.ACTIVE)
    )
    return result.scalar_one_or_none()
