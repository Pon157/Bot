from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import settings
from bot.services.points import award_points
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AdminNorm, AdminRest, AppealMessage, MessageDirection

logger = logging.getLogger(__name__)

INACTIVITY_PENALTY_3D_DAYS = 3
INACTIVITY_PENALTY_6D_DAYS = 6


async def _count_admin_messages(session, admin_id: int, since: datetime, until: datetime) -> int:
    result = await session.execute(
        select(func.count()).select_from(AppealMessage).where(
            AppealMessage.sender_id == admin_id,
            AppealMessage.direction == MessageDirection.ADMIN_TO_USER,
            AppealMessage.created_at >= since,
            AppealMessage.created_at < until,
        )
    )
    return result.scalar_one()


async def _check_norms(sessionmaker: async_sessionmaker, bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        result = await session.execute(select(AdminNorm))
        norms = result.scalars().all()

        expired_reports: list[str] = []
        for norm in norms:
            period_end = norm.period_start + timedelta(days=norm.period_days)
            if now < period_end:
                continue  # период ещё не закончился

            sent = await _count_admin_messages(session, norm.admin_id, norm.period_start, period_end)
            if sent < norm.messages_required and not norm.last_period_reported:
                admin_res = await session.execute(select(Admin).where(Admin.telegram_id == norm.admin_id))
                admin = admin_res.scalar_one_or_none()
                nickname = admin.nickname if admin else str(norm.admin_id)
                expired_reports.append(
                    f"• {nickname} (id {norm.admin_id}): {sent}/{norm.messages_required} "
                    f"за {norm.period_days} дн. (период закончился {period_end:%d.%m.%Y %H:%M})"
                )
                norm.last_period_reported = True

            # сдвигаем период на следующий (сколько бы периодов ни было пропущено —
            # просто стартуем новый от текущего момента, чтобы не копить долги)
            norm.period_start = now
            norm.last_period_reported = False

        if expired_reports:
            await session.commit()
            text = (
                f"{ce(e.WARNING)} <b>Не выполнена норма сообщений</b>\n\n" + "\n".join(expired_reports)
            )
            try:
                await bot.send_message(settings.owner_id, text, parse_mode="HTML")
            except Exception:
                logger.exception("norm_scheduler: не удалось отправить отчёт владельцу")
        elif norms:
            await session.commit()


async def _check_inactivity_penalties(sessionmaker: async_sessionmaker) -> None:
    """
    -2 балла за 3 дня без активности и без реста, -4 балла (дополнительно) за
    6 дней. Пока админ на активном /giverest — не штрафуется вообще (это же
    и есть смысл реста). Флаги penalized_inactive_3d/6d не дают начислить
    штраф повторно за один и тот же непрерывный простой — сбрасываются, как
    только админ снова прислал сообщение (см. bot/services/relay.py).
    """
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
        admins = result.scalars().all()

        for admin in admins:
            rest_res = await session.execute(
                select(AdminRest).where(AdminRest.admin_id == admin.telegram_id, AdminRest.is_active.is_(True))
            )
            if rest_res.scalar_one_or_none() is not None:
                continue  # на ресте — не штрафуем

            if admin.last_message_at is None:
                continue  # ни разу не писал вообще — не с чем сравнивать, не штрафуем

            idle_days = (now - admin.last_message_at).days

            if idle_days >= INACTIVITY_PENALTY_3D_DAYS and not admin.penalized_inactive_3d:
                await award_points(session, admin, -2, f"Неактив {idle_days} дн. без реста")
                admin.penalized_inactive_3d = True

            if idle_days >= INACTIVITY_PENALTY_6D_DAYS and not admin.penalized_inactive_6d:
                await award_points(session, admin, -4, f"Неактив {idle_days} дн. без реста")
                admin.penalized_inactive_6d = True

        await session.commit()


def start_norm_scheduler(sessionmaker: async_sessionmaker, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _check_norms,
        "interval",
        minutes=15,
        args=[sessionmaker, bot],
        id="check_admin_norms",
        replace_existing=True,
    )
    scheduler.add_job(
        _check_inactivity_penalties,
        "interval",
        hours=1,
        args=[sessionmaker],
        id="check_admin_inactivity_penalties",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик проверки норм и активности администраторов запущен")
    return scheduler
