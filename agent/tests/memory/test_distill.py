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
