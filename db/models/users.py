from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(256))

    # онбординг
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    questionnaire_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # мини-анкета
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    hobbies: Mapped[str | None] = mapped_column(Text, nullable=True)

    # модерация
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # заблокировал ли пользователь бота (узнаём по ошибке TelegramForbiddenError
    # при попытке что-то отправить — например, после рассылки)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # состояние
    is_in_dialog: Mapped[bool] = mapped_column(Boolean, default=False)
    active_appeal_id: Mapped[int | None] = mapped_column(
        ForeignKey("appeals.id", use_alter=True), nullable=True
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    favorite_admins: Mapped[list["FavoriteAdmin"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    warns: Mapped[list["Warn"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class FavoriteAdmin(Base):
    __tablename__ = "favorite_admins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.telegram_id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="favorite_admins")


class Warn(TimestampMixin, Base):
    __tablename__ = "warns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    issued_by: Mapped[int] = mapped_column(BigInteger)  # telegram_id админа
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="warns")

