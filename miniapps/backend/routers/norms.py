from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import Admin, AdminNorm, AdminPointsLog, AdminRole, AppealMessage, MessageDirection
from bot.config import settings

router = APIRouter()


class PointsLogEntry(BaseModel):
    delta: int
    reason: str
    created_at: str


class NormOut(BaseModel):
    admin_id: int
    nickname: str
    messages_required: int
    messages_sent: int
    period_days: int
    period_start: str
    period_end: str
    is_on_track: bool  # прогресс не отстаёт от доли прошедшего времени периода
    points: int
    points_log: list[PointsLogEntry]


async def _sent_count(session: AsyncSession, admin_id: int, since: datetime, until: datetime) -> int:
    result = await session.execute(
        select(func.count()).select_from(AppealMessage).where(
            AppealMessage.sender_id == admin_id,
            AppealMessage.direction == MessageDirection.ADMIN_TO_USER,
            AppealMessage.created_at >= since,
            AppealMessage.created_at < until,
        )
    )
    return result.scalar_one()


def _to_out(admin: Admin, norm: AdminNorm, sent: int, points_log: list[AdminPointsLog]) -> NormOut:
    now = datetime.now(timezone.utc)
    period_end = norm.period_start + timedelta(days=norm.period_days)
    elapsed_share = min(1.0, max(0.0, (now - norm.period_start).total_seconds() / max(1, (period_end - norm.period_start).total_seconds())))
    expected_by_now = norm.messages_required * elapsed_share
    return NormOut(
        admin_id=admin.telegram_id,
        nickname=admin.nickname,
        messages_required=norm.messages_required,
        messages_sent=sent,
        period_days=norm.period_days,
        period_start=norm.period_start.isoformat(),
        period_end=period_end.isoformat(),
        is_on_track=sent >= expected_by_now,
        points=admin.points,
        points_log=[
            PointsLogEntry(delta=p.delta, reason=p.reason, created_at=p.created_at.isoformat())
            for p in points_log
        ],
    )


async def _recent_points_log(session: AsyncSession, admin_id: int, limit: int = 20) -> list[AdminPointsLog]:
    result = await session.execute(
        select(AdminPointsLog)
        .where(AdminPointsLog.admin_id == admin_id)
        .order_by(AdminPointsLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/me", response_model=NormOut)
async def my_norm(
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    admin_res = await session.execute(select(Admin).where(Admin.telegram_id == tg_user["id"]))
    admin = admin_res.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=403, detail="Доступно только администраторам")

    norm_res = await session.execute(select(AdminNorm).where(AdminNorm.admin_id == admin.telegram_id))
    norm = norm_res.scalar_one_or_none()
    if norm is None:
        raise HTTPException(status_code=404, detail="Норма ещё не настроена — используй /setnorm")

    period_end = norm.period_start + timedelta(days=norm.period_days)
    sent = await _sent_count(session, admin.telegram_id, norm.period_start, period_end)
    points_log = await _recent_points_log(session, admin.telegram_id)
    return _to_out(admin, norm, sent, points_log)


@router.get("/all", response_model=list[NormOut])
async def all_norms(
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    is_owner = tg_user["id"] == settings.owner_id
    if not is_owner:
        admin_res = await session.execute(select(Admin).where(Admin.telegram_id == tg_user["id"]))
        requester = admin_res.scalar_one_or_none()
        if requester is None or requester.role not in (AdminRole.HEAD_ADMIN, AdminRole.OWNER):
            raise HTTPException(status_code=403, detail="Доступно только владельцу и хед-админам")

    result = await session.execute(select(AdminNorm))
    norms = result.scalars().all()

    out: list[NormOut] = []
    for norm in norms:
        admin_res = await session.execute(select(Admin).where(Admin.telegram_id == norm.admin_id))
        admin = admin_res.scalar_one_or_none()
        if admin is None:
            continue
        period_end = norm.period_start + timedelta(days=norm.period_days)
        sent = await _sent_count(session, admin.telegram_id, norm.period_start, period_end)
        points_log = await _recent_points_log(session, admin.telegram_id, limit=5)
        out.append(_to_out(admin, norm, sent, points_log))

    out.sort(key=lambda n: n.messages_sent / max(1, n.messages_required))
    return out
