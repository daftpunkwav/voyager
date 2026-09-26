"""Tests for the two-part context assembly: the byte-stable system head
(ContextBuilder.system) and the per-turn volatile block
(ContextBuilder.turn_context) — the prefix-cache contract."""

from agent.context import ContextBuilder, PageContextRegistry
from agent.engine import TaskBook
from agent.memory import Memory
from agent.personas import LUCIEN


class TestBuilder:
    def test_layer_order(self, tmp_path) -> None:
        memory = Memory(tmp_path)
        memory.profile.set("language", "Chinese")
        pages = PageContextRegistry()
        pages.update("notes", "36 notes")
        builder = ContextBuilder(rules=["honesty first"], memory=memory, pages=pages)
        system = builder.system(
            persona=LUCIEN,
            task=TaskBook(goal="organize the repo", constraints="read-only"),
            style="热心",
        )
        turn_ctx = builder.turn_context()
        order = [
            system.index("【全局规则】"),
            system.index("【人格】"),
            system.index("【风格】"),
            system.index("【用户画像】"),
            system.index("【任务书】"),
        ]
        assert order == sorted(order)  # stable head: rules -> persona -> style -> profile -> task
        assert "honesty first" in system and "organize the repo" in system and "read-only" in system
        # Volatile layers render in the turn-context block, never in the system
        # prompt: a per-turn change in message[0] would re-bill the whole history
        assert "36 notes" in turn_ctx and "【用户当前页面】" in turn_ctx
        assert "【用户当前页面】" not in system
        memory.close()

    def test_volatile_layers_live_in_turn_context(self, tmp_path) -> None:
        """Cards/recall/digests/pages move with the turn, the system head stays
        byte-identical when only they change — the prefix-cache contract."""
        memory = Memory(tmp_path)
        memory.profile.set("language", "Chinese")
        builder = ContextBuilder(rules=["honesty first"], memory=memory)
        system_a = builder.system(persona=LUCIEN, style="热心")
        ctx_a = builder.turn_context(memory_cards=3, memory_card_chars=400)
        memory.episodic.log("tool", "查了 graph", {"action": {"tool": "graph"}, "result": "ok"})
        system_b = builder.system(persona=LUCIEN, style="热心")
        ctx_b = builder.turn_context(memory_cards=3, memory_card_chars=400)
        assert system_a == system_b  # stable head untouched by card churn
        assert ctx_a != ctx_b  # the volatile row carries the change
        assert "【最近记忆】" in ctx_b
        memory.close()
