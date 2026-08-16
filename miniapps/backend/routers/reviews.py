from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.points import award_points
from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from miniapps.backend.uploads import REVIEWS_SUBDIR, save_upload_image, to_public_url
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
    admin_id: int
    admin_nickname: str
    admin_is_active: bool
    rating: int
    text: str | None
    photo_url: str | None
    created_at: str


@router.get("/recent-admins", response_model=list[RecentAdminOut])
async def recent_admins(
    session: AsyncSession = Depends(get_session), tg_user: dict = Depends(get_current_telegram_user)
):
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
    appeal_id: int = Form(...),
    admin_id: int = Form(...),
    rating: int = Form(..., ge=1, le=5),
    text: str | None = Form(default=None),
    photo: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    photo_path = None
    if photo is not None and photo.filename:
        photo_path = await save_upload_image(photo, REVIEWS_SUBDIR)

    session.add(
        Review(
            appeal_id=appeal_id,
            user_id=tg_user["id"],
            admin_id=admin_id,
            rating=rating,
            text=text or None,
            photo_path=photo_path,
        )
    )

    admin_res = await session.execute(select(Admin).where(Admin.telegram_id == admin_id))
    admin = admin_res.scalar_one_or_none()
    if admin is not None:
        if rating == 5:
            await award_points(session, admin, +1, "Отзыв 5★")
        elif rating <= 2:
            await award_points(session, admin, -2, f"Плохой отзыв ({rating}★)")

    await session.commit()
    return {"ok": True}


@router.get("/feed", response_model=list[ReviewOut])
async def reviews_feed(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Review).order_by(Review.created_at.desc()).limit(300))
    reviews = result.scalars().all()
    out = []
    for r in reviews:
        admin_res = await session.execute(select(Admin).where(Admin.telegram_id == r.admin_id))
        admin = admin_res.scalar_one_or_none()
        out.append(
            ReviewOut(
                admin_id=r.admin_id,
                admin_nickname=admin.nickname if admin else "—",
                admin_is_active=bool(admin and admin.is_active),
                rating=r.rating,
                text=r.text,
                photo_url=to_public_url(r.photo_path),
                created_at=r.created_at.isoformat(),
            )
        )
    return out
