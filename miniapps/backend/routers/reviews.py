from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import Admin, Appeal, AppealStatus, Review

router = APIRouter()


class RecentAdminOut(BaseModel):
    appeal_id: int
    admin_id: int
    nickname: str
    already_reviewed: bool


class ReviewIn(BaseModel):
    appeal_id: int
    admin_id: int
    rating: int = Field(ge=1, le=5)
    text: str | None = None


class ReviewOut(BaseModel):
    admin_nickname: str
    rating: int
    text: str | None
    created_at: str


@router.get("/recent-admins", response_model=list[RecentAdminOut])
async def recent_admins(
    session: AsyncSession = Depends(get_session), tg_user: dict = Depends(get_current_telegram_user)
):
    """Обращения пользователя за последние 30 дней — для подсказки 'вы недавно говорили с ... оставить отзыв?'."""
    result = await session.execute(
        select(Appeal)
        .where(
            Appeal.user_id == tg_user["id"],
            Appeal.status == AppealStatus.CLOSED,
            Appeal.primary_admin_id.is_not(None),
        )
        .order_by(Appeal.closed_at.desc())
        .limit(10)
    )
    appeals = result.scalars().all()

    out = []
    for appeal in appeals:
        admin_res = await session.execute(select(Admin).where(Admin.telegram_id == appeal.primary_admin_id))
        admin = admin_res.scalar_one_or_none()
        if admin is None:
            continue
        review_res = await session.execute(
            select(Review).where(Review.appeal_id == appeal.id, Review.admin_id == admin.telegram_id)
        )
        out.append(
            RecentAdminOut(
                appeal_id=appeal.id,
                admin_id=admin.telegram_id,
                nickname=admin.nickname,
                already_reviewed=review_res.scalar_one_or_none() is not None,
            )
        )
    return out


@router.post("")
async def create_review(
    payload: ReviewIn,
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    session.add(
        Review(
            appeal_id=payload.appeal_id,
            user_id=tg_user["id"],
            admin_id=payload.admin_id,
            rating=payload.rating,
            text=payload.text,
        )
    )
    await session.commit()
    return {"ok": True}


@router.get("/feed", response_model=list[ReviewOut])
async def reviews_feed(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Review).order_by(Review.created_at.desc()).limit(50))
    reviews = result.scalars().all()
    out = []
    for r in reviews:
        admin_res = await session.execute(select(Admin).where(Admin.telegram_id == r.admin_id))
        admin = admin_res.scalar_one_or_none()
        out.append(
            ReviewOut(
                admin_nickname=admin.nickname if admin else "—",
                rating=r.rating,
                text=r.text,
                created_at=r.created_at.isoformat(),
            )
        )
    return out
