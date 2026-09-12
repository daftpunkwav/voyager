"""On-demand loader: indexes stay resident while full content loads on
demand.

Every load is recorded for auditing.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any


class OnDemandLoader:
    """Unified on-demand entry point for skill full text, memory recall, and page context."""

    #: Cap on load records: long-running processes keep only the most recent 200 entries
    _LOADS_CAP = 200

    def __init__(
        self,
        *,
        skills: Any = None,  # SkillLoader
        memory: Any = None,  # Memory
        pages: Any = None,  # PageContextRegistry
    ) -> None:
        self._skills = skills
        self._memory = memory
        self._pages = pages
        # Load records as (kind, key, ts); fixed-length deque evicts the oldest beyond the cap
        self.loads: deque[dict[str, Any]] = deque(maxlen=self._LOADS_CAP)

    def _record(self, kind: str, key: str) -> None:
        self.loads.append({"kind": kind, "key": key, "ts": time.time()})

    def skill_text(self, name: str) -> str:
        self._record("skill", name)
        if self._skills is None:
            return "[skill 体系未装配]"
        return self._skills.full_text(name)

    def recall(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        self._record("memory", query)
        if self._memory is None:
            return []
        return self._memory.recall(query, limit)

    def page_summary(self) -> str:
        self._record("page", "current")
        if self._pages is None:
            return "(页面感知未装配)"
        return self._pages.render()
