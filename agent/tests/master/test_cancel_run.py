"""Closed-loop tests for agent.cancel_run: user and agent have equal standing
to abort a run.
"""

import asyncio

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime.state import RunStatus
from agent.subagent import Mode, TaskBook
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError


def _app(tmp_path, llm=None):
    return build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm or FakeLLM()
    )


class TestCancelRun:
    async def test_cancel_by_name_stops_running_task(self, tmp_path) -> None:
        class HangingLLM(FakeLLM):
            """Hangs inside complete to create a running window that can be aborted."""

            async def complete(self, *args, **kw):
                await asyncio.Event().wait()

        app = _app(tmp_path, HangingLLM())
        inst = app.spawner.spawn(TaskBook(goal="long task", mode=Mode.REACT), name="job")
        task = asyncio.create_task(app.spawner.start(inst))
        await asyncio.sleep(0.02)
        assert inst.status.alive

        out = await execute(
            app.registry, "cancel_run", ActorContext(actor=LOCAL_USER), {"id_or_name": "job"}
        )
        assert out["cancelled"] == [inst.id]
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert inst.state.status is RunStatus.CANCELLED

    async def test_cancel_unknown_404(self, tmp_path) -> None:
        app = _app(tmp_path)
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "cancel_run", ActorContext(actor=LOCAL_USER), {"id_or_name": "ghost"}
            )
        assert exc.value.body.code == "AGENT.NOT_FOUND"


class TestHardCancel:
    """Hard cancel (not via cancel_run): status must still land on a terminal state when shutdown or
    scheduler cleanup interrupts the task directly."""

    async def test_hard_cancel_marks_cancelled_and_emits(self, tmp_path) -> None:
        class HangingLLM(FakeLLM):
            async def complete(self, *args, **kw):
                await asyncio.Event().wait()

        app = _app(tmp_path, HangingLLM())
        events: list = []

        async def sink(type_: str, **payload) -> None:
            events.append((type_, payload))

        inst = app.spawner.spawn(TaskBook(goal="long task", mode=Mode.REACT), name="job2")
        inst.events = type("E", (), {"emit": staticmethod(sink)})()
        task = asyncio.create_task(app.spawner.start(inst))
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert inst.state.status is RunStatus.CANCELLED  # must not stay RUNNING
        assert any(t == "RunCancelled" for t, _ in events)

    async def test_cancelled_error_never_swallowed(self, tmp_path) -> None:
        """Cancellation errors must propagate upward so the scheduler cannot hang forever."""

        class HangingLLM(FakeLLM):
            async def complete(self, *args, **kw):
                raise asyncio.CancelledError

        app = _app(tmp_path, HangingLLM())
        inst = app.spawner.spawn(TaskBook(goal="x"), name="job3")
        task = asyncio.create_task(app.spawner.start(inst))
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert inst.state.status is RunStatus.CANCELLED
