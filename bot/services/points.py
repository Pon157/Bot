from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Admin, AdminPointsLog

# ─────────────────────────────────────────────────────────────────────────
# Единая точка начисления/списания баллов админам — чтобы правило "баллы
# всегда сопровождаются записью в лог" не могло быть случайно нарушено в
# одном из мест, где начисление происходит (отзывы, вехи по сообщениям,
# штрафы за неактив).
# ─────────────────────────────────────────────────────────────────────────


async def award_points(session: AsyncSession, admin: Admin, delta: int, reason: str) -> None:
    admin.points += delta
    session.add(AdminPointsLog(admin_id=admin.telegram_id, delta=delta, reason=reason))
    # Коммит — на совести вызывающего кода (обычно там и так уже есть await session.commit()
    # рядом по месту использования), чтобы не плодить лишние транзакции.
