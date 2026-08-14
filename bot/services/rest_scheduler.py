from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AdminRest

logger = logging.getLogger(__name__)


async def _release_expired_rests(sessionmaker: async_sessionmaker, bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    async with sessionmaker() as session:
        result = await session.execute(
            select(AdminRest).where(
                AdminRest.is_active.is_(True),
                AdminRest.until.is_not(None),
                AdminRest.until <= now,
            )
        )
        expired = result.scalars().all()
        for rest in expired:
            rest.is_active = False
            rest.ended_at = now

            admin_res = await session.execute(select(Admin).where(Admin.telegram_id == rest.admin_id))
            admin = admin_res.scalar_one_or_none()
            if admin:
                admin.is_active = True
                try:
                    await bot.send_message(
                        admin.telegram_id,
                        f"{ce(e.PARTY)} Срок твоего реста истёк, можешь возвращаться к работе!",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        if expired:
            await session.commit()
            logger.info("Автоматически снято рестов: %s", len(expired))


def start_rest_scheduler(sessionmaker: async_sessionmaker, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _release_expired_rests,
        "interval",
        minutes=1,
        args=[sessionmaker, bot],
        id="release_expired_rests",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик снятия рестов запущен (проверка раз в минуту)")
    return scheduler

