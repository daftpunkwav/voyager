"""Closed-loop tests for agent.cancel_run: user and agent have equal standing
to abort a run.
"""

import asyncio
from typing import Any

import pytest
from agent.engine import Mode, TaskBook
from agent.llm import FakeLLM, LLMReply, ToolSpec
from agent.main import build_agent
from agent.runtime.state import RunStatus
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
            app.registry,
            "agent_instance",
            ActorContext(actor=LOCAL_USER),
            {"action": "cancel", "id_or_name": "job"},
        )
        assert out["cancelled"] == [inst.id]
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert inst.state.status is RunStatus.CANCELLED

    async def test_cancel_unknown_404(self, tmp_path) -> None:
        app = _app(tmp_path)
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "agent_instance",
                ActorContext(actor=LOCAL_USER),
                {"action": "cancel", "id_or_name": "ghost"},
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

    async def test_cancel_while_queued_in_scheduler_prevents_run(
        self, tmp_path, agent_replies, wait_until
    ) -> None:
        """The real queuing race: an instance parked INSIDE scheduler.run
        (waiting for a concurrency slot) is cancelled — when the slot opens,
        the deferred coroutine re-checks CANCELLED at the run_turn entry and
        never executes a round (it used to revive to RUNNING and run to
        completion)."""

        class GateLLM(FakeLLM):
            """Hangs the holder's round (slot stays busy); counts finished
            rounds so a revived queued instance cannot hide."""

            def __init__(self) -> None:
                super().__init__()
                self.rounds = 0
                self.gate = asyncio.Event()

            async def complete(
                self,
                messages: list[dict[str, Any]],
                tools: list[ToolSpec] | None = None,
                response_format: dict[str, Any] | None = None,
                max_tokens: int | None = None,
            ) -> LLMReply:
                head = str(messages[0].get("content") or "") if messages else ""
                if "hold the slot" in head:
                    await self.gate.wait()
                self.rounds += 1
                return await super().complete(messages, tools, response_format, max_tokens)

        llm = GateLLM()
        app = _app(tmp_path, llm)
        from platform_contracts import LOCAL_USER

        await app.settings.set("agent.subagents.max_concurrent", 1, LOCAL_USER)
        holder = await app.master.dispatch_task("hold the slot", name="holder")
        assert holder is not None
        queued = await app.master.dispatch_task("queued work", name="queuedjob")
        assert queued is not None
        out = await app.spawner.cancel("queuedjob")
        assert out == [queued.id]
        await app.spawner.cancel(holder.name)  # frees the slot
        await wait_until(
            lambda: any("[cancelled]" in r and "queuedjob" in r for r in agent_replies(app))
        )
        assert llm.rounds == 0  # the queued instance never executed a round
        assert queued.state.status is RunStatus.CANCELLED

    async def test_stopped_chat_revives_on_next_message(self, tmp_path) -> None:
        """A stopped conversation revives on the next message: CANCELLED is
        terminal for start(), so without the revive the session would swallow
        every later message silently (a FAILED instance revives implicitly;
        this is the CANCELLED counterpart). Task instances stay terminal."""
        from platform_contracts import DomainEvent

        app = _app(tmp_path)
        await app.master.handle_user_message("first")
        while app.master._bg:
            await asyncio.gather(*list(app.master._bg))
        chat = app.master.chat
        assert chat is not None
        chat.state.status = RunStatus.CANCELLED  # as a completed stop leaves it
        await app.master.handle_user_message("还在吗")
        while app.master._bg:
            await asyncio.gather(*list(app.master._bg))
        assert chat.state.status is RunStatus.WAITING_INPUT
        messages = [e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]
        assert messages and messages[-1].get("content")
        # a task instance is NOT revived by dispatch: start() keeps it terminal
        app.memory.close()


