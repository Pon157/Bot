from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AdminNorm(Base):
    """
    Норма (квота) сообщений админа за период. period_start сдвигается вперёд
    каждый раз, когда период заканчивается (см. bot/services/norm_scheduler.py) —
    "сколько сообщений он отправил" считается запросом к AppealMessage за
    промежуток [period_start, period_start + period_days], а не отдельным
    счётчиком, чтобы не было риска рассинхронизации.
    """

    __tablename__ = "admin_norms"

    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("admins.telegram_id", ondelete="CASCADE"), primary_key=True)
    messages_required: Mapped[int] = mapped_column(SmallInteger)
    period_days: Mapped[int] = mapped_column(SmallInteger)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # выставляется в True после того, как по итогам текущего (уже истёкшего)
    # периода владельцу был отправлен отчёт о невыполнении — чтобы не слать
    # повторно, пока планировщик не сдвинет период
    last_period_reported: Mapped[bool] = mapped_column(default=False)
