from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.infra.cache import KeyedLockManager, TTLCache
from app.infra.membership import MembershipVerifier


@dataclass(slots=True)
class AppRuntime:
    content_cache: TTLCache[str, object]
    membership_cache: TTLCache[str, object]
    membership_verifier: MembershipVerifier
    user_action_locks: KeyedLockManager
    settings_snapshot: dict[str, dict[str, object]]


@lru_cache(1)
def get_runtime() -> AppRuntime:
    content_cache: TTLCache[str, object] = TTLCache(max_size=4096)
    membership_cache: TTLCache[str, object] = TTLCache(max_size=4096)
    membership_locks = KeyedLockManager()
    return AppRuntime(
        content_cache=content_cache,
        membership_cache=membership_cache,
        membership_verifier=MembershipVerifier(membership_cache, membership_locks),
        user_action_locks=KeyedLockManager(),
        settings_snapshot={},
    )
