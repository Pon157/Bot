from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from bot.config import settings
from bot.middlewares.admin_context import AdminContextMiddleware
from bot.middlewares.agreement import AgreementMiddleware
from bot.middlewares.antispam import AntiSpamMiddleware
from bot.middlewares.ban import BanMiddleware
from bot.middlewares.db_session import DBSessionMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.handlers import register_all_routers
from bot.services.rest_scheduler import start_rest_scheduler
from bot.services.norm_scheduler import start_norm_scheduler
from db.base import make_engine, make_sessionmaker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def build_bot_session() -> AiohttpSession:
    proxy_url = getattr(settings, "bot_proxy_url", None) or os.getenv("BOT_PROXY_URL")

    if not proxy_url:
        logger.warning("Bot session: прокси НЕ найден, запуск прямого соединения")
        return AiohttpSession(timeout=40)

    if proxy_url.startswith("socks"):
        try:
            from aiohttp_socks import ProxyConnector
        except ImportError as exc:
            raise RuntimeError(
                "Для SOCKS5-прокси нужен пакет aiohttp-socks: pip install aiohttp-socks"
            ) from exc

        connector = ProxyConnector.from_url(proxy_url)
        session = AiohttpSession(timeout=40)
        session._connector_init = {"connector": connector}
        logger.info(f"Bot session: используется SOCKS5-прокси ({proxy_url})")
        return session

    session = AiohttpSession(proxy=proxy_url, timeout=40)
    logger.info(f"Bot session: используется HTTP(S)-прокси ({proxy_url})")
    return session


async def main() -> None:
    session = build_bot_session()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    for mw in (
        DBSessionMiddleware(sessionmaker),
        AdminContextMiddleware(sessionmaker),
        BanMiddleware(sessionmaker),
        AntiSpamMiddleware(owner_id=settings.owner_id, sessionmaker=sessionmaker),
        SubscriptionMiddleware(bot),
        AgreementMiddleware(sessionmaker),
    ):
        dp.update.outer_middleware.register(mw)

    register_all_routers(dp)

    scheduler = start_rest_scheduler(sessionmaker, bot)
    norm_scheduler = start_norm_scheduler(sessionmaker, bot)

    try:
        logger.info("Удаление вебхука и застрявших обновлений...")
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Не удалось удалить вебхук (продолжаем запуск): {e}")

    logger.info("Бот 'Спокойный рассвет' успешно запущен и ожидает сообщений!")
    try:
        await dp.start_polling(bot, sessionmaker=sessionmaker)
    finally:
        scheduler.shutdown(wait=False)
        norm_scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())

