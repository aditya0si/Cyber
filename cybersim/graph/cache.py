"""LRU cache for live attack graphs (docs/10 §3.1).

Bounded simple LRU; cold-graph eviction is the extension seam for Neo4j (Phase 8+).
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from typing import Any


class LruCache:
    """Capacity-bound LRU keyed on `simulation_id`. Thread-safe."""

    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = capacity
        self._od: OrderedDict[str, Any] = OrderedDict()
        self._lock = RLock()

    def get_or_load(self, key: str, loader: Callable[[], Any]) -> Any:
        with self._lock:
            if key in self._od:
                self._od.move_to_end(key)
                return self._od[key]
            value = loader()
            self._od[key] = value
            self._od.move_to_end(key)
            self._evict_locked()
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._od[key] = value
            self._od.move_to_end(key)
            self._evict_locked()

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key not in self._od:
                return None
            self._od.move_to_end(key)
            return self._od[key]

    def drop(self, key: str) -> None:
        with self._lock:
            self._od.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._od.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._od)

    @property
    def capacity(self) -> int:
        return self._capacity

    def _evict_locked(self) -> None:
        while len(self._od) > self._capacity:
            self._od.popitem(last=False)


__all__ = ["LruCache"]
