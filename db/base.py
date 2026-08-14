from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BigIntPK:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)


def make_engine(database_url: str):
    return create_async_engine(database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)


def make_sessionmaker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)

