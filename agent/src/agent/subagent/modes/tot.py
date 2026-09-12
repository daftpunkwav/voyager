"""TOT: three candidate branches, then select the best."""

from __future__ import annotations

from typing import Any

from agent.llm import LLMClient
from agent.subagent.modes.base import Mode, StepCb
from agent.subagent.modes.branching import branch
from agent.subagent.modes.registry import register_mode


async def run_tot(llm: LLMClient, messages: list[dict[str, Any]], on_step: StepCb) -> str:
    return await branch(llm, messages, on_step, branches=3, joint=False)


__all__ = ["run_tot"]

register_mode(
    Mode.TOT,
    lambda **kw: run_tot(kw["llm"], kw["messages"], kw["on_step"]),
)
