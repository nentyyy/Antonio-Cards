from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.domain.membership import MembershipCheckState, MembershipResult
from app.infra.cache import KeyedLockManager, TTLCache


class MembershipVerifier:
    _MEMBER_STATUSES = {"member", "administrator", "creator", "restricted"}
    _BOT_VISIBLE_STATUSES = {"member", "administrator", "creator", "restricted"}

    def __init__(
        self,
        cache: TTLCache[str, MembershipResult | int],
        locks: KeyedLockManager,
        *,
        request_timeout_seconds: float = 4.0,
        member_ttl_seconds: float = 120.0,
        bot_access_ttl_seconds: float = 300.0,
        me_ttl_seconds: float = 1800.0,
    ) -> None:
        self._cache = cache
        self._locks = locks
        self._request_timeout_seconds = request_timeout_seconds
        self._member_ttl_seconds = member_ttl_seconds
        self._bot_access_ttl_seconds = bot_access_ttl_seconds
        self._me_ttl_seconds = me_ttl_seconds

    async def verify_membership(self, bot: Bot, chat_ref: str | int, user_id: int) -> MembershipResult:
        bot_id = await self._get_bot_id(bot)
        bot_access = await self._get_chat_member(bot, chat_ref, bot_id, self._bot_access_ttl_seconds)
        if bot_access.state != MembershipCheckState.MEMBER:
            if bot_access.state in {MembershipCheckState.TIMEOUT, MembershipCheckState.ERROR}:
                return MembershipResult(
                    state=MembershipCheckState.BOT_NO_ACCESS,
                    detail="bot_access_unstable",
                )
            return MembershipResult(
                state=MembershipCheckState.BOT_NO_ACCESS,
                status=bot_access.status,
                detail=bot_access.detail,
            )
        if bot_access.status not in self._BOT_VISIBLE_STATUSES:
            return MembershipResult(
                state=MembershipCheckState.BOT_NO_ACCESS,
                status=bot_access.status,
                detail="bot_not_in_chat",
            )

        member = await self._get_chat_member(bot, chat_ref, user_id, self._member_ttl_seconds)
        if member.state != MembershipCheckState.MEMBER:
            return member
        if member.status in self._MEMBER_STATUSES:
            return member
        return MembershipResult(
            state=MembershipCheckState.NOT_MEMBER,
            status=member.status,
            detail=member.detail,
        )

    async def _get_bot_id(self, bot: Bot) -> int:
        cache_key = f"tg:me:{id(bot)}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, int):
            return cached

        async with self._locks.hold(cache_key):
            cached = self._cache.get(cache_key)
            if isinstance(cached, int):
                return cached
            async with asyncio.timeout(self._request_timeout_seconds):
                me = await bot.get_me()
            return self._cache.set(cache_key, int(me.id), self._me_ttl_seconds)

    async def _get_chat_member(
        self,
        bot: Bot,
        chat_ref: str | int,
        user_id: int,
        ttl_seconds: float,
    ) -> MembershipResult:
        cache_key = f"tg:member:{id(bot)}:{chat_ref}:{user_id}"
        cached = self._cache.get(cache_key)
        if isinstance(cached, MembershipResult):
            return cached

        async with self._locks.hold(cache_key):
            cached = self._cache.get(cache_key)
            if isinstance(cached, MembershipResult):
                return cached

            try:
                async with asyncio.timeout(self._request_timeout_seconds):
                    member = await bot.get_chat_member(chat_ref, user_id)
                result = MembershipResult(
                    state=MembershipCheckState.MEMBER,
                    status=getattr(member, "status", None),
                )
            except asyncio.TimeoutError:
                result = MembershipResult(
                    state=MembershipCheckState.TIMEOUT,
                    detail="timeout",
                )
            except TelegramForbiddenError:
                result = MembershipResult(
                    state=MembershipCheckState.BOT_NO_ACCESS,
                    detail="forbidden",
                )
            except TelegramBadRequest as exc:
                message = (exc.message or "").lower()
                if "chat not found" in message or "user not found" in message:
                    state = MembershipCheckState.CHAT_UNAVAILABLE
                else:
                    state = MembershipCheckState.ERROR
                result = MembershipResult(
                    state=state,
                    detail=exc.message,
                )
            except Exception as exc:
                result = MembershipResult(
                    state=MembershipCheckState.ERROR,
                    detail=str(exc),
                )

            self._cache.set(cache_key, result, ttl_seconds)
            return result
