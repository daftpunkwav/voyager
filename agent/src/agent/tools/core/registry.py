"""Assembly-time tool registry: named sources merge into one roster.

Each contributor (a builtin tool group, the domain bridge, a test fixture)
registers as one named source; build() merges them in registration order with
later sources overwriting earlier ones on name clashes (the same rule the
previous dict.update chain had). origins() records which source supplied each
name, so roster introspection (which layer owns this tool) never depends on
name-prefix conventions.

Dynamic tools (external MCP approvals, spawn_subagent) keep registering
directly into Toolbelt after assembly; this registry covers the static
assembly-time roster only.
"""

from __future__ import annotations

from agent.contracts import ToolSource
from agent.tools.core.base import AgentTool


class StaticToolSource:
    """Trivial ToolSource adapter for an already-built tool dict."""

    def __init__(self, name: str, tools: dict[str, AgentTool]) -> None:
        if not name:
            raise ValueError("tool source name must not be empty")
        self._name = name
        self._tools = dict(tools)

    @property
    def source_name(self) -> str:
        return self._name

    def tools(self) -> dict[str, AgentTool]:
        return dict(self._tools)


class ToolRegistry:
    """Ordered set of tool sources with origin tracking."""

    def __init__(self) -> None:
        self._sources: list[ToolSource] = []

    def add(self, source: ToolSource) -> None:
        """Register one source; duplicate source names are rejected so an
        assembly bug (registering the same group twice) fails loudly."""
        name = source.source_name
        if not name:
            raise ValueError("tool source name must not be empty")
        if any(s.source_name == name for s in self._sources):
            raise ValueError(f"tool source already registered: {name}")
        self._sources.append(source)

    def source_names(self) -> tuple[str, ...]:
        return tuple(s.source_name for s in self._sources)

    def build(self) -> dict[str, AgentTool]:
        """Merge all sources in registration order; later sources win clashes."""
        merged: dict[str, AgentTool] = {}
        for source in self._sources:
            tools = source.tools()
            merged.update(tools)
        return merged

    def origins(self) -> dict[str, str]:
        """Tool name -> supplying source name (post-overwrite winner)."""
        won: dict[str, str] = {}
        for source in self._sources:
            for name in source.tools():
                won[name] = source.source_name
        return won


__all__ = ["StaticToolSource", "ToolRegistry"]
