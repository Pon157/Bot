from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# ─────────────────────────────────────────────────────────────────────────
# Простая защита от DDoS/абьюза для miniapp-backend. Без внешних зависимостей
# (slowapi и т.п.) — состояние в памяти процесса, этого достаточно для одного
# инстанса (как и антиспам бота). Лимиты намеренно щедрые: обычный пользователь
# мини-аппы (открытие страницы + поллинг игр раз в 1.5с + пара кликов) никогда
# их не заденет — это именно защита от скриптового/массового долбления API,
# а не от живых людей.
# ─────────────────────────────────────────────────────────────────────────

WINDOW_SECONDS = 60.0
MAX_REQUESTS_PER_WINDOW = 240     # ~4 запроса в секунду в среднем на IP
BURST_WINDOW_SECONDS = 5.0
MAX_BURST_REQUESTS = 40           # защита от резких вспышек (скриптов)
BAN_SECONDS = 30.0                # временный бан при превышении лимита


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._banned_until: dict[str, float] = {}

    @staticmethod
    def _client_key(request: Request) -> str:
        # За реверс-прокси (nginx) реальный IP обычно в X-Forwarded-For —
        # используем его первое значение, если есть, иначе IP соединения.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        # Статику (картинки/css/js) не лимитируем — там нет смысла: DDoS-риск
        # только у API-эндпоинтов, которые ходят в БД/Telegram.
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()

        banned_until = self._banned_until.get(key)
        if banned_until and now < banned_until:
            return JSONResponse(
                {"detail": "Слишком много запросов, попробуй чуть позже."},
                status_code=429,
                headers={"Retry-After": str(int(banned_until - now) + 1)},
            )

        dq = self._requests[key]
        while dq and now - dq[0] > WINDOW_SECONDS:
            dq.popleft()
        dq.append(now)

        burst_count = sum(1 for t in dq if now - t <= BURST_WINDOW_SECONDS)

        if len(dq) > MAX_REQUESTS_PER_WINDOW or burst_count > MAX_BURST_REQUESTS:
            self._banned_until[key] = now + BAN_SECONDS
            return JSONResponse(
                {"detail": "Слишком много запросов, попробуй чуть позже."},
                status_code=429,
                headers={"Retry-After": str(int(BAN_SECONDS))},
            )

        return await call_next(request)
