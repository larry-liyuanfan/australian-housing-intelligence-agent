from __future__ import annotations

import threading
from collections import Counter, defaultdict


class Metrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._durations: defaultdict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def observe_ms(self, name: str, value: float) -> None:
        with self._lock:
            values = self._durations[name]
            values.append(value)
            if len(values) > 2000:
                del values[:1000]

    def render_prometheus(self) -> str:
        with self._lock:
            lines = ["# Housing Agent process-local metrics"]
            for name, value in sorted(self._counters.items()):
                lines.extend((f"# TYPE housing_agent_{name} counter", f"housing_agent_{name} {value}"))
            for name, values in sorted(self._durations.items()):
                if not values:
                    continue
                ordered = sorted(values)
                p50 = ordered[int(0.50 * (len(ordered) - 1))]
                p95 = ordered[int(0.95 * (len(ordered) - 1))]
                lines.extend((
                    f"# TYPE housing_agent_{name}_milliseconds gauge",
                    f'housing_agent_{name}_milliseconds{{quantile="0.50"}} {p50:.6f}',
                    f'housing_agent_{name}_milliseconds{{quantile="0.95"}} {p95:.6f}',
                ))
            return "\n".join(lines) + "\n"
