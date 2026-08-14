from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import User

router = APIRouter()


class ProfileOut(BaseModel):
    nickname: str | None
    about: str | None
    hobbies: str | None
    created_at: str


@router.get("", response_model=ProfileOut)
async def get_profile(
    session: AsyncSession = Depends(get_session), tg_user: dict = Depends(get_current_telegram_user)
):
    result = await session.execute(select(User).where(User.telegram_id == tg_user["id"]))
    user = result.scalar_one()
    return ProfileOut(
        nickname=user.nickname, about=user.about, hobbies=user.hobbies, created_at=user.created_at.isoformat()
    )

