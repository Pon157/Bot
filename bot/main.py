from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from redis.asyncio import Redis

from bot.config import settings
from bot.middlewares.admin_context import AdminContextMiddleware
from bot.middlewares.agreement import AgreementMiddleware
from bot.middlewares.antispam import AntiSpamMiddleware
from bot.middlewares.ban import BanMiddleware
from bot.middlewares.db_session import DBSessionMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.handlers import register_all_routers
from db.base import make_engine, make_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def build_bot_session() -> AiohttpSession | None:
    """
    Прокси-сессия для бота. Полезно, если сервер, на котором крутится бот,
    не имеет прямого доступа к api.telegram.org (частая ситуация у части хостингов/регионов)
    или если нужно принудительно ходить через выделенный прокси для стабильности.

    Поддерживаемые схемы (через переменную окружения BOT_PROXY_URL):
      http://user:pass@host:port
      socks5://user:pass@host:port   (требует пакет aiohttp-socks)

    Если BOT_PROXY_URL не задан — используется обычное прямое соединение.
    """
    proxy_url = os.getenv("BOT_PROXY_URL")
    if not proxy_url:
        return None

    if proxy_url.startswith("socks"):
        try:
            from aiohttp_socks import ProxyConnector
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Для SOCKS5-прокси нужен пакет aiohttp-socks: pip install aiohttp-socks"
            ) from exc

        session = AiohttpSession()
        # aiogram AiohttpSession сам создаёт ClientSession лениво, поэтому подменяем
        # фабрику коннектора, а не сам session напрямую
        connector = ProxyConnector.from_url(proxy_url)
        session._connector_init = {"connector": connector}  # type: ignore[attr-defined]
        logger.info("Bot session: используется SOCKS5-прокси")
        return session

    # http/https-прокси aiohttp поддерживает нативно через параметр proxy у запроса,
    # aiogram позволяет прокинуть его через кастомный session с proxy=...
    session = AiohttpSession(proxy=proxy_url)
    logger.info("Bot session: используется HTTP(S)-прокси")
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

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = RedisStorage(redis=redis)

    dp = Dispatcher(storage=storage)

    # ВАЖНО: порядок регистрации мидлварей имеет значение.
    # 1) db_session — всем остальным мидлварям и хендлерам нужна сессия
    # 2) admin_context — узнаём, админ ли пользователь (нужно антиспаму)
    # 3) ban — банят раньше всего остального
    # 4) antispam — троттлим до дорогих проверок подписки/соглашения
    # 5) subscription — обязательная подписка на каналы
    # 6) agreement — пользовательское соглашение
    for mw in (
        DBSessionMiddleware(sessionmaker),
        AdminContextMiddleware(sessionmaker),
        BanMiddleware(sessionmaker),
        AntiSpamMiddleware(redis, owner_id=settings.owner_id),
        SubscriptionMiddleware(bot),
        AgreementMiddleware(sessionmaker),
    ):
        dp.update.outer_middleware.register(mw)

    register_all_routers(dp)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот 'Спокойный рассвет' запущен")
    await dp.start_polling(bot, sessionmaker=sessionmaker, redis=redis)


if __name__ == "__main__":
    asyncio.run(main())
