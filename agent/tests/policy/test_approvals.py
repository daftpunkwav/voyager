"""Approval memory: session/persistent grants shortcut the write_roots
confirmation dialog (the one kept confirm), revocation works end to end,
and the default stays ask-every-time."""

from __future__ import annotations

import pytest
from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.policy.approvals import ApprovalStore
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.tools import Toolbelt
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER
from platform_settings import SettingsStore

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


async def _app_with_write_root(tmp_path):
    """App with one user-configured write root: writes there keep the confirm
    dialog (the sole surviving L2), everything else executes directly."""
    extra = tmp_path / "extra"
    extra.mkdir()
    settings = SettingsStore(tmp_path / "settings.db")
    settings.register_fresh(AGENT_SETTING_DEFS)
    await settings.set("agent.fs.write_roots", [str(extra)], LOCAL_USER)
    app = build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=FakeLLM(),
        settings_store=settings,
    )
    return app, extra


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
    """The residual confirmation: writes into user-configured write_roots.
    clear_memory / bash and the like no longer confirm at all (confirm
    retired) — only the write_roots branch reaches the dialog."""

    async def test_always_allow_skips_future_dialogs(self, tmp_path) -> None:
        app, extra = await _app_with_write_root(tmp_path)
        try:
            answers = ["always"]
            belt, asked = _belt(app, answers)
            target = extra / "note.txt"
            out1 = await belt.call(ToolCall("1", "write", {"path": str(target), "content": "x"}))
            assert "written" in out1 and asked == [f"write:{target}"]
            out2 = await belt.call(ToolCall("2", "write", {"path": str(target), "content": "y"}))
            assert "written" in out2 and len(asked) == 1  # remembered grant, no second dialog
        finally:
            app.close()

    async def test_session_grant_then_revoke_capability(self, tmp_path) -> None:
        app, extra = await _app_with_write_root(tmp_path)
        try:
            answers = ["session", "deny"]
            belt, asked = _belt(app, answers)
            target = extra / "note.txt"
            out = await belt.call(ToolCall("1", "write", {"path": str(target), "content": "a"}))
            assert "written" in out  # session grant recorded from answer 1
            out = await belt.call(ToolCall("2", "write", {"path": str(target), "content": "b"}))
            assert "written" in out and len(asked) == 1  # remembered for the session
            # revoke via the capability, then the dialog is back (answer 2 = deny)
            revoke = await execute(
                app.registry, "revoke_approval", USER_CTX, {"tool": "write", "target": str(target)}
            )
            assert revoke["revoked"] >= 1
            listed = await execute(app.registry, "list_approvals", USER_CTX, {})
            assert all(r["tool"] != "write" for r in listed)
            out = await belt.call(ToolCall("3", "write", {"path": str(target), "content": "c"}))
            assert out.startswith("[已取消]") and len(asked) == 2
        finally:
            app.close()

    async def test_outside_write_roots_no_dialog(self, tmp_path) -> None:
        """Workspace writes and shell commands execute directly: the confirm
        channel is retired everywhere except write_roots."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            answers: list[str] = []
            belt, asked = _belt(app, answers)
            out = await belt.call(
                ToolCall("1", "write", {"path": "inside-workspace.txt", "content": "x"})
            )
            assert "written" in out and asked == []  # no dialog for workspace writes
            out = await belt.call(ToolCall("2", "bash", {"command": "definitely-not-a-real-cmd"}))
            # The command reaches the handler (handler-level failure text),
            # never a confirm branch rejection
            assert "[需确认]" not in out and "[已取消]" not in out
            assert asked == []
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
