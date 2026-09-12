"""Working memory sees both sides of a turn: the assistant's reply is written
at turn end so distillation reads the exchange, not only the asks."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply


class TestWorkingMemoryAssistant:
    async def test_reply_written_after_turn(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="Sure, here is the plan.")]),
        )
        try:
            await app.master.handle_user_message("plan my week")
            await settle(app)
            roles = [m["role"] for m in app.memory.working.recent(10)]
            assert roles[-2:] == ["user", "assistant"]
            assert app.memory.working.recent(1)[0]["content"] == "Sure, here is the plan."
        finally:
            app.close()
