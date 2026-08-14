from __future__ import annotations

import json
import logging

import httpx

from bot.config import settings
from db.models import Admin, User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты помогаешь подобрать наиболее подходящего администратора поддержки для пользователя "
    "по описанию его анкеты (о себе, хобби) и краткой специализации администраторов. "
    "Отвечай СТРОГО в формате JSON без каких-либо пояснений: "
    '{"admin_ids": [id1, id2], "reason": "краткое обоснование в 1-2 предложениях"}. '
    "Выбери от 1 до 3 наиболее подходящих администраторов из предложенного списка."
)


async def ai_match_admins(user: User, admins: list[Admin]) -> tuple[list[int], str]:
    """
    Возвращает (список telegram_id подходящих админов, текст обоснования).
    При любой ошибке API — безопасный fallback: вернуть онлайн-админов (или всех) без объяснения ИИ.
    """
    if not settings.openrouter_api_key or not admins:
        return _fallback(admins), "Автоматический подбор без ИИ (не настроен OPENROUTER_API_KEY)."

    candidates = [
        {
            "id": a.telegram_id,
            "nickname": a.nickname,
            "specialization": a.specialization or "",
            "online": a.is_online,
        }
        for a in admins
    ]

    user_payload = {
        "user_about": user.about or "",
        "user_hobbies": user.hobbies or "",
        "admins": candidates,
    }

    try:
        async with httpx.AsyncClient(base_url=settings.openrouter_base_url, timeout=20) as client:
            resp = await client.post(
                "/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            content = content.strip()
            # Некоторые совместимые с OpenAI эндпоинты (в т.ч. кастомные агенты
            # вроде Timeweb Cloud AI) игнорируют response_format=json_object и
            # оборачивают JSON в ```-блок или возвращают пустой content, если модель
            # решила "подумать" в отдельном поле (reasoning/thinking). Подчищаем это,
            # а не падаем с "Expecting value: line 1 column 1 (char 0)".
            if content.startswith("```"):
                content = content.strip("`")
                if content.lower().startswith("json"):
                    content = content[4:]
                content = content.strip()
            if not content:
                logger.warning("AI matching: пустой content в ответе API. Полный ответ: %s", data)
                return _fallback(admins), "ИИ вернул пустой ответ, подобрали автоматически."
            parsed = json.loads(content)
            ids = [int(i) for i in parsed.get("admin_ids", [])]
            valid_ids = {a.telegram_id for a in admins}
            ids = [i for i in ids if i in valid_ids]
            if not ids:
                return _fallback(admins), "ИИ не смог выбрать однозначно, подобрали автоматически."
            return ids, parsed.get("reason", "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI matching failed: %s", exc)
        return _fallback(admins), "ИИ временно недоступен, подобрали автоматически."


def _fallback(admins: list[Admin]) -> list[int]:
    online = [a.telegram_id for a in admins if a.is_online]
    return online[:2] if online else [a.telegram_id for a in admins[:2]]

