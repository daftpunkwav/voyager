"""Task board: the publish/claim/confirm state machine, the capability
surface, and the delivery announcement (board stamp + agent.delivery event +
the standing host's relay turn)."""

import asyncio

import pytest
from agent.build import build_agent
from agent.capabilities.team.taskboard import taskboard_action
from agent.llm import FakeLLM, LLMReply
from agent.master.task_board import TaskBoard
from platform_capability import current_chat_session
from platform_contracts import DomainEvent, ServiceError


class TestBoardStateMachine:
    def test_full_lifecycle(self) -> None:
        board = TaskBoard()
        row = board.publish(
            title="讲 real-mock", brief="三句话讲解", session="s1", publisher="orchestrator"
        )
        tid = row["id"]
        assert row["status"] == "open"
        claimed = board.claim(tid, claimant="explainer", note="需要 README")
        assert claimed["status"] == "claimed" and claimed["claimant"] == "explainer"
        assert board.confirm(tid, publisher="orchestrator")["status"] == "assigned"
        assert board.mark_running(tid, run_id="r-1")["status"] == "running"
        done = board.finish(tid, ok=True, result="讲完了")
        assert done["status"] == "done" and done["result"] == "讲完了"

    def test_second_claim_conflicts(self) -> None:
        board = TaskBoard()
        tid = board.publish(title="t", brief="b", session="s", publisher="orchestrator")["id"]
        board.claim(tid, claimant="explainer")
        with pytest.raises(ServiceError):
            board.claim(tid, claimant="organizer")
        # refreshing one's own note is fine
        assert board.claim(tid, claimant="explainer", note="update")["claim_note"] == "update"

    def test_confirm_requires_publisher_and_claim(self) -> None:
        board = TaskBoard()
        tid = board.publish(title="t", brief="b", session="s", publisher="orchestrator")["id"]
        with pytest.raises(ServiceError):
            board.confirm(tid, publisher="recon")  # not the publisher
        with pytest.raises(ServiceError):
            board.confirm(tid, publisher="orchestrator")  # not claimed yet

    def test_reopen_drops_claim_and_terminal_is_final(self) -> None:
        board = TaskBoard()
        tid = board.publish(title="t", brief="b", session="s", publisher="orchestrator")["id"]
        board.claim(tid, claimant="explainer")
        assert board.reopen(tid)["status"] == "open"
        assert board.reopen(tid)["claimant"] is None
        board.finish(tid, ok=False, result="gone")
        with pytest.raises(ServiceError):
            board.reopen(tid)

    def test_unknown_task_and_session_filter(self) -> None:
        board = TaskBoard()
        with pytest.raises(ServiceError):
            board.get("nope")
        board.publish(title="a", brief="b", session="s1", publisher="orchestrator")
        board.publish(title="b", brief="b", session="s2", publisher="orchestrator")
        assert [r["session"] for r in board.list(session="s1")] == ["s1"]


def _deps_with_board(board, dispatch=None):
    from agent.capabilities.deps import CapabilityDeps

    return CapabilityDeps(
        settings=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
        skills=None,  # type: ignore[arg-type]
        spawner=None,  # type: ignore[arg-type]
        subagents=None,  # type: ignore[arg-type]
        pages=None,  # type: ignore[arg-type]
        asker=None,  # type: ignore[arg-type]
        toolbelt=None,
        mcp=None,
        meter=None,
        checkpoints=None,
        plugins=None,
        user_hooks=None,
        todos=None,
        sessions=None,
        jobs=None,
        job_cancel=None,
        blackboard=None,
        task_board=board,
        dispatch=dispatch,
    )


