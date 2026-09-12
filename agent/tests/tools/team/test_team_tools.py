"""Team governance tools: same capabilities as the team page, driven by the
agent through the toolbelt (policy tier + audit)."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.subagent import Mode, TaskBook
from agent.tools import Toolbelt


def _belt(app, *, confirm=None) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return Toolbelt(dict(root._tools), root._policy, confirm=confirm or _yes, notify=_noop)


class TestTeamTools:
    async def test_register_then_list_then_cancel(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            out = await belt.call(
                ToolCall(
                    "1",
                    "register_subagent",
                    {"name": "scout", "description": "d", "mode": "direct", "readonly": True},
                )
            )
            assert '"scout"' in out
            listed = await belt.call(ToolCall("2", "list_subagents", {}))
            assert "scout" in listed
            inst = app.spawner.spawn(TaskBook(goal="g", mode=Mode.REACT), persona="recon", name="v")
            cancelled = await belt.call(ToolCall("3", "cancel_run", {"id_or_name": inst.id}))
            assert inst.id in cancelled
            missing = await belt.call(ToolCall("4", "cancel_run", {"id_or_name": "nope"}))
            assert missing.startswith("[工具失败]")
        finally:
            app.close()

    async def test_abandon_checkpoint_requires_confirmation(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            asked: list[str] = []

            async def _deny(prompt: str) -> bool:
                asked.append(prompt)
                return False

            belt = _belt(app, confirm=_deny)
            out = await belt.call(
                ToolCall("1", "abandon_resumable_checkpoint", {"run_id": "r-none"})
            )
            assert out.startswith("[已取消]") and asked
            listed = await belt.call(ToolCall("2", "list_resumable_checkpoints", {}))
            assert '"items"' in listed
        finally:
            app.close()
