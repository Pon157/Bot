from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from redis.asyncio import Redis

from bot.utils import emoji as e
from bot.utils.emoji import ce


class AntiSpamMiddleware(BaseMiddleware):
    """
    Простой, но рабочий антифлуд на Redis с несколькими окнами:
      - "мягкий" троттлинг: не чаще, чем раз в `soft_interval` сек — на быстрые повторные нажатия/сообщения
        просто игнорируем событие без предупреждения (частая история с даблтапами по кнопкам)
      - "жёсткий" лимит: не более `hard_limit` событий за `hard_window` сек — при превышении временно
        выдаём мьют на `mute_seconds` и предупреждаем пользователя
    Владелец и админы не троттлятся вовсе (иначе рискуем мешать работе поддержки).
    """

    def __init__(
        self,
        redis: Redis,
        owner_id: int,
        soft_interval: float = 0.7,
        hard_limit: int = 12,
        hard_window: int = 10,
        mute_seconds: int = 15,
    ):
        self.redis = redis
        self.owner_id = owner_id
        self.soft_interval = soft_interval
        self.hard_limit = hard_limit
        self.hard_window = hard_window
        self.mute_seconds = mute_seconds

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
        if user_id == self.owner_id:
            return await handler(event, data)

        # админов не троттлим — определяем по флагу, положенному более ранней мидлварью,
        # если её ещё не было (порядок важен, см. registration в bot/main.py), считаем обычным юзером
        if data.get("is_admin"):
            return await handler(event, data)

        now = time.monotonic()
        mute_key = f"antispam:mute:{user_id}"
        if await self.redis.exists(mute_key):
            if event.callback_query:
                await event.callback_query.answer(
                    "Слишком быстро! Подожди немного.", show_alert=False
                )
            return  # просто глушим событие, не отвечая новым сообщением, чтобы не плодить спам в ответ на спам

        soft_key = f"antispam:soft:{user_id}"
        last_ts_raw = await self.redis.get(soft_key)
        if last_ts_raw is not None:
            last_ts = float(last_ts_raw)
            if now - last_ts < self.soft_interval:
                return  # тихо игнорируем — это защита от даблтапов, не наказание
        await self.redis.set(soft_key, now, ex=5)

        hard_key = f"antispam:hard:{user_id}"
        count = await self.redis.incr(hard_key)
        if count == 1:
            await self.redis.expire(hard_key, self.hard_window)

        if count > self.hard_limit:
            await self.redis.set(mute_key, "1", ex=self.mute_seconds)
            text = (
                f"{ce(e.WARNING)} Слишком много действий подряд. "
                f"Подожди {self.mute_seconds} секунд и продолжай — мы никуда не торопимся {ce(e.OK_HAND)}"
            )
            if event.message:
                await event.message.answer(text, parse_mode="HTML")
            elif event.callback_query:
                await event.callback_query.answer("Слишком быстро, притормози немного", show_alert=True)
            return

        return await handler(event, data)
