from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Cooldown
from app.utils.time import ensure_utc, utcnow


@dataclass(frozen=True)
class CooldownState:
    ready: bool
    seconds_left: int


class CooldownService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, action: str) -> CooldownState:
        now = utcnow()
        row = await self.session.get(Cooldown, {"user_id": user_id, "action": action})
        available_at = ensure_utc(row.available_at) if row else None
        if row is None or available_at is None or available_at <= now:
            return CooldownState(ready=True, seconds_left=0)
        return CooldownState(
            ready=False,
            seconds_left=int((available_at - now).total_seconds()),
        )

    async def set(self, user_id: int, action: str, seconds: int) -> None:
        available_at = utcnow() + timedelta(seconds=max(0, int(seconds)))
        row = await self.session.get(Cooldown, {"user_id": user_id, "action": action})
        if row is None:
            row = Cooldown(user_id=user_id, action=action, available_at=available_at)
            self.session.add(row)
        else:
            row.available_at = available_at
        await self.session.flush()
