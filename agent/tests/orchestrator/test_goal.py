"""Session goals: durable per-session state, the boot downgrade fence
(active never survives a restart unattended), the daily round budget,
the driver's admission checks before any continuation turn, and the goal
capability's action/scope matrix with its actor-based driver rules."""

from __future__ import annotations

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM
from agent.orchestrator.goal import ACTIVE, PAUSED, GoalManager
from agent.tools.core.self_capability import agent_context
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ErrorSuffix, ServiceError


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

            async def _notice(session, text, guard=None):
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

            async def _notice(session, text, guard=None):
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

            async def _notice(session, text, guard=None):
                seen.append(session)

            monkeypatch.setattr(app.master, "handle_notice", _notice)
            await app.master.goal_driver._run_goal_job({"session": "s1"})
            assert seen == []
        finally:
            app.close()

    async def test_prestep_guard_failure_is_fail_closed(self, tmp_path, monkeypatch) -> None:
        """A guard that explodes skips the wakeup (fail-closed): an
        unverifiable fence never runs the turn."""
        import asyncio

        app = _app(tmp_path)
        try:
            app.master.sessions.create(session_id="s1", title="t")
            started: list[str] = []

            async def _start(inst, text):
                started.append(text)

            monkeypatch.setattr(app.spawner, "start", _start)

            def _boom() -> bool:
                raise RuntimeError("guard exploded")

            await app.master.handle_notice("s1", "通知", guard=_boom)
            while app.master._bg:
                await asyncio.gather(*list(app.master._bg))
            assert started == []
        finally:
            app.close()

    async def test_prestep_guard_carries_active_check(self, tmp_path, monkeypatch) -> None:
        """The notice rides with a guard closure that re-verifies the goal is
        still ACTIVE when the turn would actually start (pre-step barrier)."""
        app = _app(tmp_path)
        try:
            from types import SimpleNamespace

            monkeypatch.setattr(
                app.master.goal_driver, "_settings", SimpleNamespace(get=lambda k: "")
            )
            goals = app.master.goal_driver._goals
            goals.create("s1", "keep going")
            received: dict[str, object] = {}

            async def _notice(session, text, guard=None):
                received["guard"] = guard

            monkeypatch.setattr(app.master, "handle_notice", _notice)
            await app.master.goal_driver._run_goal_job({"session": "s1"})
            guard = received["guard"]
            assert callable(guard) and guard() is True
            goals.set_status("s1", PAUSED)
            assert guard() is False  # a pause landing between admission and start cancels
        finally:
            app.close()


class TestGoalRearm:
    async def test_primary_user_turn_rearms_goal(self, tmp_path, monkeypatch) -> None:
        """An active goal is re-armed after a primary user turn, not only
        after queued drain turns - otherwise the continuation driver stays
        dormant on the common path."""
        import asyncio

        app = _app(tmp_path)
        try:
            goals = app.master.goal_driver._goals
            goals.create("s1", "ship it")
            armed: list[str] = []
            monkeypatch.setattr(
                app.master.goal_driver,
                "maybe_schedule",
                lambda session: armed.append(session),
            )
            await app.master.handle_user_message("推进一下", session_id="s1")
            while app.master._bg:
                await asyncio.gather(*list(app.master._bg))
            assert armed == ["s1"]
        finally:
            app.close()


