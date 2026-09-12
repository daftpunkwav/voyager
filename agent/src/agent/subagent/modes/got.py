"""GOT: two angles produced independently, then aggregated."""

from __future__ import annotations

from typing import Any

from agent.llm import LLMClient
from agent.subagent.modes.base import Mode, StepCb
from agent.subagent.modes.branching import branch
from agent.subagent.modes.registry import register_mode


async def run_got(llm: LLMClient, messages: list[dict[str, Any]], on_step: StepCb) -> str:
    return await branch(llm, messages, on_step, branches=2, joint=True)


__all__ = ["run_got"]

register_mode(
    Mode.GOT,
    lambda **kw: run_got(kw["llm"], kw["messages"], kw["on_step"]),
)
