"""Approval memory: session/persistent grants shortcut the L2 dialog,
revocation works end to end, and the default stays ask-every-time."""

from __future__ import annotations

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.policy.approvals import ApprovalStore
from agent.tools import Toolbelt
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

USER_CTX = ActorContext(actor=LOCAL_USER)


def _belt(app, answers: list[str]) -> tuple[Toolbelt, list[str]]:
    asked: list[str] = []

    async def scoped(prompt: str, tool: str, target: str) -> str:
        asked.append(f"{tool}:{target}")
        return answers.pop(0) if answers else "deny"

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return (
        Toolbelt(
            dict(root._tools),
            root._policy,
            approvals=app.checkpoints and root.approvals_store,
            confirm_scoped=scoped,
        ),
        asked,
    )


class TestApprovalStore:
    def test_grant_lookup_and_revoke(self, tmp_path) -> None:
        store = ApprovalStore(tmp_path / "approvals.db")
        assert store.lookup("clear_memory", "profile") is None  # default: ask
        store.grant("clear_memory", "profile", "session")
        assert store.lookup("clear_memory", "profile") == "session"
        store.grant("run_shell", "pip install x", "always")
        assert store.lookup("run_shell", "pip install x") == "always"
        rows = store.list()
        assert {r["scope"] for r in rows} == {"session", "always"}
        assert store.revoke(tool="run_shell", target="pip install x") == 1
        assert store.lookup("run_shell", "pip install x") is None
        store.close()

    def test_persistent_grant_survives_reopen(self, tmp_path) -> None:
        store = ApprovalStore(tmp_path / "a.db")
        store.grant("uninstall_plugin", "old-plugin", "always")
        store.close()
        store = ApprovalStore(tmp_path / "a.db")
        assert store.lookup("uninstall_plugin", "old-plugin") == "always"
        store.close()

    def test_session_grant_is_memory_only(self, tmp_path) -> None:
        store = ApprovalStore(tmp_path / "a.db")
        store.grant("t", "g", "session")
        store.close()
        store = ApprovalStore(tmp_path / "a.db")
        assert store.lookup("t", "g") is None  # restart = new session
        store.close()


class TestScopedConfirm:
    async def test_always_allow_skips_future_dialogs(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            answers = ["always"]
            belt, asked = _belt(app, answers)
            app.memory.profile.set("k", "v")
            out1 = await belt.call(ToolCall("1", "clear_memory", {"zone": "profile"}))
            assert "cleared" in out1 and asked == ["clear_memory:clear_memory"]
            out2 = await belt.call(ToolCall("2", "clear_memory", {"zone": "profile"}))
            assert "cleared" in out2 and len(asked) == 1  # no second dialog
        finally:
            app.close()

    async def test_session_grant_then_revoke_capability(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            answers = ["session", "deny"]
            belt, asked = _belt(app, answers)
            out = await belt.call(ToolCall("1", "clear_memory", {"zone": "working"}))
            assert "cleared" in out  # session grant recorded from answer 1
            out = await belt.call(ToolCall("2", "clear_memory", {"zone": "working"}))
            assert "cleared" in out and len(asked) == 1  # remembered for the session
            # revoke via the capability, then the dialog is back (answer 2 = deny)
            revoke = await execute(
                app.registry, "revoke_approval", USER_CTX, {"tool": "clear_memory"}
            )
            assert revoke["revoked"] >= 1
            listed = await execute(app.registry, "list_approvals", USER_CTX, {})
            assert all(r["tool"] != "clear_memory" for r in listed)
            out = await belt.call(ToolCall("3", "clear_memory", {"zone": "working"}))
            assert out.startswith("[已取消]") and len(asked) == 2
        finally:
            app.close()

    async def test_agent_cannot_manage_approvals(self, tmp_path) -> None:
        from platform_contracts import ActorKind, ActorRef, ServiceError

        agent_ctx = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(app.registry, "revoke_approval", agent_ctx, {})
            assert exc.value.body.code == "AGENT.FORBIDDEN"
        finally:
            app.close()
