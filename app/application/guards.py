from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.infra.runtime import get_runtime


@asynccontextmanager
async def user_action_guard(user_id: int, scope: str = "callback") -> AsyncIterator[None]:
    key = f"{scope}:{user_id}"
    async with get_runtime().user_action_locks.hold(key):
        yield
