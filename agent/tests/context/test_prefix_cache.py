"""Prefix-cache friendliness: the system prompt is byte-stable across turns
and the per-turn volatile layers render into ONE trailing user-role row
appended after the full history, so the request prefix (system + history)
survives turn-to-turn; the compaction planner request replays the
conversation verbatim with one tail instruction (never a rewritten copy)."""

from __future__ import annotations

from typing import Any

from agent.context.builder import ContextBuilder
from agent.context.editor import iter_segments, render_segment_map


class _FakeProfile:
    def render(self, max_chars: int = 800) -> str:
        text = "偏好:简洁"
        return text if len(text) <= max_chars else text[:max_chars] + "…"


class _FakeMemory:
    profile = _FakeProfile()

    def __init__(self, cards: int) -> None:
        self._cards = cards
        self.episodic = self

    def recent(self, limit: int):
        return [{"kind": "tool", "summary": f"第{n}条"} for n in range(self._cards)]


def test_system_head_stable_and_volatile_in_tail_row() -> None:
    """Changing the memory-card layer leaves the system prompt byte-identical;
    the change lands in the turn-context block (rendered as one trailing
    user-role row) so the provider prefix cache keeps the whole history."""
    from types import SimpleNamespace

    skills = SimpleNamespace(index=lambda: [{"name": "s1", "description": "d"}])
    mem_a: Any = _FakeMemory(cards=2)
    mem_b: Any = _FakeMemory(cards=5)
    builder_a = ContextBuilder(rules=["规则A", "规则B"], memory=mem_a, skills=skills)
    builder_b = ContextBuilder(rules=["规则A", "规则B"], memory=mem_b, skills=skills)
    sys_a = builder_a.system()
    sys_b = builder_b.system()
    assert sys_a == sys_b  # the stable head carries no per-turn state at all
    ctx_a = builder_a.turn_context(memory_cards=4, memory_card_chars=400)
    ctx_b = builder_b.turn_context(memory_cards=4, memory_card_chars=400)
    assert ctx_a != ctx_b  # the volatile row carries the change
    assert "规则A" in sys_a and "【用户画像】" in sys_a
    assert "第0条" in ctx_b  # card content lives in the volatile row only
    assert "第0条" not in sys_b


def test_planner_request_replays_transcript_verbatim() -> None:
    """The planner sees the live transcript messages untouched, then one tail
    instruction carrying the segment map — no re-rendered copy."""
    from agent.prompts import P

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务开始"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "grep"}]},
        {"role": "tool", "tool_call_id": "1", "content": "结果"},
    ]
    segments = iter_segments(messages)
    planner_request = [
        *messages,
        {"role": "user", "content": P.context.editor_plan + render_segment_map(segments)},
    ]
    assert planner_request[:-1] == messages  # byte-identical prefix
    tail = planner_request[-1]
    assert tail["role"] == "user"
    assert "Segment map" in tail["content"] and "[seg 0] messages 0-0" in tail["content"]
    # Tool pairing stays intact in the replayed prefix
    assert planner_request[2]["tool_calls"] == messages[2]["tool_calls"]


def test_segment_map_lists_message_ranges() -> None:
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    m = render_segment_map(iter_segments(messages))
    assert "[seg 0] messages 0-0" in m and "[seg 1] messages 1-1" in m
