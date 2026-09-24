"""Execution deadlines: wall-clock caps for one tool call and one ReAct round.

Timeouts already exist per tool (AgentTool.timeout_s) and per transport; this
module adds the harness-level backstop for calls that declare none, so a hung
subprocess/MCP session cannot pin a turn forever. On expiry the call is
cancelled and a structured timeout result is fed back (and surfaced as
ToolFailed through the normal outcome path) — the turn continues or winds
down, nothing hangs.

Deadlines never import the loop guards; settings are hot-read per use
(0 = off).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from platform_contracts import ServiceError

from agent.contracts import SettingsReader

TOOL_DEADLINE_KEY = "agent.execution.tool_deadline_s"
ROUND_DEADLINE_KEY = "agent.execution.round_deadline_s"

_DEFAULT_TOOL_S = 90.0
_DEFAULT_ROUND_S = 240.0

#: Self-bounded tools are exempt from the tool deadline: they carry their own
#: wait cap (ask_user: question_broker timeout; subagent wait: timeout_s with a
#: 600s ceiling), so the 90s tool cap would only amputate the wait mid-block
#: and report a forced interruption that never happened — the waited-on
#: subagent keeps running and completes after the fake cancel. The round
#: deadline still backstops the turn.
_INTERACTIVE_TOOLS = frozenset({"ask_user", "subagent"})


@dataclass(frozen=True)
class Deadline:
    tool_s: float = _DEFAULT_TOOL_S
    round_s: float = _DEFAULT_ROUND_S

    @classmethod
    def from_settings(cls, settings: SettingsReader) -> Deadline:
        def _s(key: str, fallback: float) -> float:
            try:
                value = float(settings.get(key))
            except (TypeError, ValueError, ServiceError):  # unregistered reads NOT_FOUND
                return fallback
            return value if value > 0 else 0.0

        return cls(
            tool_s=_s(TOOL_DEADLINE_KEY, _DEFAULT_TOOL_S),
            round_s=_s(ROUND_DEADLINE_KEY, _DEFAULT_ROUND_S),
        )

    async def run_tool(self, awaitable_factory, *, tool: str):
        """Await one tool execution under the tool cap; expiry returns a
        structured timeout outcome (ok=False) instead of raising."""
        if self.tool_s <= 0 or tool in _INTERACTIVE_TOOLS:
            return await awaitable_factory()
        try:
            return await asyncio.wait_for(awaitable_factory(), self.tool_s)
        except TimeoutError:
            return _TimeoutOutcome(tool=tool, cap=self.tool_s)

    async def run_round(self, awaitable_factory):
        """Await one completion round under the round cap; expiry returns a
        degraded final reply so the loop can wind down gracefully."""
        if self.round_s <= 0:
            return await awaitable_factory()
        try:
            return await asyncio.wait_for(awaitable_factory(), self.round_s)
        except TimeoutError:
            from agent.llm import LLMReply

            return LLMReply(
                text=f"[超时] 本回合在 {self.round_s:.0f}s 内未完成,已中断;请拆小任务后重试。",
                degraded=True,
            )


class _TimeoutOutcome:
    """Duck-typed ToolResult stand-in for an expired tool call (ok=False drives
    the ToolFailed lifecycle event; the text is model-actionable)."""

    def __init__(self, *, tool: str, cap: float) -> None:
        self.name = tool
        self.ok = False
        self.title = tool
        self.text = f"[超时] {tool} 在 {cap:.0f}s 内未完成,已被强制中断;请缩小输入或换实现方式"
        self.metadata: dict = {"timeout": True}

    def get(self, key: str, default=None):  # dict-like access kept off the hot path
        return getattr(self, key, default)


__all__ = ["ROUND_DEADLINE_KEY", "TOOL_DEADLINE_KEY", "Deadline"]
