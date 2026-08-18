from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None: ...


class InMemoryTTLCache:
    def __init__(self, max_entries: int = 512) -> None:
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


class RedisCache:
    def __init__(self, url: str, namespace: str = "housing-agent:v1") -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Install the redis extra to use RedisCache") from exc
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1.0)
        self.namespace = namespace
        self.fallback = InMemoryTTLCache()

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Any | None:
        try:
            value = self.client.get(self._key(key))
            return json.loads(value) if value is not None else self.fallback.get(key)
        except Exception:
            return self.fallback.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        self.fallback.set(key, value, ttl_seconds)
        try:
            self.client.setex(self._key(key), ttl_seconds, json.dumps(value, ensure_ascii=False, default=str))
        except Exception:
            return
