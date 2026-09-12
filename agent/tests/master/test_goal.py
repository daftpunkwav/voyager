"""Session goals: durable per-session state, the boot downgrade fence
(active never survives a restart unattended), the daily round budget, and
the driver's admission checks before any continuation turn."""

from __future__ import annotations

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM
from agent.master.goal import ACTIVE, PAUSED, GoalManager
from agent.tools.core.self_capability import agent_context
from platform_capability import execute
from platform_contracts import ErrorSuffix, ServiceError


def _app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    return app


class TestGoalManager:
    def test_create_get_clear(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = GoalManager(app.session_store)
            goals.create("s1", "把周报写完")
            goal = goals.get("s1")
            assert goal is not None and goal.status == ACTIVE and goal.text == "把周报写完"
            goals.set_status("s1", PAUSED)
            paused = goals.get("s1")
            assert paused is not None and paused.status == PAUSED
            goals.clear("s1")
            assert goals.get("s1") is None
        finally:
            app.close()

    def test_boot_downgrade_never_auto_revives(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = GoalManager(app.session_store)
            goals.create("s1", "long running")
            assert goals.downgrade_active_to_paused() == 1
            paused = goals.get("s1")
            assert paused is not None and paused.status == PAUSED
            assert goals.downgrade_active_to_paused() == 0  # idempotent across boots
        finally:
            app.close()

    def test_daily_round_budget(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = GoalManager(app.session_store)
            goals.create("s1", "target")
            for _ in range(2):
                assert goals.may_continue("s1", max_rounds_per_day=2) is True
                goals.record_round("s1")
            assert goals.may_continue("s1", max_rounds_per_day=2) is False
        finally:
            app.close()


class TestGoalDriverFence:
    async def test_paused_goal_is_never_admitted(self, tmp_path, monkeypatch) -> None:
        app = _app(tmp_path)
        try:
            goals = app.master.goal_driver._goals
            goals.create("s1", "keep going")
            goals.set_status("s1", PAUSED)
            seen: list[str] = []

            async def _notice(session, text):
                seen.append(session)

            monkeypatch.setattr(app.master, "handle_notice", _notice)
            await app.master.goal_driver._run_goal_job({"session": "s1"})
            assert seen == []  # the fence refuses: no continuation turn
        finally:
            app.close()

    async def test_active_goal_admits_one_notice_turn(self, tmp_path, monkeypatch) -> None:
        app = _app(tmp_path)
        try:
            from types import SimpleNamespace

            # Neutral quiet hours so the fence result is deterministic
            monkeypatch.setattr(
                app.master.goal_driver, "_settings", SimpleNamespace(get=lambda k: "")
            )
            goals = app.master.goal_driver._goals
            goals.create("s1", "keep going")
            seen: list[str] = []

            async def _notice(session, text):
                seen.append(session)

            monkeypatch.setattr(app.master, "handle_notice", _notice)
            await app.master.goal_driver._run_goal_job({"session": "s1"})
            assert seen == ["s1"]
            assert goals.get("s1").rounds == 1  # the round is accounted
        finally:
            app.close()

    async def test_round_budget_exhausted_blocks_admission(self, tmp_path, monkeypatch) -> None:
        app = _app(tmp_path)
        try:
            goals = app.master.goal_driver._goals
            goals.create("s1", "keep going")
            for _ in range(2):
                goals.record_round("s1")  # MAX_ROUNDS_PER_DAY = 2
            seen: list[str] = []

            async def _notice(session, text):
                seen.append(session)

            monkeypatch.setattr(app.master, "handle_notice", _notice)
            await app.master.goal_driver._run_goal_job({"session": "s1"})
            assert seen == []
        finally:
            app.close()


class TestGoalCapabilityAndTools:
    async def test_goal_manage_validates_action(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "goal_manage",
                    agent_context(),
                    {"session_id": "s1", "action": "nope"},
                )
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.close()

    async def test_goal_manage_create_then_agent_reports_done(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            from agent.tools.plan import goal_tools

            out = await execute(
                app.registry,
                "goal_manage",
                agent_context(),
                {"session_id": "s1", "action": "create", "text": "ship it"},
            )
            assert out["status"] == ACTIVE

            tools = goal_tools(app.master.goal_driver._goals)
            bad = await tools["goal_write"].handler(status="active")
            assert "参数错误" in str(bad)  # create/resume stays human-side
            ok = await tools["goal_write"].handler(status="done", session_id="s1")
            assert "done" in str(ok)
        finally:
            app.close()

    async def test_goal_read_reports_missing(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            from agent.tools.plan import goal_tools

            tools = goal_tools(app.master.goal_driver._goals)
            out = await tools["goal_read"].handler(session_id="nope")
            assert "没有持久目标" in str(out)
        finally:
            app.close()
