"""Tests for the per-tool timeout: a handler overrunning its cap
fails the call immediately (no retries burn) while untouched tools keep the
default behavior.
"""

import asyncio

from agent.llm import ToolCall
from agent.policy import PolicyEngine
from agent.tools.core.base import AgentTool, Toolbelt


async def test_timeout_fails_call_without_retries() -> None:
    attempts: list[int] = []

    async def slow() -> str:
        attempts.append(1)
        await asyncio.sleep(1.0)
        return "done"

    belt = Toolbelt(
        {"slow": AgentTool(name="slow", description="s", handler=slow, timeout_s=0.05)},
        PolicyEngine(),
        retries=3,  # generous: a timeout must not be retried despite this
    )
    out = await belt.call(ToolCall("1", "slow", {}))
    assert "[工具失败]" in out and "Timeout" in out
    assert len(attempts) == 1  # exactly one handler attempt: fail fast by design


async def test_timeout_error_not_retried_for_writes() -> None:
    async def w() -> str:
        await asyncio.sleep(1.0)
        return "done"

    belt = Toolbelt(
        {
            "w": AgentTool(
                name="w",
                description="w",
                handler=w,
                write=True,
                timeout_s=0.05,
            )
        },
        PolicyEngine(),
    )
    out = await belt.call(ToolCall("1", "w", {}))
    assert "Timeout" in out


async def test_no_timeout_keeps_default_behavior() -> None:
    async def quick() -> str:
        return "ok"

    belt = Toolbelt(
        {"quick": AgentTool(name="quick", description="q", handler=quick)},
        PolicyEngine(),
    )
    assert await belt.call(ToolCall("1", "quick", {})) == "ok"
