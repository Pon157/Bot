from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from bot.config import settings


def verify_init_data(init_data: str) -> dict:
    """
    Проверяет подпись Telegram WebApp initData.
    Возвращает распарсенные поля включая объект user.
    """
    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Отсутствует hash в initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Невалидная подпись initData")

    return parsed


async def get_current_telegram_user(
    x_telegram_init_data: str = Header(default=""),
) -> dict:
    """
    Зависимость FastAPI: извлекает и верифицирует пользователя из initData.
    initData приходит в заголовке X-Telegram-Init-Data, который JS-сторона
    ставит в каждый запрос: headers: { 'X-Telegram-Init-Data': tg.initData }
    """
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Заголовок X-Telegram-Init-Data отсутствует")

    parsed = verify_init_data(x_telegram_init_data)
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Нет данных пользователя в initData")

    try:
        return json.loads(user_raw)
    except Exception:
        raise HTTPException(status_code=401, detail="Не удалось распарсить user из initData")

