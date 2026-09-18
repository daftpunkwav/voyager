"""Tests for background memory distillation: turn-count trigger with
hot interval, JSON extraction into profile/semantic, and silent skip on
malformed or degraded output.
"""

import json

from agent.llm import FakeLLM, LLMReply
from agent.memory import Memory
from agent.memory.distill import Distiller


def _settings(values: dict[str, int]):
    class _S:
        def get(self, key: str):
            return values.get(key)

    return _S()


def _memory(tmp_path) -> Memory:
    return Memory(tmp_path / "memory")


def _reply(payload: dict | str, *, degraded: bool = False) -> LLMReply:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return LLMReply(text=text, degraded=degraded)


async def test_interval_zero_never_triggers(tmp_path) -> None:
    memory = _memory(tmp_path)
    llm = FakeLLM()
    d = Distiller(llm=llm, memory=memory, settings=_settings({"agent.memory.distill_interval": 0}))
    for _ in range(10):
        assert d.maybe_distill() is None
    assert llm.calls == []


async def test_triggers_on_interval_and_writes_memories(tmp_path) -> None:
    memory = _memory(tmp_path)
    payload = {
        "profile": {"favorite_color": "蓝色"},
        "facts": [["用户", "works_on", "voyager 项目"], ["bad row"]],
    }
    d = Distiller(
        llm=FakeLLM(default=json.dumps(payload, ensure_ascii=False)),
        memory=memory,
        settings=_settings({"agent.memory.distill_interval": 2}),
    )
    memory.working.add("user", "我最喜欢蓝色,最近在做 voyager 项目")
    memory.working.add("assistant", "好的,记住了")
    memory.working.add("user", "第二句话")
    memory.working.add("assistant", "第三句回复")
    coro = d.maybe_distill()
    assert coro is None  # turn 1 of 2
    coro = d.maybe_distill()
    assert coro is not None  # turn 2 -> distillation point
    await coro
    assert memory.profile.get("favorite_color") == "蓝色"
    hits = memory.semantic.query(keyword="voyager")
    assert any(h["object"] == "voyager 项目" for h in hits)


async def test_malformed_json_skipped(tmp_path) -> None:
    memory = _memory(tmp_path)
    d = Distiller(
        llm=FakeLLM(default="这不是 JSON"),
        memory=memory,
        settings=_settings({"agent.memory.distill_interval": 1}),
    )
    for i in range(4):
        memory.working.add("user", f"消息{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro  # must not raise
    assert memory.profile.all() == {}


async def test_degraded_reply_skipped(tmp_path) -> None:
    memory = _memory(tmp_path)
    d = Distiller(
        llm=FakeLLM([_reply({}, degraded=True)]),
        memory=memory,
        settings=_settings({"agent.memory.distill_interval": 1}),
    )
    for i in range(4):
        memory.working.add("user", f"消息{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    assert memory.profile.all() == {}


async def test_cursor_never_re_distills_the_same_entries(tmp_path) -> None:
    """After one distillation, entries older than the cursor are excluded:
    a distill point with nothing new costs no LLM call, and the next real
    extraction renders only the fresh tail."""
    memory = _memory(tmp_path)
    payload = {"facts": [["用户", "works_on", "voyager"]]}
    llm = FakeLLM(default=json.dumps(payload, ensure_ascii=False))
    d = Distiller(llm=llm, memory=memory, settings=_settings({"agent.memory.distill_interval": 1}))
    for i in range(4):
        memory.working.add("user", f"旧消息{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    first_calls = len(llm.calls)
    assert first_calls == 1
    # distill point with no new entries: skipped before the LLM
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    assert len(llm.calls) == first_calls
    # new entries arrive: only they are rendered
    for i in range(4):
        memory.working.add("user", f"新消息{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    assert len(llm.calls) == first_calls + 1
    prompt = str(llm.calls[-1]["messages"][1]["content"])
    assert "新消息0" in prompt
    assert "旧消息0" not in prompt


async def test_failed_pass_keeps_the_cursor(tmp_path) -> None:
    """Malformed output writes nothing and does not advance the cursor, so the
    same entries are retried on the next distill point."""
    memory = _memory(tmp_path)
    llm = FakeLLM(default="这不是 JSON")
    d = Distiller(llm=llm, memory=memory, settings=_settings({"agent.memory.distill_interval": 1}))
    for i in range(4):
        memory.working.add("user", f"消息{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    # same entries again: still above _MIN_ENTRIES and still rendered
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    assert len(llm.calls) == 2
    prompt = str(llm.calls[-1]["messages"][1]["content"])
    assert "消息0" in prompt  # retried, not skipped by the cursor


async def test_exact_duplicate_fact_not_rewritten(tmp_path) -> None:
    """A repeated extraction of an identical triple does not insert a second
    row (write-side dedup)."""
    memory = _memory(tmp_path)
    payload = {"facts": [["用户", "works_on", "voyager"]]}
    d = Distiller(
        llm=FakeLLM(default=json.dumps(payload, ensure_ascii=False)),
        memory=memory,
        settings=_settings({"agent.memory.distill_interval": 1}),
    )
    for i in range(4):
        memory.working.add("user", f"第一批{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro
    for i in range(4):
        memory.working.add("user", f"第二批{i}")
    coro = d.maybe_distill()
    assert coro is not None
    await coro  # model repeats the same fact for the new window
    hits = memory.semantic.query(keyword="voyager")
    assert len(hits) == 1
