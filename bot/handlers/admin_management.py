from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.services.relay import get_active_appeal_by_topic
from bot.utils import emoji as e
from bot.utils.emoji import ce
from bot.utils.permissions import is_head_or_owner, is_owner, resolve_target
from db.models import Admin, AdminRole, AppealParticipant, User

router = Router(name="admin_management")


def _only_support_group(message: Message) -> bool:
    return message.chat.id == settings.support_group_id


# ---------------------------- /add — подключить админа к текущему обращению ----------------------------

@router.message(Command("add"), F.message_thread_id.is_not(None))
async def cmd_add(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return

    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return

    # добавлять может только принявший (primary) или владелец/хед-админ
    is_primary = appeal.primary_admin_id == db_admin.telegram_id
    if not (is_primary or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Подключать администраторов может только принявший обращение.")
        return

    if not command.args:
        await message.reply("Использование: /add псевдоним|id|username")
        return

    kind, value = resolve_target(command.args.strip())
    query = select(Admin)
    if kind == "id":
        query = query.where(Admin.telegram_id == int(value))
    else:
        query = query.where((Admin.username == value) | (Admin.nickname == value))
    result = await session.execute(query)
    target = result.scalar_one_or_none()
    if target is None:
        await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
        return

    exists = await session.execute(
        select(AppealParticipant).where(
            AppealParticipant.appeal_id == appeal.id, AppealParticipant.admin_id == target.telegram_id
        )
    )
    if exists.scalar_one_or_none():
        await message.reply(f"{ce(e.INFO)} Этот администратор уже подключён к диалогу.")
        return

    session.add(
        AppealParticipant(
            appeal_id=appeal.id, admin_id=target.telegram_id, added_by=db_admin.telegram_id, is_primary=False
        )
    )
    await session.commit()
    await message.reply(
        f"{ce(e.CHECK)} <a href='tg://user?id={target.telegram_id}'>{target.nickname}</a> подключён к диалогу.",
        parse_mode="HTML",
    )


# ---------------------------- /transfer — передать диалог другому администратору ----------------------------

@router.message(Command("transfer"), F.message_thread_id.is_not(None))
async def cmd_transfer(
    message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None
) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    if not (appeal.primary_admin_id == db_admin.telegram_id or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Передавать диалог может только текущий ответственный.")
        return
    if not command.args:
        await message.reply("Использование: /transfer псевдоним|id|username")
        return

    kind, value = resolve_target(command.args.strip())
    query = select(Admin)
    query = query.where(Admin.telegram_id == int(value)) if kind == "id" else query.where(
        (Admin.username == value) | (Admin.nickname == value)
    )
    result = await session.execute(query)
    target = result.scalar_one_or_none()
    if target is None:
        await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
        return

    appeal.primary_admin_id = target.telegram_id
    exists = await session.execute(
        select(AppealParticipant).where(
            AppealParticipant.appeal_id == appeal.id, AppealParticipant.admin_id == target.telegram_id
        )
    )
    participant = exists.scalar_one_or_none()
    if participant is None:
        session.add(
            AppealParticipant(
                appeal_id=appeal.id, admin_id=target.telegram_id, added_by=db_admin.telegram_id, is_primary=True
            )
        )
    else:
        participant.is_primary = True
    await session.commit()

    await message.reply(
        f"{ce(e.ZAP)} Диалог передан <a href='tg://user?id={target.telegram_id}'>{target.nickname}</a>.",
        parse_mode="HTML",
    )


# ---------------------------- /addadmin, /removeadmin, /promote ----------------------------

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        return
    if not command.args:
        await message.reply("Использование: /addadmin @username Псевдоним")
        return
    parts = command.args.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /addadmin @username Псевдоним")
        return
    username, nickname = parts[0].lstrip("@"), parts[1].strip()

    # резолвим telegram_id через анкету, если пользователь уже писал боту (есть в users),
    # либо через get_chat, если это возможно по username
    user_res = await session.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    telegram_id = user.telegram_id if user else None

    if telegram_id is None:
        try:
            chat = await message.bot.get_chat(f"@{username}")
            telegram_id = chat.id
        except Exception:
            await message.reply(
                f"{ce(e.WARNING)} Не удалось определить id пользователя @{username}. "
                f"Попроси его сначала написать боту /start, затем повтори команду."
            )
            return

    existing = await session.execute(select(Admin).where(Admin.telegram_id == telegram_id))
    if existing.scalar_one_or_none():
        await message.reply(f"{ce(e.INFO)} Этот пользователь уже администратор.")
        return

    about = user.about if user else None
    admin = Admin(
        telegram_id=telegram_id,
        username=username,
        nickname=nickname,
        role=AdminRole.ADMIN,
        added_by=message.from_user.id,
        about=about,
    )
    session.add(admin)
    await session.commit()

    await message.reply(f"{ce(e.CHECK)} Администратор {nickname} добавлен.")
    try:
        await message.bot.send_message(
            telegram_id, f"{ce(e.CROWN)} Тебя назначили администратором в «Спокойный рассвет»!"
        )
    except Exception:
        pass


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        return
    if not command.args:
        await message.reply("Использование: /removeadmin id|username")
        return
    kind, value = resolve_target(command.args)
    query = select(Admin)
    query = query.where(Admin.telegram_id == int(value)) if kind == "id" else query.where(Admin.username == value)
    result = await session.execute(query)
    target = result.scalar_one_or_none()
    if target is None:
        await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
        return
    target.is_active = False
    await session.commit()
    await message.reply(f"{ce(e.CHECK)} {target.nickname} больше не администратор.")


@router.message(Command("promote"))
async def cmd_promote(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_owner(message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Только владелец может назначать хед-админов.")
        return
    if not command.args:
        await message.reply("Использование: /promote id|username")
        return
    kind, value = resolve_target(command.args)
    query = select(Admin)
    query = query.where(Admin.telegram_id == int(value)) if kind == "id" else query.where(Admin.username == value)
    result = await session.execute(query)
    target = result.scalar_one_or_none()
    if target is None:
        await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
        return
    target.role = AdminRole.HEAD_ADMIN
    await session.commit()
    await message.reply(f"{ce(e.CROWN)} {target.nickname} теперь хед-администратор.")


# ---------------------------- /broadcastusers — рассылка своим принятым пользователям ----------------------------

@router.message(Command("broadcastusers"))
async def cmd_broadcastusers(
    message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None
) -> None:
    if db_admin is None:
        return
    if not command.args:
        await message.reply("Использование: /broadcastusers текст рассылки")
        return

    from db.models import Appeal

    result = await session.execute(select(Appeal.user_id).where(Appeal.primary_admin_id == db_admin.telegram_id).distinct())
    user_ids = [row[0] for row in result.all()]

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await message.bot.send_message(
                uid, f"{ce(e.LOUDSPEAKER)} <b>Сообщение от {db_admin.nickname}:</b>\n\n{command.args}", parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1

    await message.reply(f"{ce(e.CHECK)} Рассылка завершена: доставлено {sent}, не доставлено {failed}.")


# ---------------------------- Панель владельца ----------------------------

@router.message(Command("adminpanel"))
async def cmd_admin_panel(message: Message, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return

    users_count = (await session.execute(select(User))).scalars().all()
    admins_count = (await session.execute(select(Admin).where(Admin.is_active.is_(True)))).scalars().all()
    online = [a for a in admins_count if a.is_online]

    text = (
        f"{ce(e.CROWN)} <b>Панель владельца</b>\n\n"
        f"{ce(e.CHART)} Пользователей: {len(users_count)}\n"
        f"{ce(e.SHIELD)} Администраторов: {len(admins_count)} (онлайн: {len(online)})\n\n"
        f"Команды:\n"
        f"/broadcastall текст — рассылка всем пользователям бота\n"
        f"/addadmin /removeadmin /promote — управление составом\n"
        f"/giverest /endrest — управление рестами"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("broadcastall"))
async def cmd_broadcastall(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return
    if not command.args:
        await message.reply("Использование: /broadcastall текст рассылки")
        return

    result = await session.execute(select(User.telegram_id))
    ids = [row[0] for row in result.all()]
    sent, failed = 0, 0
    for uid in ids:
        try:
            await message.bot.send_message(
                uid, f"{ce(e.LOUDSPEAKER)} <b>Объявление:</b>\n\n{command.args}", parse_mode="HTML"
            )
            sent += 1
        except Exception:
            failed += 1
    await message.reply(f"{ce(e.CHECK)} Рассылка: доставлено {sent}, не доставлено {failed}.")
