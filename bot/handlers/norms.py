from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.utils import emoji as e
from bot.utils.buttons import inline_btn
from bot.utils.emoji import ce
from bot.utils.permissions import is_head_or_owner, is_owner, resolve_target
from db.models import Admin, AdminNorm, User

router = Router(name="norms")

MIN_PERIOD_DAYS = 1
MAX_PERIOD_DAYS = 90


def _webapp_button(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[inline_btn("Открыть", emo=e.CHART, web_app=WebAppInfo(url=url), style="primary")]])


@router.message(Command("setnorm"), F.chat.type == "private")
async def cmd_setnorm(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        return

    args = (command.args or "").split()
    # Форматы: "/setnorm 150 7" (себе) или "/setnorm @nickname 150 7" (хед-админ/владелец — другому)
    target = db_admin
    if len(args) == 3:
        if not is_head_or_owner(db_admin, message.from_user.id):
            await message.reply(f"{ce(e.NO_ENTRY)} Настраивать норму другим может только хед-админ/владелец.")
            return
        kind, value = resolve_target(args[0])
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
        count_raw, period_raw = args[1], args[2]
    elif len(args) == 2:
        count_raw, period_raw = args
    else:
        await message.reply(
            "Использование:\n"
            "<code>/setnorm кол-во период_дней</code> — себе\n"
            "<code>/setnorm @ник кол-во период_дней</code> — другому (хед-админ/владелец)\n\n"
            "Например: <code>/setnorm 150 7</code> — 150 сообщений за 7 дней.",
            parse_mode="HTML",
        )
        return

    if not (count_raw.isdigit() and period_raw.isdigit()):
        await message.reply(f"{ce(e.WARNING)} Количество сообщений и период должны быть числами.")
        return
    count, period = int(count_raw), int(period_raw)
    if count < 1 or not (MIN_PERIOD_DAYS <= period <= MAX_PERIOD_DAYS):
        await message.reply(
            f"{ce(e.WARNING)} Количество — не меньше 1, период — от {MIN_PERIOD_DAYS} до {MAX_PERIOD_DAYS} дней."
        )
        return

    result = await session.execute(select(AdminNorm).where(AdminNorm.admin_id == target.telegram_id))
    norm = result.scalar_one_or_none()
    if norm is None:
        norm = AdminNorm(
            admin_id=target.telegram_id,
            messages_required=count,
            period_days=period,
            period_start=datetime.now(timezone.utc),
        )
        session.add(norm)
    else:
        norm.messages_required = count
        norm.period_days = period
        norm.period_start = datetime.now(timezone.utc)  # новая норма — новый отсчёт периода
        norm.last_period_reported = False
    await session.commit()

    await message.reply(
        f"{ce(e.CHECK)} Норма для {target.nickname}: {count} сообщений за {period} дн. "
        f"Отсчёт периода начат сейчас."
    )


@router.message(Command("mynorm"), F.chat.type == "private")
async def cmd_mynorm(message: Message, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        return
    if not settings.norms_webapp_url or not settings.norms_webapp_url.startswith("https://"):
        await message.reply(f"{ce(e.WARNING)} Не настроен NORMS_WEBAPP_URL в .env.")
        return
    url = settings.norms_webapp_url.rstrip("/") + "/?mode=me"
    await message.answer(f"{ce(e.CHART)} Твоя норма сообщений:", reply_markup=_webapp_button(url))


@router.message(Command("allnorms"), F.chat.type == "private")
async def cmd_allnorms(message: Message, db_admin: Admin | None) -> None:
    if not is_owner(message.from_user.id) and not (
        db_admin is not None and is_head_or_owner(db_admin, message.from_user.id)
    ):
        return
    if not settings.norms_webapp_url or not settings.norms_webapp_url.startswith("https://"):
        await message.reply(f"{ce(e.WARNING)} Не настроен NORMS_WEBAPP_URL в .env.")
        return
    url = settings.norms_webapp_url.rstrip("/") + "/?mode=all"
    await message.answer(f"{ce(e.CHART)} Нормы всех администраторов:", reply_markup=_webapp_button(url))


# ───────────────────── /seedialogs ─────────────────────
# Владелец/хед-админ может посмотреть ВСЕ диалоги любого пользователя в том же
# мини-аппе, которым пользуется сам пользователь (см. miniapps/backend/static/dialogs/,
# параметр view_as_user_id — на бэкенде доступ к чужим диалогам через него
# перепроверяется отдельно, см. miniapps/backend/routers/dialogs.py).

@router.message(Command("seedialogs"), F.chat.type == "private")
async def cmd_seedialogs(message: Message, command: CommandObject, session: AsyncSession, db_admin: Admin | None) -> None:
    if not is_owner(message.from_user.id) and not (
        db_admin is not None and is_head_or_owner(db_admin, message.from_user.id)
    ):
        return
    if not command.args:
        await message.reply("Использование: <code>/seedialogs id</code> или <code>/seedialogs @псевдоним</code>", parse_mode="HTML")
        return
    if not settings.dialogs_webapp_url or not settings.dialogs_webapp_url.startswith("https://"):
        await message.reply(f"{ce(e.WARNING)} Не настроен DIALOGS_WEBAPP_URL в .env.")
        return

    kind, value = resolve_target(command.args.strip())
    query = select(User)
    query = query.where(User.telegram_id == int(value)) if kind == "id" else query.where(User.username == value)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    if user is None:
        await message.reply(f"{ce(e.CROSS)} Пользователь не найден.")
        return

    url = settings.dialogs_webapp_url.rstrip("/") + f"/?view_as_user_id={user.telegram_id}"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[inline_btn("Открыть диалоги", emo=e.CHAT, web_app=WebAppInfo(url=url), style="primary")]]
    )
    await message.answer(
        f"{ce(e.CHAT)} Диалоги пользователя {user.nickname or user.full_name} (id {user.telegram_id}):",
        reply_markup=markup,
    )
