"""Page awareness: the frontend provider reports summaries; the agent
fetches full text on demand.

Lets the floating window / chat stay aware of what the user is doing: page type, item counts,
visible item titles, current selection -- not full domain data (the server-side list returns
summaries by default; full bodies are fetched via capabilities on demand).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageSummary:
    page: str
    summary: str  # e.g. "36 notes, one document open, cursor at paragraph 3"
    counts: dict[str, int] = field(default_factory=dict)
    selected: str = ""
    ts: float = field(default_factory=time.time)


class PageContextRegistry:
    def __init__(self) -> None:
        self._pages: dict[str, PageSummary] = {}
        self._current: str = ""

    def update(
        self,
        page: str,
        summary: str,
        *,
        counts: dict[str, int] | None = None,
        selected: str = "",
    ) -> PageSummary:
        item = PageSummary(page=page, summary=summary, counts=counts or {}, selected=selected)
        self._pages[page] = item
        self._current = page
        return item

    def current(self) -> PageSummary | None:
        return self._pages.get(self._current) if self._current else None

    def render(self) -> str:
        cur = self.current()
        if cur is None:
            return "(用户当前页面未知)"
        counts = ",".join(f"{k}={v}" for k, v in cur.counts.items())
        base = f"用户正在【{cur.page}】页:{cur.summary}"
        if counts:
            base += f"({counts})"
        if cur.selected:
            base += f";当前选中: {cur.selected}"
        return base
