"""Wiring for L1 policy notify events: the production Toolbelt carries a
notify callback that emits agent.policy.notify after a call.
"""

import asyncio

from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent


class TestPolicyNotify:
    async def test_l1_tool_call_emits_notify_event(self, tmp_path) -> None:
        """write inside the jail is L1_NOTIFY: invoke emits notify and the tool still runs;
        the event log must contain an agent.policy.notify whose message includes the tool name and target."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            (tmp_path / "ws" / "f.txt").write_text("x", encoding="utf-8")
            out = await app.spawner._toolbelt.call(
                ToolCall("1", "write", {"path": "g.txt", "content": "y"})
            )
            assert "written" in out  # L1 only notifies, never blocks; the tool runs as usual
            rows: list = []
            for _ in range(20):  # publish persists via to_thread; poll until the row lands
                rows = app.log.read_after(after_seq=0, types=("agent.policy.notify",))
                if rows:
                    break
                await asyncio.sleep(0.05)
            assert rows, "L1 调用后应至少有一条 agent.policy.notify"
            _seq, ev = rows[0]
            assert "write" in ev.payload["message"]
            assert "g.txt" in ev.payload["message"]
        finally:
            app.close()
