from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.db import get_session
from miniapps.backend.uploads import to_public_url
from db.models import Admin, AdminRole

router = APIRouter()


class AdminOut(BaseModel):
    telegram_id: int
    nickname: str
    role: str
    is_online: bool
    last_message_at: str | None
    avatar_url: str | None


@router.get("", response_model=list[AdminOut])
async def list_admins(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = result.scalars().all()
    admins.sort(key=lambda a: (not a.is_online, a.nickname.lower()))
    return [
        AdminOut(
            telegram_id=a.telegram_id,
            nickname=a.nickname,
            role=a.role.value if isinstance(a.role, AdminRole) else a.role,
            is_online=a.is_online,
            last_message_at=a.last_message_at.isoformat() if a.last_message_at else None,
            avatar_url=to_public_url(a.avatar_path),
        )
        for a in admins
    ]

