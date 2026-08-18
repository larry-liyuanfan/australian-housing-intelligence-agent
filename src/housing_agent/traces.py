from __future__ import annotations

import threading
from collections import OrderedDict

from .schemas import TraceRecord


class TraceStore:
    def __init__(self, limit: int = 1000) -> None:
        self.limit = limit
        self._items: OrderedDict[str, TraceRecord] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, trace: TraceRecord) -> None:
        with self._lock:
            self._items[trace.trace_id] = trace.model_copy(deep=True)
            self._items.move_to_end(trace.trace_id)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def get(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            trace = self._items.get(trace_id)
            return trace.model_copy(deep=True) if trace else None
