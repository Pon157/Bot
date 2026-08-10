from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.support_topic import accept_keyboard
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, Appeal, AppealMode, AppealParticipant, AppealStatus, FavoriteAdmin, User


def admin_is_online(admin: Admin) -> bool:
    return admin.is_online


async def get_online_admins(session: AsyncSession) -> list[Admin]:
    result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = result.scalars().all()
    return [a for a in admins if admin_is_online(a)]


async def build_mode_text(mode: AppealMode, user: User) -> str:
    names = {
        AppealMode.BY_NICKNAME: "по псевдониму",
        AppealMode.FAVORITES: "из любимых администраторов",
        AppealMode.FASTEST: "кто быстрее ответит",
        AppealMode.AI_MATCH: "подбор ИИ",
    }
    return names[mode]


async def create_appeal(
    session: AsyncSession,
    bot: Bot,
    user: User,
    mode: AppealMode,
    invited_admin_ids: list[int],
    first_text: str | None,
) -> Appeal:
    appeal = Appeal(
        user_id=user.telegram_id,
        mode=mode,
        status=AppealStatus.PENDING,
        invited_admin_ids=json.dumps(invited_admin_ids),
    )
    session.add(appeal)
    await session.flush()

    user.is_in_dialog = False  # станет True только после ACCEPT
    user.active_appeal_id = appeal.id
    await session.commit()

    # тегаем администраторов в общем топике
    mentions = ""
    if invited_admin_ids:
        result = await session.execute(select(Admin).where(Admin.telegram_id.in_(invited_admin_ids)))
        admins = result.scalars().all()
        mentions = " ".join(f'<a href="tg://user?id={a.telegram_id}">{a.nickname}</a>' for a in admins)

    text = (
        f"{ce(e.FLAG)} <b>Новое обращение №{appeal.id}</b>\n\n"
        f"От: <b>{user.nickname or user.full_name}</b>\n"
        f"Режим: {await build_mode_text(mode, user)}\n"
        + (f"Приглашены: {mentions}\n" if mentions else "")
        + (f"\n{ce(e.CHAT)} Сообщение:\n{first_text}" if first_text else "")
    )

    msg = await bot.send_message(
        settings.support_group_id,
        text,
        message_thread_id=settings.support_topic_id,
        reply_markup=accept_keyboard(appeal.id),
        parse_mode="HTML",
    )
    appeal.common_message_id = msg.message_id
    await session.commit()
    return appeal


async def accept_appeal(session: AsyncSession, bot: Bot, appeal: Appeal, admin: Admin) -> int:
    """Создаёт отдельный форум-топик под обращение и возвращает его id."""
    result = await session.execute(select(User).where(User.telegram_id == appeal.user_id))
    user = result.scalar_one()

    topic = await bot.create_forum_topic(
        settings.support_group_id,
        name=f"#{appeal.id} {user.nickname or user.full_name}",
    )
    appeal.topic_id = topic.message_thread_id
    appeal.status = AppealStatus.ACTIVE
    appeal.primary_admin_id = admin.telegram_id
    await session.flush()

    session.add(
        AppealParticipant(
            appeal_id=appeal.id, admin_id=admin.telegram_id, added_by=admin.telegram_id, is_primary=True
        )
    )

    user.is_in_dialog = True
    await session.commit()

    intro = (
        f"{ce(e.CHECK)} Обращение №{appeal.id} принято администратором "
        f"<b>{admin.nickname}</b>.\n\n"
        f"Псевдоним: {user.nickname or user.full_name}\n"
        f"О себе: {user.about or '—'}\n"
        f"Хобби: {user.hobbies or '—'}\n\n"
        f"Команды: /add ник|id|username — подключить админа, /transfer — передать диалог, "
        f"/warn /unwarn /ban /unban, /close — закрыть обращение."
    )
    await bot.send_message(
        settings.support_group_id, intro, message_thread_id=topic.message_thread_id, parse_mode="HTML"
    )

    # убираем кнопку "Принять" в общем топике
    try:
        await bot.edit_message_reply_markup(
            settings.support_group_id, message_id=appeal.common_message_id, reply_markup=None
        )
    except Exception:
        pass

    await bot.send_message(
        user.telegram_id,
        f"{ce(e.CHECK)} Твоё обращение принял администратор <b>{admin.nickname}</b>. "
        f"Можешь писать сюда — сообщения дойдут напрямую.",
        parse_mode="HTML",
    )
    return topic.message_thread_id


async def close_appeal(session: AsyncSession, bot: Bot, appeal: Appeal, closed_by: int, reason: str | None) -> None:
    appeal.status = AppealStatus.CLOSED
    appeal.closed_by = closed_by
    appeal.closed_at = datetime.now(timezone.utc)
    appeal.close_reason = reason

    result = await session.execute(select(User).where(User.telegram_id == appeal.user_id))
    user = result.scalar_one()
    user.is_in_dialog = False
    user.active_appeal_id = None
    await session.commit()

    from bot.keyboards.main_menu import main_menu_keyboard

    await bot.send_message(
        user.telegram_id,
        f"{ce(e.INFO)} Обращение №{appeal.id} закрыто."
        + (f" Причина: {reason}" if reason else "")
        + f"\n\nЕсли хочешь — можешь оставить отзыв о диалоге в мини-приложении «Панель отзывов».",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(has_active_appeal=False),
    )
    if appeal.topic_id:
        try:
            await bot.close_forum_topic(settings.support_group_id, appeal.topic_id)
        except Exception:
            pass
