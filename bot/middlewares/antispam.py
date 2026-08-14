from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from aiogram import Bot, BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.utils import emoji as e
from bot.utils.emoji import ce

logger = logging.getLogger(__name__)


class AntiSpamMiddleware(BaseMiddleware):
    """
    Антифлуд без внешних зависимостей — состояние хранится в памяти процесса.
    Подходит для одного инстанса бота (типичный случай для такого проекта).
    Если бот когда-нибудь будет масштабирован на несколько процессов —
    можно заменить это хранилище на Redis, интерфейс метода __call__ не изменится.

    Логика (двухуровневая — это важно для регулярного, но не слишком частого
    спама, который раньше проходил мимо антиспама):

      - soft_interval: тихо игнорируем событие, если оно пришло раньше, чем через
        soft_interval секунд после предыдущего (защита от даблтапов по кнопкам).
        Спамер с "хорошей регулярностью" (например, ровно раз в секунду) этот
        порог не задевает вообще — поэтому одного soft_interval недостаточно.

      - burst-уровень (hard_limit событий за hard_window секунд): защита от
        быстрых очередей сообщений — короткий мьют.

      - sustained-уровень (sustained_limit событий за sustained_window секунд,
        окно значительно шире): ловит именно тот случай, который раньше не
        ловился — размеренный, но настойчивый спам, не превышающий burst-порог
        ни разу, но суммарно превышающий разумную активность. Мьют на этом
        уровне длиннее и засчитывается как нарушение для автобана.

      - если пользователь получает `ban_after_violations` нарушений
        (burst ИЛИ sustained) в течение `violation_memory_seconds` — считаем,
        что это не "случайно расшалившийся" живой человек, а спам-бот/абьюз,
        и баним пользователя в БД (это отдельный источник банов от команды
        /warn — оба пишут в одно и то же поле User.is_banned).
    """

    def __init__(
        self,
        owner_id: int,
        sessionmaker: async_sessionmaker | None = None,
        soft_interval: float = 0.7,
        hard_limit: int = 6,
        hard_window: float = 8.0,
        mute_seconds: float = 20.0,
        sustained_limit: int = 20,
        sustained_window: float = 60.0,
        sustained_mute_seconds: float = 120.0,
        ban_after_violations: int = 3,
        violation_memory_seconds: float = 600.0,
    ):
        self.owner_id = owner_id
        self.sessionmaker = sessionmaker
        self.soft_interval = soft_interval
        self.hard_limit = hard_limit
        self.hard_window = hard_window
        self.mute_seconds = mute_seconds
        self.sustained_limit = sustained_limit
        self.sustained_window = sustained_window
        self.sustained_mute_seconds = sustained_mute_seconds
        self.ban_after_violations = ban_after_violations
        self.violation_memory_seconds = violation_memory_seconds

        self._last_event: dict[int, float] = {}
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._sustained_events: dict[int, deque[float]] = defaultdict(deque)
        self._muted_until: dict[int, float] = {}
        self._violations: dict[int, deque[float]] = defaultdict(deque)

    @staticmethod
    def _cleanup(dq: "deque[float]", now: float, window: float) -> None:
        while dq and now - dq[0] > window:
            dq.popleft()

    async def _register_violation_and_maybe_ban(self, user_id: int, now: float, bot: Bot | None) -> bool:
        """Возвращает True, если пользователь был автоматически забанен."""
        dq = self._violations[user_id]
        self._cleanup(dq, now, self.violation_memory_seconds)
        dq.append(now)

        if len(dq) < self.ban_after_violations or self.sessionmaker is None:
            return False

        async with self.sessionmaker() as session:
            from db.models import User

            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            if user is None or user.is_banned:
                return bool(user and user.is_banned)

            user.is_banned = True
            user.ban_reason = "Автобан: повторяющийся спам/флуд"
            user.banned_at = datetime.now(timezone.utc)
            await session.commit()

        logger.warning("antispam: пользователь %s автоматически забанен за повторяющийся спам", user_id)
        dq.clear()

        if bot is not None:
            try:
                await bot.send_message(
                    user_id,
                    f"{ce(e.NO_ENTRY)} Ты автоматически заблокирован(а) за повторяющийся спам/флуд.",
                )
            except Exception:
                pass
            try:
                await bot.send_message(
                    self.owner_id,
                    f"{ce(e.WARNING)} Пользователь {user_id} автоматически забанен антиспамом "
                    f"(повторяющийся флуд).",
                )
            except Exception:
                pass
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        user_event = event.message or event.callback_query
        if user_event is None or user_event.from_user is None:
            return await handler(event, data)

        user_id = user_event.from_user.id
        if user_id == self.owner_id or data.get("is_admin"):
            return await handler(event, data)

        now = time.monotonic()
        bot = data.get("bot")

        muted_until = self._muted_until.get(user_id)
        if muted_until and now < muted_until:
            if event.callback_query:
                await event.callback_query.answer("Слишком быстро! Подожди немного.", show_alert=False)
            logger.info("antispam: %s замьючен ещё на %.1fс, апдейт проигнорирован", user_id, muted_until - now)
            return

        last_ts = self._last_event.get(user_id)
        if last_ts is not None and now - last_ts < self.soft_interval:
            logger.info(
                "antispam: %s — апдейт проигнорирован (soft_interval), прошло %.3fс с предыдущего",
                user_id, now - last_ts,
            )
            return
        self._last_event[user_id] = now

        # burst-окно — быстрая очередь событий
        burst_dq = self._events[user_id]
        self._cleanup(burst_dq, now, self.hard_window)
        burst_dq.append(now)

        # sustained-окно — размеренный, но настойчивый спам с "хорошей регулярностью",
        # который burst-порог не задевает ни разу
        sustained_dq = self._sustained_events[user_id]
        self._cleanup(sustained_dq, now, self.sustained_window)
        sustained_dq.append(now)

        if len(burst_dq) > self.hard_limit:
            self._muted_until[user_id] = now + self.mute_seconds
            burst_dq.clear()
            banned = await self._register_violation_and_maybe_ban(user_id, now, bot)
            if not banned:
                text = (
                    f"{ce(e.WARNING)} Слишком много действий подряд. "
                    f"Подожди {int(self.mute_seconds)} секунд и продолжай — мы никуда не торопимся {ce(e.OK_HAND)}"
                )
                if event.message:
                    await event.message.answer(text, parse_mode="HTML")
                elif event.callback_query:
                    await event.callback_query.answer("Слишком быстро, притормози немного", show_alert=True)
            return

        if len(sustained_dq) > self.sustained_limit:
            self._muted_until[user_id] = now + self.sustained_mute_seconds
            sustained_dq.clear()
            banned = await self._register_violation_and_maybe_ban(user_id, now, bot)
            if not banned:
                text = (
                    f"{ce(e.WARNING)} Замечена подозрительно высокая активность. "
                    f"Подожди {int(self.sustained_mute_seconds)} секунд, прежде чем продолжить {ce(e.OK_HAND)}"
                )
                if event.message:
                    await event.message.answer(text, parse_mode="HTML")
                elif event.callback_query:
                    await event.callback_query.answer("Слишком быстро, притормози немного", show_alert=True)
            return

        return await handler(event, data)
