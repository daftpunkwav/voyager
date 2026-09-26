"""The plan capability (the human REST surface of the plan review gate):
action dispatch over the shared plan-gate operations — status / write /
enter / exit — with the human exit closing the gate directly.

Test type: integration (registered capability over a built app).
"""

from __future__ import annotations

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError

USER = ActorContext(actor=LOCAL_USER)


def _app(tmp_path):
    return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())


async def _plan(app, **args):
    return await execute(app.registry, "plan", USER, {"session_id": "s1", **args})


class TestPlanCapability:
    async def test_status_reports_inactive_gate_with_empty_draft(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            out = await _plan(app, action="status")
            assert out == {"session_id": "s1", "plan_mode": False, "draft": ""}
        finally:
            app.memory.close()

    async def test_enter_turns_the_gate_on(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            out = await _plan(app, action="enter")
            assert out == {"session_id": "s1", "plan_mode": True}
            # the gate is per session: another session's gate stays off
            other = await execute(
                app.registry, "plan", USER, {"session_id": "s2", "action": "status"}
            )
            assert other["plan_mode"] is False
        finally:
            app.memory.close()

    async def test_write_stores_and_replaces_the_draft(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            out = await _plan(app, action="write", plan="  # step one  ")
            assert out == {"session_id": "s1", "stored_chars": len("# step one")}
            await _plan(app, action="write", plan="# step one\n# step two")
            status = await _plan(app, action="status")
            assert status["draft"] == "# step one\n# step two"
            assert status["plan_mode"] is False  # writing alone never opens the gate
        finally:
            app.memory.close()

    async def test_write_with_empty_plan_rejected(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await _plan(app, action="write", plan="   ")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        finally:
            app.memory.close()

    async def test_human_exit_closes_the_gate_directly(self, tmp_path) -> None:
        """The capability exit is the human path: no review round-trip, the
        gate simply closes (the agent's own exit goes through plan_submit)."""
        app = _app(tmp_path)
        try:
            await _plan(app, action="enter")
            out = await _plan(app, action="exit")
            assert out == {"session_id": "s1", "plan_mode": False}
            assert await _plan(app, action="status") == {
                "session_id": "s1",
                "plan_mode": False,
                "draft": "",
            }
        finally:
            app.memory.close()

    async def test_unknown_action_rejected(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await _plan(app, action="approve")
            assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
            assert "status/write/enter/exit" in exc.value.body.hint
        finally:
            app.memory.close()

    async def test_sessions_have_independent_gates(self, tmp_path) -> None:
        app = _app(tmp_path)
        try:
            await execute(app.registry, "plan", USER, {"session_id": "a", "action": "enter"})
            await execute(
                app.registry, "plan", USER, {"session_id": "b", "action": "write", "plan": "x"}
            )
            a = await execute(app.registry, "plan", USER, {"session_id": "a", "action": "status"})
            b = await execute(app.registry, "plan", USER, {"session_id": "b", "action": "status"})
            assert a["plan_mode"] is True and a["draft"] == ""
            assert b["plan_mode"] is False and b["draft"] == "x"
        finally:
            app.memory.close()
