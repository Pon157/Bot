from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class AppealMode(str, enum.Enum):
    BY_NICKNAME = "by_nickname"       # выбор конкретного админа вручную
    FAVORITES = "favorites"           # тегаются избранные админы
    FASTEST = "fastest"               # кто быстрее нажмёт
    AI_MATCH = "ai_match"             # подбор ИИ


class AppealStatus(str, enum.Enum):
    PENDING = "pending"        # висит в общем топике, ждёт принятия
    ACTIVE = "active"          # открыт отдельный топик, идёт диалог
    CLOSED = "closed"          # закрыт
    CANCELLED = "cancelled"    # отменён пользователем до принятия


class Appeal(TimestampMixin, Base):
    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    mode: Mapped[AppealMode] = mapped_column(Enum(AppealMode))
    status: Mapped[AppealStatus] = mapped_column(Enum(AppealStatus), default=AppealStatus.PENDING)

    # кандидаты, которых тегнули в общем топике (список telegram_id через запятую в JSON-строке)
    invited_admin_ids: Mapped[str] = mapped_column(Text, default="[]")

    # топики
    common_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # сообщение в общем топике
    topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # id открытого форум-топика

    primary_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # кто принял (главный)

    closed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    participants: Mapped[list["AppealParticipant"]] = relationship(
        back_populates="appeal", cascade="all, delete-orphan"
    )
    messages: Mapped[list["AppealMessage"]] = relationship(
        back_populates="appeal", cascade="all, delete-orphan"
    )


class AppealParticipant(Base):
    """Админы, допущенные писать в топик (принявший + добавленные через /add)."""

    __tablename__ = "appeal_participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"))
    admin_id: Mapped[int] = mapped_column(BigInteger)
    added_by: Mapped[int] = mapped_column(BigInteger)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    appeal: Mapped["Appeal"] = relationship(back_populates="participants")


class MessageDirection(str, enum.Enum):
    USER_TO_ADMIN = "user_to_admin"
    ADMIN_TO_USER = "admin_to_user"


class AppealMessage(TimestampMixin, Base):
    """
    Лог каждого сообщения диалога — нужен и для пересылки медиа 1:1, и для
    отрисовки красивой истории переписки в мини-аппе (dialogs webapp).
    """

    __tablename__ = "appeal_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"))
    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection))

    sender_id: Mapped[int] = mapped_column(BigInteger)

    # исходное сообщение (в личке юзера или в топике) и зеркальное (переслано на другую сторону)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    mirror_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mirror_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    content_type: Mapped[str] = mapped_column(String(32))  # text/photo/video/voice/document/sticker/...
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)  # file_id медиа (для отдачи в мини-аппу)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    appeal: Mapped["Appeal"] = relationship(back_populates="messages")

