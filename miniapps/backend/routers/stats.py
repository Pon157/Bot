from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.db import get_session
from db.models import Admin, AppealMessage, User

router = APIRouter()


class StatsOut(BaseModel):
    active_users_24h: int
    active_admins_now: int
    total_users: int
    total_admins: int
    appeals_by_day: dict[str, int]


@router.get("", response_model=StatsOut)
async def stats(session: AsyncSession = Depends(get_session)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    active_users_res = await session.execute(
        select(AppealMessage.sender_id).where(AppealMessage.created_at >= since).distinct()
    )
    active_users = len(active_users_res.all())

    admins_res = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = admins_res.scalars().all()
    active_admins_now = sum(1 for a in admins if a.is_online)

    total_users = len((await session.execute(select(User.telegram_id))).all())

    return StatsOut(
        active_users_24h=active_users,
        active_admins_now=active_admins_now,
        total_users=total_users,
        total_admins=len(admins),
        appeals_by_day={},  # можно расширить агрегацией по дням при необходимости
    )
