"""Real-model evaluation harness (opt-in): the same build_agent assembly and
task style as the offline scenarios, driven by a live OpenAI-compatible
endpoint instead of FakeLLM scripts.

Fully skipped unless the harness environment is provided:
    AGENT_EVAL_BASE_URL  OpenAI-compatible /chat/completions base URL
    AGENT_EVAL_API_KEY   endpoint API key (empty when the endpoint needs none)
    AGENT_EVAL_MODEL     model name

Run: AGENT_EVAL_BASE_URL=... AGENT_EVAL_MODEL=... uv run pytest
     agent/tests/eval/test_eval_real.py -v

The scenario matrix covers the agent's own capabilities: loop health
(smoke), tool use, memory recall (resident relevance layer + cross-turn
persistence), the composite execution modes (plan_execute / cot dispatches),
and prefix-cache health telemetry. Assertions stay behavioral and
model-agnostic (a step happened / the seeded fact is used / status counters
exist) - a wiring regression set, not a benchmark.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from agent.build import build_agent
from agent.llm_http import HttpLLM, HttpLlmConfig
from agent.runtime.state import RunStatus
from agent.subagent.instance import SubagentInstance
from platform_contracts import DomainEvent

_BASE_URL = os.environ.get("AGENT_EVAL_BASE_URL", "")
_API_KEY = os.environ.get("AGENT_EVAL_API_KEY", "")
_MODEL = os.environ.get("AGENT_EVAL_MODEL", "")

pytestmark = pytest.mark.skipif(
    not (_BASE_URL and _MODEL),
    reason="real-model eval is opt-in: set AGENT_EVAL_BASE_URL and AGENT_EVAL_MODEL",
)


def _llm() -> HttpLLM:
    return HttpLLM(HttpLlmConfig(base_url=_BASE_URL, api_key=_API_KEY, model=_MODEL))


async def _drive(app, text: str) -> str:
    """Send one message and drain the background turn; returns the final reply."""
    await app.master.handle_user_message(text)
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))
    replies = [
        e.payload.get("content", "")
        for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
    ]
    return replies[-1] if replies else ""


async def test_smoke_chitchat_completes(tmp_path) -> None:
    """One full conversational turn against the real endpoint: the loop
    starts, the reply is real text (not a harness degradation)."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        reply = await _drive(app, "用一句话回答:1+1 等于几?")
        assert reply.strip(), "no reply produced"
        assert not reply.startswith("[LLM error]")
    finally:
        app.memory.close()
        await llm.aclose()


async def test_smoke_tool_round_completes(tmp_path) -> None:
    """A tool task produces at least one tool step and a final reply."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        await _drive(
            app, "用 todowrite 工具(action=set)新建计划,一条待办事项,内容是“写周报”,状态 pending。"
        )
        steps = [
            e.payload.get("name", "") for _, e in app.log.read_after(types=[DomainEvent.AGENT_STEP])
        ]
        assert any("todowrite" in s for s in steps), f"no tool step in {steps}"
    finally:
        app.memory.close()
        await llm.aclose()


# -- scenario matrix -----------------------------------------------------------
#
# Each scenario pins one agent capability against the real endpoint with
# behavioral, model-agnostic assertions (never exact wording). They are opt-in
# by the same environment gate and meant as the pre-release regression set.


async def _wait_instance(inst: SubagentInstance) -> None:
    import asyncio

    from agent.runtime.state import RunStatus

    for _ in range(600):  # <= 2 minutes; the deadline watchdog backstops anyway
        if inst.status is not RunStatus.RUNNING:
            return
        await asyncio.sleep(0.2)


async def test_memory_recall_surfaces_seeded_fact(tmp_path) -> None:
    """A seeded semantic fact is used by the next conversational turn: the
    resident relevance layer makes it reachable without an explicit recall
    call, and the reply reflects it."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        app.memory.semantic.add("demo服务", "部署地址", "内网 192.168.7.7")
        reply = await _drive(app, "demo服务部署在哪个地址?只回答地址。")
        assert reply.strip()
        assert "192.168.7.7" in reply, f"seeded fact not used in reply: {reply[:200]}"
    finally:
        app.memory.close()
        await llm.aclose()


async def test_two_turn_memory_keeps_context(tmp_path) -> None:
    """A fact stated in turn 1 survives into turn 2's answer (cross-turn
    history persistence plus the memory channels)."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        await _drive(app, "记住:我的代号是 NightRider。")
        reply = await _drive(app, "我的代号是什么?只回答代号。")
        assert reply.strip()
        assert "nightrider" in reply.lower(), f"turn-1 fact lost: {reply[:200]}"
    finally:
        app.memory.close()
        await llm.aclose()


async def test_plan_execute_dispatch_completes(tmp_path) -> None:
    """A dispatched task with mode=plan_execute runs the composite plan
    machinery (plan step present) and completes with a real result."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        inst = await app.master.dispatch_task(
            "用一句话写一首关于秋天的短诗", mode="plan_execute", name="eval-poem"
        )
        assert isinstance(inst, SubagentInstance)  # no depends_on: never deferred
        await _wait_instance(inst)
        assert inst.status is RunStatus.COMPLETED, f"task ended {inst.status}: {inst.state.error}"
        assert inst.state.result and inst.state.result.strip()
        kinds = [(s.kind, s.name) for s in inst.state.steps]
        assert any(name == "plan" for _kind, name in kinds), f"no plan step: {kinds}"
    finally:
        app.memory.close()
        await llm.aclose()


async def test_cot_dispatch_completes_with_steps(tmp_path) -> None:
    """A dispatched cot task decomposes into steps and synthesizes an
    answer; step entries carry the cot phase names."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        inst = await app.master.dispatch_task(
            "用一句话说明为什么天空是蓝色的", mode="cot", name="eval-cot"
        )
        assert isinstance(inst, SubagentInstance)  # no depends_on: never deferred
        await _wait_instance(inst)
        assert inst.status is RunStatus.COMPLETED, f"task ended {inst.status}: {inst.state.error}"
        names = [s.name for s in inst.state.steps]
        assert any(n == "cot-plan" for n in names), f"no cot plan step: {names}"
        assert inst.state.result and inst.state.result.strip()
    finally:
        app.memory.close()
        await llm.aclose()


async def test_prefix_cache_health_visible_after_turns(tmp_path) -> None:
    """After a couple of conversational turns the prefix-cache sentinel has
    folded the rounds and context_status reports its health counters."""

    llm = _llm()
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        await _drive(app, "用一句话回答:天空为什么是蓝的?")
        await _drive(app, "再补充一句。")
        from agent.tools.core.self_capability import agent_context
        from platform_capability import execute

        status = await execute(app.registry, "context", agent_context(), {"action": "status"})
        cache = status.get("prefix_cache") or {}
        assert cache.get("turns", 0) >= 2, f"sentinel did not fold turns: {cache}"
        assert "warm_rounds" in cache and "cold_rounds" in cache
    finally:
        app.memory.close()
        await llm.aclose()
