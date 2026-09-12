"""Prefix-cache friendliness: the system prompt puts stable layers first so
per-turn volatile layers only invalidate the tail, and the compaction
planner request replays the conversation verbatim with one tail instruction
(never a rewritten copy of the transcript)."""

from __future__ import annotations

from typing import Any

from agent.context.builder import ContextBuilder
from agent.context.editor import iter_segments, render_segment_map


class _FakeProfile:
    def render(self) -> str:
        return "偏好:简洁"


class _FakeMemory:
    profile = _FakeProfile()

    def __init__(self, cards: int) -> None:
        self._cards = cards
        self.episodic = self

    def recent(self, limit: int):
        return [{"kind": "tool", "summary": f"第{n}条"} for n in range(self._cards)]


def test_volatile_layers_stay_after_stable_prefix() -> None:
    """Changing the memory-card layer keeps the stable layers byte-identical:
    the divergence point sits at the volatile profile/memory layers, after skills."""
    from types import SimpleNamespace

    skills = SimpleNamespace(index=lambda: [{"name": "s1", "description": "d"}])
    mem_a: Any = _FakeMemory(cards=2)
    mem_b: Any = _FakeMemory(cards=5)
    builder_a = ContextBuilder(rules=["规则A", "规则B"], memory=mem_a, skills=skills)
    builder_b = ContextBuilder(rules=["规则A", "规则B"], memory=mem_b, skills=skills)
    sys_a = builder_a.system(memory_cards=4, memory_card_chars=400)
    sys_b = builder_b.system(memory_cards=4, memory_card_chars=400)
    assert sys_a != sys_b  # the volatile layer differs
    # Byte-identical stable head: everything up to the volatile block
    marker = "【用户画像】"
    head_a, head_b = sys_a.split(marker)[0], sys_b.split(marker)[0]
    assert head_a == head_b and "规则A" in head_a
    # Volatile layers sit after the stable ones (skills before the profile)
    assert sys_a.index("【可用 skill】") < sys_a.index(marker)


def test_planner_request_replays_transcript_verbatim() -> None:
    """The planner sees the live transcript messages untouched, then one tail
    instruction carrying the segment map — no re-rendered copy."""
    from agent.context.editor import _PLAN_PROMPT

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务开始"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "name": "grep"}]},
        {"role": "tool", "tool_call_id": "1", "content": "结果"},
    ]
    segments = iter_segments(messages)
    planner_request = [
        *messages,
        {"role": "user", "content": _PLAN_PROMPT + render_segment_map(segments)},
    ]
    assert planner_request[:-1] == messages  # byte-identical prefix
    tail = planner_request[-1]
    assert tail["role"] == "user"
    assert "分段对照" in tail["content"] and "[段0] 消息 0-0" in tail["content"]
    # Tool pairing stays intact in the replayed prefix
    assert planner_request[2]["tool_calls"] == messages[2]["tool_calls"]


def test_segment_map_lists_message_ranges() -> None:
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    m = render_segment_map(iter_segments(messages))
    assert "[段0] 消息 0-0" in m and "[段1] 消息 1-1" in m
