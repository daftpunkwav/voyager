"""Task-scoped shared blackboard: short structured notes subagents leave for
each other, relayed by the master (instances never talk directly).

Bounded by design: per-task card count and text length are capped, and the
whole board holds a bounded number of tasks. Writes are L1 (the tool side
declares write=True); reads are concurrent-safe.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX_TASKS = 20
_MAX_CARDS = 50
_MAX_TEXT = 500


class Blackboard:
    def __init__(self, *, max_tasks: int = _MAX_TASKS, max_cards: int = _MAX_CARDS) -> None:
        self._max_tasks = max_tasks
        self._max_cards = max_cards
        self._tasks: dict[str, deque[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def write(self, *, task: str, text: str, author: str) -> dict:
        """Append one note; the oldest task's board is evicted when the task
        cap is hit, the oldest card when a board is full."""
        task = (task or "").strip()[:80]
        if not task:
            return {"error": "[参数错误] task 不能为空"}
        body = str(text or "").strip()[:_MAX_TEXT]
        if not body:
            return {"error": "[参数错误] text 不能为空"}
        with self._lock:
            if task not in self._tasks:
                if len(self._tasks) >= self._max_tasks:
                    self._evict_oldest_locked()
                self._tasks[task] = deque(maxlen=self._max_cards)
            self._tasks[task].append({"author": author[:80], "text": body, "ts": time.time()})
            return {"task": task, "cards": len(self._tasks[task])}

    def read(self, *, task: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Newest-first cards of one task (empty task = every task's latest
        cards interleaved); bounded."""
        cap = max(1, min(int(limit), _MAX_CARDS))
        with self._lock:
            if task:
                stored = self._tasks.get(task)
                cards: list[dict[str, Any]] = list(stored) if stored else []
                return list(reversed(cards[-cap:]))
            merged: list[dict[str, Any]] = []
            for t, task_cards in self._tasks.items():
                for card in reversed(task_cards):
                    merged.append({"task": t, **card})
            merged.sort(key=lambda c: -c["ts"])
            return merged[:cap]

    def _evict_oldest_locked(self) -> None:
        oldest = next(iter(self._tasks), None)
        if oldest is not None:
            del self._tasks[oldest]

    def clear(self, *, task: str | None = None) -> int:
        with self._lock:
            if task:
                return len(self._tasks.pop(task, ()))
            n = sum(len(v) for v in self._tasks.values())
            self._tasks.clear()
            return n


__all__ = ["Blackboard"]
