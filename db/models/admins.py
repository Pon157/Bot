from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class AdminRole(str, enum.Enum):
    OWNER = "owner"
    HEAD_ADMIN = "head_admin"
    ADMIN = "admin"


class Admin(TimestampMixin, Base):
    __tablename__ = "admins"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nickname: Mapped[str] = mapped_column(String(64))  # берётся из его собственного профиля/анкеты
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.ADMIN)

    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # мини-анкета админа (используется в т.ч. ИИ-подбором)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialization: Mapped[str | None] = mapped_column(Text, nullable=True)  # темы, в которых силён

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rests: Mapped[list["AdminRest"]] = relationship(back_populates="admin", cascade="all, delete-orphan")

    @property
    def is_online(self) -> bool:
        if not self.last_message_at:
            return False
        from datetime import timedelta, timezone

        return datetime.now(timezone.utc) - self.last_message_at < timedelta(minutes=5)


class AdminRest(TimestampMixin, Base):
    """Рест = временное отстранение админа от работы (/giverest, /endrest)."""

    __tablename__ = "admin_rests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.telegram_id", ondelete="CASCADE"))
    issued_by: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # None = бессрочно
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ended_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    admin: Mapped["Admin"] = relationship(back_populates="rests")