class TestCancelCascade:
    """Cancelling a target also stops its running descendants (spawn tree)."""

    async def test_cascade_stops_child_and_grandchild(self, tmp_path) -> None:
        app = _app(tmp_path)
        parent = app.spawner.spawn(TaskBook(goal="parent"), name="parent")
        child = app.spawner.spawn(TaskBook(goal="child"), name="child")
        child.parent_run_id = parent.id
        grandchild = app.spawner.spawn(TaskBook(goal="grandchild"), name="grand")
        grandchild.parent_run_id = child.id
        outsider = app.spawner.spawn(TaskBook(goal="unrelated"), name="other")
        # spawn alone leaves a pre-run status: mark the tree alive like a
        # running dispatch would
        for inst in (parent, child, grandchild, outsider):
            inst.state.status = RunStatus.RUNNING

        out = await execute(
            app.registry,
            "agent_instance",
            ActorContext(actor=LOCAL_USER),
            {"action": "cancel", "id_or_name": "parent"},
        )
        assert set(out["cancelled"]) == {parent.id, child.id, grandchild.id}
        assert parent.state.status is RunStatus.CANCELLED
        assert child.state.status is RunStatus.CANCELLED
        assert grandchild.state.status is RunStatus.CANCELLED
        assert outsider.state.status is RunStatus.RUNNING  # untouched

    async def test_cascade_does_not_loop_on_cycles(self, tmp_path) -> None:
        app = _app(tmp_path)
        a = app.spawner.spawn(TaskBook(goal="a"), name="a")
        b = app.spawner.spawn(TaskBook(goal="b"), name="b")
        a.parent_run_id = b.id  # stale cycle in the linkage must not hang cancel
        b.parent_run_id = a.id
        a.state.status = RunStatus.RUNNING
        b.state.status = RunStatus.RUNNING

        out = await execute(
            app.registry,
            "agent_instance",
            ActorContext(actor=LOCAL_USER),
            {"action": "cancel", "id_or_name": "a"},
        )
        assert set(out["cancelled"]) == {a.id, b.id}


class TestCancelNoticeAndPending:
    async def test_cancelled_dispatch_replies_cancelled(
        self, tmp_path, agent_replies, wait_until
    ) -> None:
        """A running background dispatch that gets cancelled tells the session
        [cancelled] via the dispatch wrapper's CancelledError path."""

        class HangingLLM(FakeLLM):
            async def complete(self, *args, **kw):
                await asyncio.Event().wait()

        app = _app(tmp_path, HangingLLM())
        await app.master.dispatch_task("long analysis", name="slowjob")
        await app.spawner.cancel("slowjob")
        await wait_until(
            lambda: any("[cancelled]" in r and "slowjob" in r for r in agent_replies(app))
        )
        app.memory.close()

    async def test_pending_child_cancelled_and_never_starts(self, tmp_path) -> None:
        """Cascade covers queued (PENDING) descendants; a cancelled-queued
        instance never enters its turn even when a slot frees up."""
        from agent.runtime.state import RunStatus as RS

        app = _app(tmp_path)
        parent = app.spawner.spawn(TaskBook(goal="p"), name="p")
        child = app.spawner.spawn(TaskBook(goal="c"), name="c")
        child.parent_run_id = parent.id
        parent.state.status = RS.RUNNING
        child.state.status = RS.PENDING  # queued, no slot yet

        out = await execute(
            app.registry,
            "agent_instance",
            ActorContext(actor=LOCAL_USER),
            {"action": "cancel", "id_or_name": "p"},
        )
        assert set(out["cancelled"]) == {parent.id, child.id}
        result = await app.spawner.start(child)  # slot "frees up"
        assert "[cancelled]" in result
        assert child.state.status is RS.CANCELLED

    async def test_parent_link_survives_snapshot_roundtrip(self, tmp_path) -> None:
        app = _app(tmp_path)
        inst = app.spawner.spawn(TaskBook(goal="x"), name="snap")
        inst.parent_run_id = "parent123"
        snap = inst.build_resume_snapshot()
        assert snap.parent_run_id == "parent123"
        restored = type(snap).from_dict(snap.to_dict())
        assert restored.parent_run_id == "parent123"
        # legacy snapshot without the key still loads (default "")
        legacy = dict(snap.to_dict())
        legacy.pop("parent_run_id")
        assert type(snap).from_dict(legacy).parent_run_id == ""
        assert inst.state.status is not None  # sanity: no accidental status change
