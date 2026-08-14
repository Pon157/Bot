from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.support_topic import CB_ACCEPT_PREFIX
from bot.services.appeals import accept_appeal
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, Appeal, AppealMode, AppealStatus

router = Router(name="support_topic")


@router.callback_query(F.data.startswith(CB_ACCEPT_PREFIX))
async def cb_accept_appeal(callback: CallbackQuery, session: AsyncSession, db_admin: Admin | None) -> None:
    if db_admin is None:
        await callback.answer(f"{ce(e.NO_ENTRY)} Только администратор может принять обращение", show_alert=True)
        return

    appeal_id = int(callback.data.split(":")[-1])
    result = await session.execute(select(Appeal).where(Appeal.id == appeal_id))
    appeal = result.scalar_one_or_none()
    if appeal is None:
        await callback.answer("Обращение не найдено", show_alert=True)
        return
    if appeal.status != AppealStatus.PENDING:
        await callback.answer("Обращение уже принято другим администратором", show_alert=True)
        return

    invited = json.loads(appeal.invited_admin_ids or "[]")
    mode = AppealMode(appeal.mode)

    # По ТЗ: если конкретный(е) администратор(ы) вызван(ы) — только они могут принять.
    # "Кто быстрее" и ИИ-подбор (тоже список кандидатов) — принять может любой из приглашённых.
    # Общий список всех активных админов сюда не попадает: invited всегда заполнен создателем обращения.
    if invited and db_admin.telegram_id not in invited:
        await callback.answer(
            f"{ce(e.NO_ENTRY)} Это обращение адресовано другому администратору", show_alert=True
        )
        return

    await callback.answer(f"{ce(e.CHECK)} Обращение принято", show_alert=False)
    await accept_appeal(session, callback.bot, appeal, db_admin)

