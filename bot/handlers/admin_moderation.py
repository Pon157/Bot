from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services.appeals import close_appeal
from bot.services.relay import find_mirror, get_active_appeal_by_topic
from bot.utils import emoji as e
from bot.utils.emoji import ce
from bot.utils.permissions import is_head_or_owner, is_owner, resolve_target
from db.models import Admin, AdminRest, User, Warn

router = Router(name="admin_moderation")


def _support_group(message: Message) -> bool:
    return message.chat.id == settings.support_group_id


async def _resolve_user(session: AsyncSession, raw: str) -> User | None:
    kind, value = resolve_target(raw)
    query = select(User)
    query = query.where(User.telegram_id == int(value)) if kind == "id" else query.where(User.username == value)
    result = await session.execute(query)
    return result.scalar_one_or_none()


# ---------------------------- warn / unwarn ----------------------------

@router.message(Command("warn"), F.message_thread_id.is_not(None))
async def cmd_warn(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    reason = command.args or "не указана"
    result = await session.execute(select(User).where(User.telegram_id == appeal.user_id))
    user = result.scalar_one()
    session.add(Warn(user_id=user.telegram_id, issued_by=db_admin.telegram_id, reason=reason))
    await session.commit()
    await message.reply(f"{ce(e.WARNING)} Пользователю выдано предупреждение. Причина: {reason}")
    try:
        await message.bot.send_message(user.telegram_id, f"{ce(e.WARNING)} Тебе выдано предупреждение. Причина: {reason}")
    except Exception:
        pass


@router.message(Command("unwarn"), F.message_thread_id.is_not(None))
async def cmd_unwarn(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    result = await session.execute(
        select(Warn).where(Warn.user_id == appeal.user_id, Warn.active.is_(True)).order_by(Warn.created_at.desc())
    )
    warn = result.scalars().first()
    if warn is None:
        await message.reply(f"{ce(e.INFO)} У пользователя нет активных предупреждений.")
        return
    warn.active = False
    await session.commit()
    await message.reply(f"{ce(e.CHECK)} Последнее предупреждение снято.")


# ---------------------------- ban / unban (только хед-админы и владелец) ----------------------------

@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Банить могут только хед-администраторы и владелец.")
        return
    if not command.args:
        await message.reply("Использование: /ban id|username причина")
        return
    parts = command.args.split(maxsplit=1)
    target_raw = parts[0]
    reason = parts[1] if len(parts) > 1 else "не указана"

    user = await _resolve_user(session, target_raw)
    if user is None:
        await message.reply(f"{ce(e.CROSS)} Пользователь не найден.")
        return
    user.is_banned = True
    user.ban_reason = reason
    user.banned_at = datetime.now(timezone.utc)
    await session.commit()
    await message.reply(f"{ce(e.NO_ENTRY)} Пользователь забанен. Причина: {reason}")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Разбанивать могут только хед-администраторы и владелец.")
        return
    if not command.args:
        await message.reply("Использование: /unban id|username")
        return
    user = await _resolve_user(session, command.args)
    if user is None:
        await message.reply(f"{ce(e.CROSS)} Пользователь не найден.")
        return
    user.is_banned = False
    user.ban_reason = None
    await session.commit()
    await message.reply(f"{ce(e.CHECK)} Пользователь разбанен.")


# ---------------------------- giverest / endrest ----------------------------

@router.message(Command("giverest"))
async def cmd_giverest(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Выдавать рест могут только хед-администраторы и владелец.")
        return
    if not command.args:
        await message.reply("Использование: /giverest id причина срок_в_днях (0 = бессрочно)")
        return
    parts = command.args.split()
    if len(parts) < 3:
        await message.reply("Использование: /giverest id причина срок_в_днях")
        return
    target_id = int(parts[0])
    days = int(parts[-1])
    reason = " ".join(parts[1:-1])

    result = await session.execute(select(Admin).where(Admin.telegram_id == target_id))
    target = result.scalar_one_or_none()
    if target is None:
        await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
        return

    until = datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None
    session.add(AdminRest(admin_id=target_id, issued_by=message.from_user.id, reason=reason, until=until))
    target.is_active = False  # на время реста админ не может участвовать в диалогах
    await session.commit()

    await message.reply(f"{ce(e.HOURGLASS)} {target.nickname} отправлен(а) в рест. Причина: {reason}")
    try:
        await message.bot.send_message(target_id, f"{ce(e.HOURGLASS)} Тебе выдан рест. Причина: {reason}")
    except Exception:
        pass


@router.message(Command("endrest"))
async def cmd_endrest(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Снимать рест могут только хед-администраторы и владелец.")
        return
    if not command.args:
        await message.reply("Использование: /endrest id")
        return
    target_id = int(command.args.strip())

    result = await session.execute(
        select(AdminRest).where(AdminRest.admin_id == target_id, AdminRest.is_active.is_(True))
    )
    rest = result.scalars().first()
    if rest is None:
        await message.reply(f"{ce(e.INFO)} У администратора нет активного реста.")
        return
    rest.is_active = False
    rest.ended_by = message.from_user.id
    rest.ended_at = datetime.now(timezone.utc)

    admin_result = await session.execute(select(Admin).where(Admin.telegram_id == target_id))
    admin = admin_result.scalar_one_or_none()
    if admin:
        admin.is_active = True
    await session.commit()

    await message.reply(f"{ce(e.CHECK)} Рест снят.")
    try:
        await message.bot.send_message(target_id, f"{ce(e.PARTY)} Твой рест снят, можешь возвращаться к работе!")
    except Exception:
        pass


# ---------------------------- close ----------------------------

@router.message(Command("close"), F.message_thread_id.is_not(None))
async def cmd_close(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    if not (appeal.primary_admin_id == db_admin.telegram_id or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Закрыть обращение может только ответственный администратор.")
        return
    await close_appeal(session, message.bot, appeal, message.from_user.id, command.args)


# ---------------------------- delete — удаление сообщения по реплаю в обе стороны ----------------------------

@router.message(Command("delete"), F.reply_to_message)
async def cmd_delete(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    """
    Работает и в топике (админ удаляет своё/чужое сообщение диалога — реплаем на него),
    и в личке пользователя (пользователь реплаем на своё сообщение).
    Удаляет исходное и зеркальное сообщение, помечает в БД.
    """
    replied = message.reply_to_message
    appeal = None
    if message.chat.id == settings.support_group_id and message.message_thread_id:
        appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    elif message.chat.type == "private":
        from bot.services.relay import get_active_appeal_by_user

        appeal = await get_active_appeal_by_user(session, message.chat.id)

    if appeal is None:
        return

    mirror = await find_mirror(session, appeal.id, replied.chat.id, replied.message_id)
    if mirror is None:
        await message.reply(f"{ce(e.WARNING)} Не удалось найти это сообщение в истории диалога.")
        return

    try:
        await message.bot.delete_message(replied.chat.id, replied.message_id)
    except Exception:
        pass
    try:
        if mirror.mirror_chat_id and mirror.mirror_message_id:
            await message.bot.delete_message(mirror.mirror_chat_id, mirror.mirror_message_id)
    except Exception:
        pass

    mirror.is_deleted = True
    await session.commit()
    await message.delete()
