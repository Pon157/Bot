from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    appeal_id: Mapped[int] = mapped_column(ForeignKey("appeals.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"))
    admin_id: Mapped[int] = mapped_column(BigInteger)  # отдельный отзыв на КАЖДОГО участвовавшего админа

    rating: Mapped[int] = mapped_column(SmallInteger)  # 1..5
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # относительный путь к загруженному фото отзыва (например "uploads/reviews/<uuid>.jpg"),
    # раздаётся статикой FastAPI — см. miniapps/backend/app.py и routers/reviews.py
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)

