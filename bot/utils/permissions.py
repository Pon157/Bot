from __future__ import annotations

from bot.config import settings
from db.models import Admin, AdminRole


def is_owner(telegram_id: int) -> bool:
    return telegram_id == settings.owner_id


def is_head_or_owner(admin: Admin | None, telegram_id: int) -> bool:
    if is_owner(telegram_id):
        return True
    return admin is not None and admin.role in (AdminRole.HEAD_ADMIN, AdminRole.OWNER)


def resolve_target(raw: str) -> tuple[str, str]:
    """Возвращает (тип, значение): ('id', '123') / ('username', 'name')."""
    raw = raw.strip().lstrip("@")
    if raw.isdigit():
        return "id", raw
    return "username", raw
