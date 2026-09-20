"""The residual write_roots confirmation: writes into user-configured extra
directories still ask first (allow/deny per call — no approval memory since
the approvals system retired). Everything else executes directly."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.tools import Toolbelt
from platform_contracts import LOCAL_USER
from platform_settings import SettingsStore


def _belt(app, *, confirm=None) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _deny(_prompt: str) -> bool:
        return False

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return Toolbelt(
        dict(root._tools),
        root._policy,
        confirm=confirm or _yes,
        notify=_noop,
        permissions=root._permissions,
    )


async def _app_with_write_root(tmp_path):
    """App with one user-configured write root: writes there keep the confirm
    dialog (the sole surviving L2)."""
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


class TestWriteRootsConfirm:
    async def test_allow_then_deny(self, tmp_path) -> None:
        app, extra = await _app_with_write_root(tmp_path)
        try:
            target = extra / "note.txt"
            out = await _belt(app).call(
                ToolCall("1", "write", {"path": str(target), "content": "x"})
            )
            assert "written" in out and target.exists()
            out = await _belt(app, confirm=None).call(
                ToolCall("2", "write", {"path": str(target), "content": "y"})
            )
            # every call asks again: no approval memory shortcuts the dialog
            answers: list[str] = []

            async def _deny(_p: str) -> bool:
                answers.append("deny")
                return False

            belt = _belt(app, confirm=_deny)
            out = await belt.call(ToolCall("3", "write", {"path": str(target), "content": "z"}))
            assert out.startswith("[已取消]") and answers == ["deny"]
        finally:
            app.close()

    async def test_outside_write_roots_no_dialog(self, tmp_path) -> None:
        """Workspace writes and shell commands execute directly: the confirm
        channel is retired everywhere except write_roots."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            asked: list[str] = []

            async def _deny_bool(_p: str) -> bool:
                asked.append("asked")
                return False

            belt = _belt(app, confirm=_deny_bool)
            out = await belt.call(
                ToolCall("1", "write", {"path": "inside-workspace.txt", "content": "x"})
            )
            assert "written" in out and asked == []  # no dialog for workspace writes
            out = await belt.call(ToolCall("2", "bash", {"command": "definitely-not-a-real-cmd"}))
            # the command reaches the handler (handler-level failure text),
            # never a confirm branch rejection
            assert "[需确认]" not in out and "[已取消]" not in out
            assert asked == []
        finally:
            app.close()
