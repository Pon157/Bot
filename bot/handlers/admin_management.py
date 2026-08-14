from __future__ import annotations

import uuid
from pathlib import Path

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

# Тот же каталог, что раздаётся статикой FastAPI в miniapps/backend/app.py как /uploads
AVATARS_DIR = Path("miniapps/backend/static/uploads/avatars")
MAX_AVATAR_BYTES = 25 * 1024 * 1024  # 25 МБ, как и для фото в отзывах


def _only_support_group(message: Message) -> bool:
    return message.chat.id == settings.support_group_id


# ───────────────────── /setavatar ─────────────────────
# Использование (в личке с ботом):
#   1) Отправить боту фото с подписью "/setavatar" — себе.
#   2) Ответить командой "/setavatar" на уже отправленное боту фото — себе.
#   3) Хед-админ/владелец: ответить "/setavatar @username" на фото — поставит аватар указанному админу.

@router.message(Command("setavatar"), F.chat.type == "private")
async def cmd_setavatar(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        await message.reply(f"{ce(e.NO_ENTRY)} Эта команда доступна только администраторам.")
        return

    photo_message = message if message.photo else (message.reply_to_message if message.reply_to_message and message.reply_to_message.photo else None)
    if photo_message is None:
        await message.reply(
            f"{ce(e.WARNING)} Отправь фото с подписью /setavatar, "
            "или ответь командой /setavatar на уже отправленное фото."
        )
        return

    target = db_admin
    if command.args:
        if not is_head_or_owner(db_admin, message.from_user.id):
            await message.reply(f"{ce(e.NO_ENTRY)} Ставить аватар другим админам может только хед-админ/владелец.")
            return
        kind, value = resolve_target(command.args.strip())
        query = select(Admin)
        query = query.where(Admin.telegram_id == int(value)) if kind == "id" else query.where(
            (Admin.username == value) | (Admin.nickname == value)
        )
        result = await session.execute(query)
        found = result.scalar_one_or_none()
        if found is None:
            await message.reply(f"{ce(e.CROSS)} Администратор не найден.")
            return
        target = found

    tg_photo = photo_message.photo[-1]  # самое большое разрешение
    file = await message.bot.get_file(tg_photo.file_id)
    if file.file_size and file.file_size > MAX_AVATAR_BYTES:
        await message.reply(f"{ce(e.WARNING)} Файл слишком большой (максимум 25 МБ).")
        return

    buf = await message.bot.download_file(file.file_path)
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{target.telegram_id}_{uuid.uuid4().hex[:8]}.jpg"
    (AVATARS_DIR / filename).write_bytes(buf.read())

    target.avatar_path = f"uploads/avatars/{filename}"
    await session.commit()

    await message.reply(
        f"{ce(e.CHECK)} Аватар {'обновлён' if target.telegram_id == db_admin.telegram_id else f'для {target.nickname} обновлён'}. "
        "Он появится в «Администрация онлайн» в мини-приложении."
    )


# ───────────────────── /add ─────────────────────

@router.message(Command("add"), F.message_thread_id.is_not(None))
async def cmd_add(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return
    is_primary = appeal.primary_admin_id == db_admin.telegram_id
    if not (is_primary or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Подключать администраторов может только принявший обращение.")
        return
    if not command.args:
        await message.reply("Использование: /add псевдоним|id|@username")
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
    session.add(AppealParticipant(
        appeal_id=appeal.id, admin_id=target.telegram_id, added_by=db_admin.telegram_id, is_primary=False
    ))
    await session.commit()
    await message.reply(
        f"{ce(e.CHECK)} <a href='tg://user?id={target.telegram_id}'>{target.nickname}</a> подключён к диалогу.",
        parse_mode="HTML",
    )


# ───────────────────── /remove ─────────────────────

@router.message(Command("remove"), F.message_thread_id.is_not(None))
async def cmd_remove(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        await message.reply(f"{ce(e.WARNING)} Это не топик активного обращения.")
        return
    is_primary = appeal.primary_admin_id == db_admin.telegram_id
    if not (is_primary or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Отключать администраторов может только принявший обращение.")
        return
    if not command.args:
        await message.reply("Использование: /remove псевдоним|id|@username")
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
    if target.telegram_id == appeal.primary_admin_id:
        await message.reply(
            f"{ce(e.WARNING)} Нельзя отключить ответственного администратора — сначала выполни /transfer."
        )
        return
    exists = await session.execute(
        select(AppealParticipant).where(
            AppealParticipant.appeal_id == appeal.id, AppealParticipant.admin_id == target.telegram_id
        )
    )
    participant = exists.scalar_one_or_none()
    if participant is None:
        await message.reply(f"{ce(e.INFO)} Этот администратор и так не подключён к диалогу.")
        return
    await session.delete(participant)
    await session.commit()
    await message.reply(
        f"{ce(e.CHECK)} <a href='tg://user?id={target.telegram_id}'>{target.nickname}</a> отключён от диалога.",
        parse_mode="HTML",
    )


# ───────────────────── /transfer ─────────────────────

@router.message(Command("transfer"), F.message_thread_id.is_not(None))
async def cmd_transfer(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not _only_support_group(message) or db_admin is None:
        return
    appeal = await get_active_appeal_by_topic(session, message.message_thread_id)
    if appeal is None:
        return
    if not (appeal.primary_admin_id == db_admin.telegram_id or is_head_or_owner(db_admin, message.from_user.id)):
        await message.reply(f"{ce(e.NO_ENTRY)} Передавать диалог может только текущий ответственный.")
        return
    if not command.args:
        await message.reply("Использование: /transfer псевдоним|id|@username")
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
        session.add(AppealParticipant(
            appeal_id=appeal.id, admin_id=target.telegram_id, added_by=db_admin.telegram_id, is_primary=True
        ))
    else:
        participant.is_primary = True
    await session.commit()
    await message.reply(
        f"{ce(e.ZAP)} Диалог передан <a href='tg://user?id={target.telegram_id}'>{target.nickname}</a>.",
        parse_mode="HTML",
    )


# ───────────────────── /addadmin ─────────────────────

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
    user_res = await session.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    telegram_id = user.telegram_id if user else None
    if telegram_id is None:
        try:
            chat = await message.bot.get_chat(f"@{username}")
            telegram_id = chat.id
        except Exception:
            await message.reply(
                f"{ce(e.WARNING)} Не удалось определить id @{username}. "
                "Попроси его написать /start боту и повтори."
            )
            return
    existing = await session.execute(select(Admin).where(Admin.telegram_id == telegram_id))
    if existing.scalar_one_or_none():
        await message.reply(f"{ce(e.INFO)} Этот пользователь уже администратор.")
        return
    admin = Admin(
        telegram_id=telegram_id, username=username, nickname=nickname,
        role=AdminRole.ADMIN, added_by=message.from_user.id,
        about=user.about if user else None,
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


# ───────────────────── /removeadmin ─────────────────────

@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_head_or_owner(db_admin, message.from_user.id):
        return
    if not command.args:
        await message.reply("Использование: /removeadmin id|@username")
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


# ───────────────────── /promote ─────────────────────

@router.message(Command("promote"))
async def cmd_promote(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_owner(message.from_user.id):
        await message.reply(f"{ce(e.NO_ENTRY)} Только владелец может назначать хед-админов.")
        return
    if not command.args:
        await message.reply("Использование: /promote id|@username")
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


# ───────────────────── /broadcastusers — все типы медиа ─────────────────────

@router.message(Command("broadcastusers"))
async def cmd_broadcastusers(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        return
    # текст берём из args ИЛИ из подписи/текста реплая (если ответили на медиа)
    if not command.args and not message.reply_to_message:
        await message.reply(
            "Использование:\n"
            "  /broadcastusers текст\n"
            "  Или ответьте на сообщение с медиа командой /broadcastusers\n\n"
            "Уйдёт только тем пользователям, с которыми у тебя сейчас ОТКРЫТ диалог "
            "(обращение в статусе «в процессе»)."
        )
        return

    from db.models import Appeal, AppealStatus
    result = await session.execute(
        select(Appeal.user_id)
        .where(
            Appeal.primary_admin_id == db_admin.telegram_id,
            Appeal.status == AppealStatus.ACTIVE,  # ТОЛЬКО открытые сейчас диалоги, не вся история
        )
        .distinct()
    )
    user_ids = [row[0] for row in result.all()]
    if not user_ids:
        await message.reply(f"{ce(e.INFO)} У тебя сейчас нет ни одного открытого диалога — рассылать некому.")
        return

    sent, failed = 0, 0
    source = message.reply_to_message or message

    for uid in user_ids:
        try:
            if message.reply_to_message:
                # пересылаем медиа/сообщение любого типа
                await message.reply_to_message.copy_to(
                    uid,
                    caption=(message.reply_to_message.caption or "") +
                             (f"\n\n{ce(e.LOUDSPEAKER)} <i>Сообщение от {db_admin.nickname}</i>" if command.args else ""),
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    uid,
                    f"{ce(e.LOUDSPEAKER)} <b>Сообщение от {db_admin.nickname}:</b>\n\n{command.args}",
                    parse_mode="HTML",
                )
            sent += 1
        except Exception:
            failed += 1

    await message.reply(f"{ce(e.CHECK)} Рассылка завершена: доставлено {sent}, не доставлено {failed}.")


# ───────────────────── Панель владельца ─────────────────────

@router.message(Command("adminpanel"))
async def cmd_admin_panel(message: Message, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return
    users_res = await session.execute(select(User.telegram_id))
    admins_res = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = admins_res.scalars().all()
    online = [a for a in admins if a.is_online]
    text = (
        f"{ce(e.CROWN)} <b>Панель владельца</b>\n\n"
        f"{ce(e.CHART)} Пользователей: {len(users_res.all())}\n"
        f"{ce(e.SHIELD)} Администраторов: {len(admins)} (онлайн: {len(online)})\n\n"
        "Команды:\n"
        "/broadcastall — рассылка всем пользователям\n"
        "/addadmin /removeadmin /promote — управление составом\n"
        "/giverest /endrest — управление рестами"
    )
    await message.answer(text, parse_mode="HTML")


# ───────────────────── /broadcastall — все типы медиа ─────────────────────

@router.message(Command("broadcastall"))
async def cmd_broadcastall(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return
    if not command.args and not message.reply_to_message:
        await message.reply(
            "Использование:\n"
            "  /broadcastall текст\n"
            "  Или ответьте на сообщение с медиа командой /broadcastall"
        )
        return

    result = await session.execute(select(User.telegram_id))
    ids = [row[0] for row in result.all()]
    sent, failed = 0, 0

    for uid in ids:
        try:
            if message.reply_to_message:
                caption_suffix = f"\n\n{ce(e.LOUDSPEAKER)} <i>Объявление от администрации</i>"
                orig_caption = message.reply_to_message.caption or ""
                await message.reply_to_message.copy_to(
                    uid,
                    caption=orig_caption + (caption_suffix if command.args == "" else ""),
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    uid,
                    f"{ce(e.LOUDSPEAKER)} <b>Объявление:</b>\n\n{command.args}",
                    parse_mode="HTML",
                )
            sent += 1
        except Exception:
            failed += 1

    await message.reply(f"{ce(e.CHECK)} Рассылка: доставлено {sent}, не доставлено {failed}.")
