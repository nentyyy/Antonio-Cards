from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, cooldown: float = 0.7) -> None:
        self.cooldown = cooldown
        self._last_seen: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)

        uid = event.from_user.id
        now = time.monotonic()
        if now - self._last_seen[uid] < self.cooldown:
            await event.answer("Too many requests. Please wait a moment.")
            return None
        self._last_seen[uid] = now
        return await handler(event, data)
