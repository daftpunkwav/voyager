"""EpisodeRecorder: every executed tool call lands in episodic memory with
trigger / action / result, resolved from the executing instance."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.memory.episodic import EpisodicMemory
from agent.memory.recorder import EpisodeRecorder


class TestRecorder:
    async def test_tool_call_lands_in_episodic_with_run_context(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(tool_calls=(ToolCall("1", "glob", {"pattern": "*"}),)),
                    LLMReply(text="done"),
                ]
            ),
        )
        try:
            await app.master.handle_user_message("look around")
            await settle(app)
            rows = app.memory.episodic.recent(limit=5, kind="tool")
            assert rows and rows[0]["summary"] == "glob"
            detail = rows[0]["detail"]
            assert detail["action"] == {"tool": "glob", "target": '{"pattern": "*"}'}
            assert detail["ok"] is True and detail["result"]
            assert rows[0]["run_id"]  # bound to the chat instance's run
        finally:
            app.close()

    def test_truncates_and_never_raises(self, tmp_path) -> None:
        episodic = EpisodicMemory(tmp_path / "e.db")
        rec = EpisodeRecorder(episodic)
        rec.record_tool("write", {"path": "p" * 500, "content": "c"}, True, "x" * 5000)
        row = episodic.recent(limit=1)[0]
        assert len(row["detail"]["action"]["target"]) <= 200
        assert len(row["detail"]["result"]) <= 200
        episodic.close()
        rec.record_tool("read", {"path": "a"}, False, "boom")  # closed db: logged, not raised
