"""Tests for the wait_subagent capability: immediate return for terminal
instances, polling to completion, the timeout path, and NOT_FOUND for
unknown ids. The spawner is duck-typed (only .instances is read), matching
the capability's real dependency surface."""

from types import SimpleNamespace
from typing import cast

import pytest
from agent.capabilities.team.subagent import _wait_subagent as wait_subagent
from agent.engine.spawn import Spawner
from agent.runtime.state import RunStatus
from platform_contracts import ServiceError


def _spawner_with(inst) -> Spawner:
    return cast(Spawner, SimpleNamespace(instances={inst.id: inst}))


def _inst(status: RunStatus, result: str = "", surrendered: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id="abc123",
        name="worker",
        status=status,
        state=SimpleNamespace(result=result, error="", surrender_reason=surrendered),
        last_step_summary=lambda: "step",
    )


async def test_unknown_id_raises_not_found() -> None:
    spawner = _spawner_with(_inst(RunStatus.COMPLETED))
    with pytest.raises(ServiceError) as exc:
        await wait_subagent(spawner, "nope")
    assert "NOT_FOUND" in exc.value.body.code


async def test_terminal_instance_returns_immediately() -> None:
    inst = _inst(RunStatus.COMPLETED, result="all done")
    out = await wait_subagent(_spawner_with(inst), "abc123")
    assert out == {
        "id": "abc123",
        "name": "worker",
        "status": "completed",
        "timed_out": False,
        "result": "all done",
        "error": "",
    }


async def test_paused_instance_returns_without_waiting() -> None:
    inst = _inst(RunStatus.PAUSED)
    out = await wait_subagent(_spawner_with(inst), "worker", timeout_s=5)
    assert out["status"] == "paused" and out["timed_out"] is False


async def test_polls_until_completion() -> None:
    import asyncio

    inst = _inst(RunStatus.RUNNING)

    async def _finish() -> None:
        await asyncio.sleep(0.05)
        inst.status = RunStatus.COMPLETED
        inst.state.result = "late result"

    finisher = asyncio.create_task(_finish())
    out = await wait_subagent(_spawner_with(inst), "abc123", timeout_s=5)
    await finisher
    assert out["status"] == "completed" and out["result"] == "late result"


async def test_timeout_returns_progress_snapshot() -> None:
    inst = _inst(RunStatus.RUNNING)
    out = await wait_subagent(_spawner_with(inst), "abc123", timeout_s=0.2)
    assert out["timed_out"] is True and out["status"] == "running"
    assert out["last_step"] == "step"


async def test_timeout_is_capped_and_malformed_falls_back(monkeypatch) -> None:
    """A huge timeout is capped and a malformed one falls back to the default;
    both shrink to 0.2s here so the cap/fallback logic is observable without
    literally waiting for the production ceilings."""
    import agent.capabilities.team.subagent as mod

    monkeypatch.setattr(mod, "_MAX_TIMEOUT_S", 0.2)
    monkeypatch.setattr(mod, "_DEFAULT_TIMEOUT_S", 0.2)
    inst = _inst(RunStatus.RUNNING)
    for bad in (10**9, "not-a-number"):
        out = await wait_subagent(_spawner_with(inst), "abc123", timeout_s=cast(float, bad))
        assert out["timed_out"] is True


async def test_cap_surrender_is_flagged_on_the_result() -> None:
    """A cap surrender returns COMPLETED normally; wait must surface the
    reason so a parent can tell the truncated run from a real completion."""
    inst = _inst(RunStatus.COMPLETED, result="[中断] 已达工具调用上限(5)", surrendered="tool_cap")
    out = await wait_subagent(_spawner_with(inst), "abc123")
    assert out["surrendered"] == "tool_cap"


async def test_plain_completion_has_no_surrender_key() -> None:
    inst = _inst(RunStatus.COMPLETED, result="all done")
    out = await wait_subagent(_spawner_with(inst), "abc123")
    assert "surrendered" not in out
