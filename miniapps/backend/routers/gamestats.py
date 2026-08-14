from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from miniapps.backend.auth import get_current_telegram_user
from miniapps.backend.db import get_session
from db.models import Admin, GameResult, User

router = APIRouter()

GAME_LABELS = {
    "hangman": "Виселица",
    "guessnumber": "Угадай число",
    "ttt": "Крестики-нолики",
    "battleship": "Морской бой",
}


class LeaderboardEntry(BaseModel):
    telegram_id: int
    name: str
    is_admin: bool
    wins: int
    games_played: int


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    session: AsyncSession = Depends(get_session),
    tg_user: dict = Depends(get_current_telegram_user),
):
    result = await session.execute(select(GameResult))
    results = result.scalars().all()

    wins: dict[int, int] = defaultdict(int)
    played: dict[int, int] = defaultdict(int)
    for r in results:
        for pid in json.loads(r.participants):
            played[pid] += 1
        if r.winner_id is not None:
            wins[r.winner_id] += 1

    admin_res = await session.execute(select(Admin))
    admins_by_id = {a.telegram_id: a for a in admin_res.scalars().all()}

    all_ids = set(played.keys()) | set(wins.keys())
    user_res = await session.execute(select(User).where(User.telegram_id.in_(all_ids)))
    users_by_id = {u.telegram_id: u for u in user_res.scalars().all()}

    out: list[LeaderboardEntry] = []
    for pid in all_ids:
        if pid in admins_by_id:
            name, is_admin = admins_by_id[pid].nickname, True
        elif pid in users_by_id:
            u = users_by_id[pid]
            name, is_admin = (u.nickname or u.full_name or f"id {pid}"), False
        else:
            name, is_admin = f"id {pid}", False
        out.append(LeaderboardEntry(telegram_id=pid, name=name, is_admin=is_admin, wins=wins[pid], games_played=played[pid]))

    out.sort(key=lambda x: (-x.wins, -x.games_played))
    return out
