"""Team governance tools: same capabilities as the team page, driven by the
agent through the toolbelt (policy tier + audit). The four aggregated tools
(subagent / agent_instance / board / goal) replace the twelve single tools."""

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
                    "subagent",
                    {
                        "action": "register",
                        "name": "scout",
                        "description": "d",
                        "mode": "direct",
                        "readonly": True,
                    },
                )
            )
            assert '"scout"' in out
            listed = await belt.call(ToolCall("2", "subagent", {"action": "list"}))
            assert "scout" in listed
            inst = app.spawner.spawn(TaskBook(goal="g", mode=Mode.REACT), persona="recon", name="v")
            cancelled = await belt.call(
                ToolCall("3", "agent_instance", {"action": "cancel", "id_or_name": inst.id})
            )
            assert inst.id in cancelled
            missing = await belt.call(
                ToolCall("4", "agent_instance", {"action": "cancel", "id_or_name": "nope"})
            )
            assert missing.startswith("[工具失败]")
        finally:
            app.close()

    async def test_abandon_checkpoint_executes_without_confirm(self, tmp_path) -> None:
        """Confirm retired: the destructive abandon reaches the handler (its
        unknown-run error), never a confirm branch."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            asked: list[str] = []

            async def _deny(prompt: str) -> bool:
                asked.append(prompt)
                return False

            belt = _belt(app, confirm=_deny)
            out = await belt.call(
                ToolCall("1", "agent_instance", {"action": "abandon", "run_id": "r-none"})
            )
            assert "[已取消]" not in out and "[需确认]" not in out
            assert asked == []
            listed = await belt.call(ToolCall("2", "agent_instance", {"action": "checkpoints"}))
            assert '"items"' in listed
        finally:
            app.close()
