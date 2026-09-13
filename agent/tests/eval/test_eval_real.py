"""Real-model evaluation harness (opt-in): the same build_agent assembly and
task style as the offline scenarios, driven by a live OpenAI-compatible
endpoint instead of FakeLLM scripts.

Fully skipped unless the harness environment is provided:
    AGENT_EVAL_BASE_URL  OpenAI-compatible /chat/completions base URL
    AGENT_EVAL_API_KEY   endpoint API key (empty when the endpoint needs none)
    AGENT_EVAL_MODEL     model name

Run: AGENT_EVAL_BASE_URL=... AGENT_EVAL_MODEL=... uv run pytest
     agent/tests/eval/test_eval_real.py -v

Assertions stay behavioral and model-agnostic (turn completes, a tool step
happened / final text is non-empty) - this is a smoke harness for wiring and
loop health, not a benchmark.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from agent.build import build_agent
from agent.llm_http import HttpLLM, HttpLlmConfig
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
        await _drive(app, "用 todo_write 工具新建一个待办事项,内容是“写周报”,状态 pending。")
        steps = [
            e.payload.get("name", "") for _, e in app.log.read_after(types=[DomainEvent.AGENT_STEP])
        ]
        assert any("todo_write" in s for s in steps), f"no tool step in {steps}"
    finally:
        app.memory.close()
        await llm.aclose()
