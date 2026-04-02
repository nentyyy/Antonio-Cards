from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _CacheItem(Generic[V]):
    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    def __init__(self, max_size: int = 2048) -> None:
        self._max_size = max_size
        self._items: dict[K, _CacheItem[V]] = {}

    def get(self, key: K) -> V | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: K, value: V, ttl_seconds: float) -> V:
        if len(self._items) >= self._max_size:
            self._evict_expired()
            if len(self._items) >= self._max_size:
                self._items.pop(next(iter(self._items)))
        self._items[key] = _CacheItem(value=value, expires_at=time.monotonic() + max(0.0, ttl_seconds))
        return value

    def delete(self, key: K) -> None:
        self._items.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        for key in list(self._items):
            if isinstance(key, str) and key.startswith(prefix):
                self._items.pop(key, None)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for key, item in list(self._items.items()):
            if item.expires_at <= now:
                self._items.pop(key, None)


class KeyedLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._refs: dict[str, int] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: str) -> Iterator[None]:
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
            self._refs[key] = self._refs.get(key, 0) + 1

        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            async with self._guard:
                refs = self._refs.get(key, 0) - 1
                if refs <= 0:
                    self._refs.pop(key, None)
                    if not lock.locked():
                        self._locks.pop(key, None)
                else:
                    self._refs[key] = refs
