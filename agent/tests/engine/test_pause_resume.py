"""Supervision actions: cooperative pause at a step boundary -> AgentPaused +
persisted checkpoint -> resume -> completion (the phase-20 state machine)."""

from __future__ import annotations

import asyncio

import pytest
from agent.build import build_agent
from agent.capabilities.team.agent_instance import _resolve


def pause_run(spawner, chat, id_or_name):
    inst = _resolve(spawner, chat, id_or_name)
    if inst is None:
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no matching instance: {id_or_name}")
    if inst.status.value in ("completed", "failed", "cancelled"):
        from platform_contracts import ErrorSuffix, ServiceError

        raise ServiceError(
            "agent",
            ErrorSuffix.CONFLICT,
            f"instance {inst.name} is {inst.status.value}, cannot pause",
        )
    inst.pause_requested = True
    return {"pausing": inst.id, "name": inst.name, "status": "pause-requested"}


from agent.llm import LLMReply
from platform_contracts import RuntimeEvent


class PacedLLM:
    """Round 1 blocks until the test opens the gate, so the pause lands while
    the turn is genuinely mid-flight; round 2 finishes the task."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.stage = 0

    async def complete(self, messages, tools=None):
        self.stage += 1
        if self.stage == 1:
            await self.gate.wait()
            return LLMReply(text="round one done")
        return LLMReply(text="all done")


@pytest.fixture()
def app(tmp_path):
    llm = PacedLLM()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    app.llm_paced = llm
    try:
        yield app
    finally:
        llm.gate.set()
        app.close()


async def _wait(predicate, timeout_s: float = 10.0) -> bool:
    for _ in range(int(timeout_s / 0.05)):
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


class TestPauseResume:
    async def test_pause_then_resume_completes(self, app) -> None:
        dispatch = await app.master.dispatch_task("pausable job", name="pausable")

        # Round 1 is parked on the gate: ask for a pause mid-flight, then let
        # the round finish — the next step boundary honors the pause
        out = pause_run(app.spawner, app.master.chat, "pausable")
        assert out["pausing"] == dispatch.id
        app.llm_paced.gate.set()
        assert await _wait(lambda: inst_paused(app, dispatch.id))

        types = [e.type for _, e in app.log.read_after()]
        assert RuntimeEvent.AGENT_PAUSED in types

        # Continue the live paused instance in the background (the takeover /
        # continue path: same instance, same history; AgentResumed is emitted
        # because the run restarts from PAUSED)
        task = asyncio.create_task(app.spawner.start(inst_of(app, dispatch.id)))
        inst = app.spawner.instances[dispatch.id]
        assert await _wait(lambda: inst.status.value in ("completed", "failed"))
        await task
        assert inst.status.value == "completed"
        types = [e.type for _, e in app.log.read_after()]
        assert RuntimeEvent.AGENT_RESUMED in types

    async def test_pause_unknown_instance(self, app) -> None:
        from platform_contracts import ServiceError

        with pytest.raises(ServiceError):
            pause_run(app.spawner, app.master.chat, "ghost")


def inst_paused(app, instance_id: str) -> bool:
    inst = app.spawner.instances.get(instance_id)
    return inst is not None and inst.status.value == "paused"


def inst_of(app, instance_id: str):
    return app.spawner.instances[instance_id]
