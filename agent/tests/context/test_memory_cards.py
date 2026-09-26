"""Resident memory-card layer: rendered from recent episodic rows within its
own count/character budget, counted by the context status."""

from __future__ import annotations

from agent.build import build_agent
from agent.context.budgets import budget_from_settings
from agent.context.builder import MEMORY_CARDS_HEADER, ContextBuilder, render_memory_cards
from agent.llm import FakeLLM, LLMReply
from agent.memory import Memory
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

USER_CTX = ActorContext(actor=LOCAL_USER)


class TestRenderMemoryCards:
    def test_newest_first_and_char_cap_drops_oldest(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m")
        for i in range(6):
            mem.episodic.log(
                "tool",
                f"tool{i}",
                {"action": {"tool": f"tool{i}", "target": f"t{i}"}, "result": "ok"},
            )
        text = render_memory_cards(mem, count=5, max_chars=10_000)
        lines = text.splitlines()
        assert len(lines) == 5 and lines[0].startswith("- [tool] tool5") and "tool0" not in text
        tight = render_memory_cards(mem, count=5, max_chars=60)
        assert 0 < len(tight.splitlines()) < 5 and "tool5" in tight
        assert render_memory_cards(mem, count=0, max_chars=100) == ""
        mem.close()

    def test_builder_layer_and_budget_keys(self, tmp_path) -> None:
        mem = Memory(tmp_path / "m")
        mem.episodic.log(
            "tool", "grep", {"action": {"tool": "grep", "target": "x"}, "result": "hit"}
        )
        builder = ContextBuilder(memory=mem)
        # Cards are a per-turn volatile layer: they render in the turn-context
        # block (engine.turn appends it as one trailing user row), never in the
        # stable system head
        with_cards = builder.turn_context(memory_cards=3, memory_card_chars=500)
        assert MEMORY_CARDS_HEADER in with_cards and "grep" in with_cards
        assert MEMORY_CARDS_HEADER not in builder.turn_context()
        assert MEMORY_CARDS_HEADER not in builder.system()
        mem.close()


class _S:
    def __init__(self, values: dict) -> None:
        self.values = values

    def get(self, key: str):
        return self.values.get(key)


class TestBudget:
    def test_zero_is_a_valid_off_value(self) -> None:
        b = budget_from_settings(
            _S({"agent.memory.context_cards": 0, "agent.memory.context_card_chars": 0})
        )
        assert b.memory_cards == 0 and b.memory_card_chars == 0
        b = budget_from_settings(_S({"agent.memory.context_cards": "bad"}))
        assert b.memory_cards == 5 and b.memory_card_chars == 600


class TestStatusShare:
    async def test_context_status_reports_card_tokens(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="ok")]),
        )
        try:
            app.memory.episodic.log(
                "tool", "grep", {"action": {"tool": "grep", "target": "x"}, "result": "hit"}
            )
            await app.master.handle_user_message("hello")
            await settle(app)
            from agent.runtime.state import RunStatus

            chat = app.master.chat
            assert chat is not None
            chat.state.status = RunStatus.WAITING_INPUT
            status = await execute(app.registry, "context", USER_CTX, {"action": "status"})
            assert status["memory_cards_tokens"] > 0
        finally:
            app.close()