class TestTaskboardCapability:
    def test_claim_rejects_non_member(self) -> None:
        board = TaskBoard()
        tid = board.publish(title="t", brief="b", session="s", publisher="orchestrator")["id"]
        deps = _deps_with_board(board)
        with pytest.raises(ServiceError):
            asyncio.run(taskboard_action(deps, action="claim", task_id=tid, claimant="stranger"))

    def test_publish_requires_title_and_brief(self) -> None:
        deps = _deps_with_board(TaskBoard())
        with pytest.raises(ServiceError):
            asyncio.run(taskboard_action(deps, action="publish", title="only title"))

    def test_confirm_dispatches_and_stamps_run(self) -> None:
        board = TaskBoard()
        tid = board.publish(title="讲讲", brief="讲清楚", session="s1", publisher="orchestrator")[
            "id"
        ]
        board.claim(tid, claimant="explainer")

        dispatched: list[dict] = []

        class _State:
            run_id = "run-9"

        class _Inst:
            state = _State()

        async def _dispatch(goal, **kw):
            dispatched.append({"goal": goal, **kw})
            return _Inst()

        deps = _deps_with_board(board, dispatch=_dispatch)
        token = current_chat_session.set("s1")
        try:
            out = asyncio.run(taskboard_action(deps, action="confirm", task_id=tid))
        finally:
            current_chat_session.reset(token)
        assert dispatched[0]["persona"] == "explainer"
        assert dispatched[0]["board_task_id"] == tid
        result = out if isinstance(out, dict) else {}
        assert result["task"]["status"] == "running" and result["task"]["run_id"] == "run-9"

    def test_confirm_dispatch_failure_reopens_task(self) -> None:
        """A spawn that fails (depth cap, disabled persona) must not strand the
        row in assigned: the task goes back up so the claim can be re-made."""
        from platform_contracts import ErrorSuffix

        board = TaskBoard()
        tid = board.publish(title="t", brief="b", session="s1", publisher="orchestrator")["id"]
        board.claim(tid, claimant="explainer")

        async def _boom(goal, **kw):
            raise ServiceError("agent", ErrorSuffix.FORBIDDEN, "delegation depth exceeded")

        deps = _deps_with_board(board, dispatch=_boom)
        with pytest.raises(ServiceError):
            asyncio.run(taskboard_action(deps, action="confirm", task_id=tid))
        assert board.get(tid)["status"] == "open"
        assert board.get(tid)["claimant"] is None

    def test_list_scopes_to_current_session(self) -> None:
        board = TaskBoard()
        board.publish(title="a", brief="b", session="here", publisher="orchestrator")
        board.publish(title="b", brief="b", session="elsewhere", publisher="orchestrator")
        deps = _deps_with_board(board)
        token = current_chat_session.set("here")
        try:
            out = asyncio.run(taskboard_action(deps, action="list"))
        finally:
            current_chat_session.reset(token)
        listed = out if isinstance(out, dict) else {}
        assert [t["title"] for t in listed.get("tasks", [])] == ["a"]


class TestDeliveryAnnouncement:
    def _app(self, tmp_path, replies):
        return build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text=r) for r in replies]),
        )

    def _board_task(self, app, session="s-delivery"):
        assert app.master._task_board is not None
        return app.master._task_board.publish(
            title="讲 real-mock", brief="三句话", session=session, publisher="orchestrator"
        )

    async def _make_inst(self, app, session, task_id):
        from agent.policy import PolicyEngine
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState
        from agent.subagent import TaskBook
        from agent.subagent.instance import SubagentInstance
        from agent.tools import Toolbelt

        inst = SubagentInstance(
            task=TaskBook(goal="讲 real-mock", session=session, board_task_id=task_id),
            toolbelt=Toolbelt({}, PolicyEngine()),
            llm=app.master._llm,
            system_prompt="x",
            events=RuntimeEvents(app.bus),
            state=RunState("讲 real-mock"),
            persona="explainer",
            name="explainer-run",
        )
        return inst

    def test_delivery_event_board_stamp_and_host_relay(self, tmp_path) -> None:
        app = self._app(tmp_path, ["收到,Elio 交卷了,讲得很清楚。"])
        try:

            async def _scenario() -> None:
                await app.master.handle_user_message("开始测试", session_id="s-delivery")
                row = self._board_task(app)
                board_task_id = row["id"]
                inst = await self._make_inst(app, row["session"], board_task_id)
                await app.master.announce_delivery(
                    inst, ok=True, result="RealMock 是一个 AI 模拟面试平台。"
                )
                while app.master._bg:
                    await asyncio.gather(*list(app.master._bg))

            asyncio.run(_scenario())
            deliveries = [
                e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_DELIVERY])
            ]
            assert deliveries and deliveries[-1]["status"] == "done"
            assert deliveries[-1]["member"] == "explainer"
            assert "RealMock" in deliveries[-1]["content"]
            # the board row reached its terminal state
            row = app.master._task_board.get(deliveries[-1]["board_task_id"])
            assert row["status"] == "done"
            # the host relayed to the user as a normal group message
            messages = [e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]
            assert any("Elio" in (p.get("content") or "") for p in messages)
        finally:
            app.close()

    def test_failed_delivery_relays_failure(self, tmp_path) -> None:
        app = self._app(tmp_path, ["收到,失败了,我来说明。"])
        try:

            async def _scenario() -> None:
                row = self._board_task(app)
                inst = await self._make_inst(app, row["session"], row["id"])
                await app.master.announce_delivery(
                    inst, ok=False, result="", error="ValueError: bad input"
                )
                while app.master._bg:
                    await asyncio.gather(*list(app.master._bg))

            asyncio.run(_scenario())
            deliveries = [
                e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_DELIVERY])
            ]
            assert deliveries[-1]["status"] == "failed"
            assert "ValueError" in deliveries[-1]["error"]
            row = app.master._task_board.get(deliveries[-1]["board_task_id"])
            assert row["status"] == "failed"
        finally:
            app.close()
