from __future__ import annotations

import io

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils import emoji as e
from bot.utils.emoji import ce
from bot.utils.permissions import is_owner, resolve_target
from db.models import Admin, Appeal, AppealMessage, MessageDirection, User

router = Router(name="owner_tools")


# ───────────────────── /blocked_stats ─────────────────────
# Статистика пользователей, заблокировавших бота (актуально после рассылок —
# is_blocked проставляется в bot/services/relay.py при получении
# TelegramForbiddenError во время попытки что-то отправить пользователю).

@router.message(Command("blocked_stats"), F.chat.type == "private")
async def cmd_blocked_stats(message: Message, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return

    total_res = await session.execute(select(func.count()).select_from(User))
    total = total_res.scalar_one()

    blocked_res = await session.execute(select(func.count()).select_from(User).where(User.is_blocked.is_(True)))
    blocked = blocked_res.scalar_one()

    percent = (blocked / total * 100) if total else 0
    await message.answer(
        f"{ce(e.CHART)} <b>Статистика блокировок бота</b>\n\n"
        f"Всего пользователей: {total}\n"
        f"Заблокировали бота: {blocked} ({percent:.1f}%)\n\n"
        f"<i>Счётчик обновляется, когда бот пытается что-то отправить "
        f"заблокировавшему пользователю (например, ответ админа в диалоге) "
        f"и получает ошибку от Telegram. Разовой отдельной рассылки в боте "
        f"пока нет — если она нужна, дайте знать, добавим отдельной командой.</i>",
        parse_mode="HTML",
    )


# ───────────────────── /export_chat ─────────────────────
# Владелец может выгрузить ПОЛНУЮ переписку любого пользователя со всеми
# администраторами (по всем его обращениям), в отличие от обычной "Истории
# диалогов" пользователя, которая показывает только его собственные диалоги.

@router.message(Command("export_chat"), F.chat.type == "private")
async def cmd_export_chat(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not is_owner(message.from_user.id):
        return
    if not command.args:
        await message.answer(
            "Использование: <code>/export_chat id</code> или <code>/export_chat @username</code>",
            parse_mode="HTML",
        )
        return

    kind, value = resolve_target(command.args.strip())
    query = select(User)
    if kind == "id":
        query = query.where(User.telegram_id == int(value))
    else:
        query = query.where(User.username == value)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    if user is None:
        await message.answer(f"{ce(e.CROSS)} Пользователь не найден.")
        return

    appeals_res = await session.execute(
        select(Appeal).where(Appeal.user_id == user.telegram_id).order_by(Appeal.created_at)
    )
    appeals = appeals_res.scalars().all()
    if not appeals:
        await message.answer(f"{ce(e.INFO)} У пользователя нет ни одного обращения.")
        return

    admin_ids = set()
    lines: list[str] = [
        f"Выгрузка переписки пользователя {user.nickname or user.full_name} (id {user.telegram_id})",
        f"Всего обращений: {len(appeals)}",
        "=" * 60,
    ]
    for appeal in appeals:
        lines.append("")
        lines.append(f"--- Обращение №{appeal.id} | статус: {appeal.status.value} | создано: {appeal.created_at:%d.%m.%Y %H:%M} ---")
        msgs_res = await session.execute(
            select(AppealMessage)
            .where(AppealMessage.appeal_id == appeal.id)
            .order_by(AppealMessage.created_at)
        )
        msgs = msgs_res.scalars().all()
        for m in msgs:
            if m.direction == MessageDirection.USER_TO_ADMIN:
                who = user.nickname or user.full_name
            else:
                who = f"admin:{m.sender_id}"
                admin_ids.add(m.sender_id)
            ts = m.created_at.strftime("%d.%m.%Y %H:%M:%S")
            preview = m.text_preview or f"[{m.content_type}]"
            lines.append(f"[{ts}] {who}: {preview}")

    # подменяем "admin:<id>" на никнеймы одним запросом
    if admin_ids:
        admins_res = await session.execute(select(Admin).where(Admin.telegram_id.in_(admin_ids)))
        nick_by_id = {a.telegram_id: a.nickname for a in admins_res.scalars().all()}
        lines = [
            _sub_admin_placeholder(line, nick_by_id) for line in lines
        ]

    text = "\n".join(lines)
    buf = io.BytesIO(text.encode("utf-8"))
    await message.answer_document(
        BufferedInputFile(buf.read(), filename=f"chat_export_user_{user.telegram_id}.txt"),
        caption=f"{ce(e.CHECK)} Экспорт переписки пользователя {user.nickname or user.full_name}",
    )


def _sub_admin_placeholder(line: str, nick_by_id: dict[int, str]) -> str:
    for admin_id, nickname in nick_by_id.items():
        line = line.replace(f"admin:{admin_id}:", f"{nickname}:")
    return line
