"""report_page_context capability: the frontend provider pushes a page
summary.

Human-only by direction (UI -> agent context feed); see the parity exception
list.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="report_page_context",
        description="Page report: the frontend provider pushes a page summary",
    )
    def report_page_context(
        page: str, summary: str, counts: dict | None = None, selected: str = ""
    ) -> dict:
        item = deps.pages.update(page, summary, counts=counts, selected=selected)
        return {"page": item.page, "ok": True}
