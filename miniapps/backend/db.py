from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from db.base import make_engine, make_sessionmaker

_engine = make_engine(settings.database_url)
_sessionmaker: async_sessionmaker = make_sessionmaker(_engine)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _sessionmaker() as session:
        yield session
