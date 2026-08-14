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
    # относительный путь к загруженной аватарке (например "uploads/avatars/<id>.jpg"),
    # раздаётся статикой FastAPI — см. miniapps/backend/app.py, устанавливается командой /setavatar
    avatar_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── система баллов ──
    points: Mapped[int] = mapped_column(default=0)
    total_messages_sent: Mapped[int] = mapped_column(default=0)  # для начисления +3 балла за каждые 500 сообщений
    # флаги, чтобы не штрафовать повторно за один и тот же период неактива —
    # сбрасываются, когда админ снова присылает сообщение (см. bot/services/relay.py)
    penalized_inactive_3d: Mapped[bool] = mapped_column(Boolean, default=False)
    penalized_inactive_6d: Mapped[bool] = mapped_column(Boolean, default=False)

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


class AdminPointsLog(TimestampMixin, Base):
    """Лог начислений/списаний баллов — показывается в /mynorm и /allnorms."""

    __tablename__ = "admin_points_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.telegram_id", ondelete="CASCADE"))
    delta: Mapped[int] = mapped_column()  # положительное или отрицательное число
    reason: Mapped[str] = mapped_column(Text)