class TestGoalCapabilityAndTools:
    async def test_goal_action_validates_action(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "goal",
                    agent_context(),
                    {"session_id": "s1", "action": "nope"},
                )
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.close()

    async def test_goal_create_then_agent_reports_done(self, tmp_path) -> None:
        """The human arms the goal (create); the agent's goal tool may only
        report done/blocked — status=active is refused by the driver rule."""

        app = _app(tmp_path)
        try:
            agent_ctx = ActorContext(
                actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=())
            )

            out = await execute(
                app.registry,
                "goal",
                ActorContext(actor=LOCAL_USER),
                {"session_id": "s1", "action": "create", "text": "ship it"},
            )
            assert out["main"]["status"] == ACTIVE

            # agent cannot arm/resume the main goal (driver rule 1)
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "goal",
                    agent_ctx,
                    {"session_id": "s1", "action": "status", "status": "active"},
                )
            assert exc.value.body.code.endswith(ErrorSuffix.FORBIDDEN.value)
            # agent reports done
            out = await execute(
                app.registry,
                "goal",
                agent_ctx,
                {"session_id": "s1", "action": "status", "status": "done"},
            )
            assert out["main"]["status"] == "done"
        finally:
            app.close()

    async def test_goal_get_reports_missing(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            out = await execute(
                app.registry,
                "goal",
                ActorContext(actor=LOCAL_USER),
                {"session_id": "nope", "action": "get"},
            )
            assert out["main"] is None and out["subs"] == []
        finally:
            app.close()


class TestGoalManagerEdges:
    def _goals(self, app) -> GoalManager:
        return GoalManager(app.session_store)

    def test_set_text_keeps_status_and_counter(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            goals.create("s1", "old text")
            goals.record_round("s1")
            updated = goals.set_text("s1", "new text")
            assert updated is not None
            assert updated.text == "new text"
            assert updated.status == ACTIVE and updated.rounds == 1
        finally:
            app.close()

    def test_set_text_on_missing_session_returns_none(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            assert goals.set_text("ghost", "x") is None
            assert goals.set_status("ghost", PAUSED) is None
            goals.record_round("ghost")  # quiet no-op
            assert goals.get("ghost") is None
        finally:
            app.close()

    def test_corrupt_meta_json_reads_as_missing(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            goals.create("s1", "text")
            app.session_store.set_meta("goal:s1", "{not json")
            assert goals.get("s1") is None
            app.session_store.set_meta("goal:sub:s1", "{broken")
            assert goals.subs("s1") == []
        finally:
            app.close()

    def test_missing_fields_fall_back_to_defaults(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            app.session_store.set_meta("goal:s1", '{"text": "t"}')
            goal = self._goals(app).get("s1")
            assert goal is not None
            assert goal.status == PAUSED and goal.rounds == 0 and goal.day == ""
        finally:
            app.close()

    def test_subs_roundtrip_and_non_list_payload(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            goals.set_subs("s1", [{"text": "a", "status": "pending"}])
            assert goals.subs("s1") == [{"text": "a", "status": "pending"}]
            app.session_store.set_meta("goal:sub:s1", '{"not": "a list"}')
            assert goals.subs("s1") == []
        finally:
            app.close()

    def test_active_sessions_and_corrupt_entries(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            goals.create("s1", "a")
            goals.create("s2", "b")
            goals.set_status("s2", PAUSED)
            assert goals.active_sessions() == ["s1"]
            app.session_store.set_meta("goal:s3", "{corrupt")
            assert goals.active_sessions() == ["s1"]  # corrupt entry skipped
        finally:
            app.close()

    def test_may_continue_requires_active_goal(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            assert goals.may_continue("ghost", max_rounds_per_day=2) is False
            goals.create("s1", "a")
            goals.set_status("s1", PAUSED)
            assert goals.may_continue("s1", max_rounds_per_day=2) is False
        finally:
            app.close()

    def test_round_counter_resets_on_a_new_day(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            goals = self._goals(app)
            goals.create("s1", "a")
            goals.record_round("s1")
            goals.record_round("s1")
            # simulate yesterday's counter still persisted
            app.session_store.set_meta(
                "goal:s1",
                '{"text": "a", "status": "active", "rounds": 2, "day": "2000-01-01"}',
            )
            assert goals.may_continue("s1", max_rounds_per_day=2) is True
            goals.record_round("s1")
            goal = goals.get("s1")
            assert goal is not None and goal.rounds == 1  # fresh day restarts at 1
        finally:
            app.close()

    def test_storeless_manager_degrades_to_memory(self) -> None:
        goals = GoalManager(None)
        assert goals.get("s1") is None
        assert goals.subs("s1") == []
        assert goals.active_sessions() == []
        goal = goals.create("s1", "text")  # returned, never persisted
        assert goal.text == "text" and goals.get("s1") is None
        goals.set_subs("s1", [])  # quiet no-op
        goals.clear("s1")


class TestGoalCapabilitySurface:
    """The goal capability's full action/scope matrix and the anti
    self-continuation driver rules applied by actor."""

    HUMAN = ActorContext(actor=LOCAL_USER)
    AGENT = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))

    def _app(self, tmp_path):
        return _app(tmp_path)

    async def _goal(self, app, ctx, **args):
        return await execute(app.registry, "goal", ctx, {"session_id": "s1", **args})

    async def test_human_creates_then_updates_main_text(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            out = await self._goal(app, self.HUMAN, action="create", text="  ship it  ")
            assert out["main"] == {"text": "ship it", "status": ACTIVE}
            # set on an existing goal replaces the text, keeping status
            await self._goal(app, self.HUMAN, action="status", status=PAUSED)
            out = await self._goal(app, self.HUMAN, action="set", scope="main", text="ship v2")
            assert out["main"] == {"text": "ship v2", "status": PAUSED}
        finally:
            app.close()

    async def test_create_with_empty_text_rejected(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await self._goal(app, self.HUMAN, action="create", text="   ")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.close()

    async def test_set_main_with_empty_text_clears_the_goal(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            await self._goal(app, self.HUMAN, action="create", text="temp")
            out = await self._goal(app, self.HUMAN, action="set", scope="main", text="")
            assert out["cleared"] is True and out["main"] is None
        finally:
            app.close()

    async def test_agent_cannot_touch_main_text_or_arm(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            await self._goal(app, self.HUMAN, action="create", text="theirs")
            for args in (
                {"action": "set", "scope": "main", "text": "mine"},
                {"action": "set", "scope": "main", "text": ""},
                {"action": "create", "text": "mine"},
                {"action": "status", "scope": "main", "status": "active"},
                {"action": "status", "scope": "main", "status": "paused"},
            ):
                with pytest.raises(ServiceError) as exc:
                    await self._goal(app, self.AGENT, **args)
                assert exc.value.body.code.endswith(ErrorSuffix.FORBIDDEN.value)
        finally:
            app.close()

    async def test_agent_reports_blocked_and_done(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            await self._goal(app, self.HUMAN, action="create", text="g")
            out = await self._goal(app, self.AGENT, action="status", status="blocked")
            assert out["main"]["status"] == "blocked"
        finally:
            app.close()

    async def test_human_status_validates_against_human_vocabulary(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            await self._goal(app, self.HUMAN, action="create", text="g")
            with pytest.raises(ServiceError) as exc:
                await self._goal(app, self.HUMAN, action="status", status="doing")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
            with pytest.raises(ServiceError) as exc:
                await self._goal(app, self.HUMAN, action="status", status="")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.close()

    async def test_status_on_missing_goal_not_found(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await self._goal(app, self.HUMAN, action="status", status="paused")
            assert exc.value.body.code.endswith(ErrorSuffix.NOT_FOUND.value)
        finally:
            app.close()

    async def test_sub_goals_full_agent_authority(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            # agent adds a sub goal (no index: append as pending)
            out = await self._goal(app, self.AGENT, action="set", scope="sub", text="step one")
            assert out["subs"] == [{"text": "step one", "status": "pending"}]
            # replace text via index: status preserved
            out = await self._goal(
                app, self.AGENT, action="set", scope="sub", index=0, text="step one revised"
            )
            assert out["subs"] == [{"text": "step one revised", "status": "pending"}]
            # sub status transitions
            out = await self._goal(
                app, self.AGENT, action="status", scope="sub", index=0, status="done"
            )
            assert out["subs"][0]["status"] == "done"
            # delete via empty text
            out = await self._goal(app, self.AGENT, action="set", scope="sub", index=0, text="")
            assert out["subs"] == []
        finally:
            app.close()

    async def test_sub_status_on_plain_string_entry_is_tolerated(self, tmp_path) -> None:
        """A legacy/plain-string sub entry gains an object shape on first
        status update instead of crashing."""
        app = self._app(tmp_path)
        try:
            GoalManager(app.session_store).set_subs("s1", ["raw step"])
            out = await self._goal(
                app, self.HUMAN, action="status", scope="sub", index=0, status="doing"
            )
            assert out["subs"] == [{"text": "raw step", "status": "doing"}]
        finally:
            app.close()

    async def test_sub_set_replaces_text_of_plain_string_entry(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            GoalManager(app.session_store).set_subs("s1", ["raw step"])
            out = await self._goal(
                app, self.HUMAN, action="set", scope="sub", index=0, text="typed step"
            )
            assert out["subs"] == [{"text": "typed step", "status": "pending"}]
        finally:
            app.close()

    async def test_sub_validation_errors(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            goals = GoalManager(app.session_store)
            goals.set_subs("s1", [{"text": "a", "status": "pending"}])
            cases = (
                {"action": "set", "scope": "sub", "index": None, "text": ""},  # empty append
                {"action": "set", "scope": "sub", "index": 5, "text": "x"},  # out of range
                {"action": "status", "scope": "sub", "index": None, "status": "done"},
                {"action": "status", "scope": "sub", "index": 0, "status": ""},
                {"action": "status", "scope": "sub", "index": 0, "status": "active"},
                {"action": "status", "scope": "sub", "index": 9, "status": "done"},
            )
            for args in cases:
                with pytest.raises(ServiceError) as exc:
                    await self._goal(app, self.HUMAN, **args)
                assert exc.value.body.code.endswith(
                    (ErrorSuffix.INVALID_INPUT.value, ErrorSuffix.NOT_FOUND.value)
                )
        finally:
            app.close()

    async def test_unknown_scope_and_action_rejected(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            for args in (
                {"action": "set", "scope": "other", "text": "x"},
                {"action": "status", "scope": "other", "status": "done"},
                {"action": "destroy"},
            ):
                with pytest.raises(ServiceError) as exc:
                    await self._goal(app, self.HUMAN, **args)
                assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.close()

    async def test_get_snapshot_reports_main_and_subs(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            goals = GoalManager(app.session_store)
            goals.create("s1", "main goal")
            goals.set_subs("s1", [{"text": "sub", "status": "doing"}])
            out = await self._goal(app, self.HUMAN, action="get")
            assert out["main"] == {"text": "main goal", "status": ACTIVE, "rounds": 0}
            assert out["subs"] == [{"text": "sub", "status": "doing"}]
        finally:
            app.close()
