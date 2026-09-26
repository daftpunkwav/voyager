"""Mirror-parity contract between the two hand-mirrored OpenAI-compatible
chat SSE parsers.

``agent.llm_http.HttpLLM`` (standalone agent runs) and ``llm.stream``
(aggregate runs, chat format) are intentionally separate implementations —
the import-linter law forbids agent -> domain imports — but they parse the
same wire protocol and their observable semantics must not drift: the same
provider response must produce the same answer text, reasoning split,
tool-call recovery and usage figures on both paths. A behavior fix on one
side (e.g. the null tool-call index fix) has to land on the other; this test
locks that in by feeding identical SSE fixtures through both parsers and
comparing the normalized results.

Lives under packages/host/tests because the composition root's test area is
the one place allowed to import both agent and llm (see
host/tests/test_import_boundaries.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from agent.llm_http import HttpLLM, HttpLlmConfig
from llm import client as llm_client_mod
from llm import stream as llm_stream_mod

_CFG = HttpLlmConfig(base_url="http://fake/v1", api_key="k", model="m1")
_PROVIDER = {"id": "p1", "api_format": "chat", "base_url": "http://fake/v1"}
_MSGS: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]


def _sse(*objs: dict[str, Any] | str) -> str:
    """dict -> one SSE data line; str -> verbatim payload (the [DONE] marker)."""

    def _line(obj: dict[str, Any] | str) -> str:
        return "data: " + (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))

    return "\n\n".join(_line(o) for o in objs) + "\n\n"


def _handler(sse: str) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse)

    return handler


# ---- driver for the agent-side mirror (HttpLLM) ----


async def _run_agent(sse: str) -> list[Any]:
    client = HttpLLM(_CFG, transport=httpx.MockTransport(_handler(sse)))
    return [ev async for ev in client.complete_stream(_MSGS)]


# ---- driver for the llm-domain mirror (llm.stream) ----


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        llm_stream_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def _run_llm(monkeypatch: pytest.MonkeyPatch, sse: str) -> list[dict[str, Any]]:
    _patch_transport(monkeypatch, _handler(sse))
    return [
        c
        async for c in llm_stream_mod.complete_stream(
            _PROVIDER, api_key="sk", model="m1", messages=_MSGS
        )
    ]


# ---- normalization: both sides -> comparable semantics ----


@dataclass(frozen=True)
class Semantics:
    text: str
    reasoning: str
    tool_calls: tuple[tuple[str, Any], ...]
    usage: tuple[int, int, int]
    degraded: bool


def _agent_semantics(events: list[Any]) -> Semantics:
    # The final aggregate's text is the authoritative answer (the streamed
    # deltas are its echo-back); on the degraded path it carries the error.
    reasoning = "".join(e.reasoning_delta or "" for e in events if e.reasoning_delta)
    final = next(e.final for e in events if e.final is not None)
    return Semantics(
        text=str(final.text or ""),
        reasoning=reasoning,
        tool_calls=tuple((c.name, c.arguments) for c in final.tool_calls or ()),
        usage=(
            final.usage.input_tokens,
            final.usage.output_tokens,
            final.usage.cached_tokens,
        ),
        degraded=bool(final.degraded),
    )


def _llm_semantics(chunks: list[dict[str, Any]]) -> Semantics:
    text = "".join(c.get("text", "") for c in chunks if c.get("type") == "text")
    reasoning = "".join(c.get("text", "") for c in chunks if c.get("type") == "reasoning")
    final = next(c for c in chunks if c.get("type") == "final")
    usage = final.get("usage") or {}
    calls = tuple((c.get("name", ""), c.get("arguments")) for c in final.get("tool_calls") or ())
    return Semantics(
        text=text,
        reasoning=reasoning,
        tool_calls=calls,
        usage=(
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
            int(usage.get("cached_tokens") or 0),
        ),
        degraded=False,  # the llm domain raises typed errors instead of degrading
    )


# ---- parity scenarios: identical fixtures through both parsers ----


async def test_plain_text_and_usage_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    sse = _sse(
        {"choices": [{"delta": {"content": "Hel"}}]},
        {"choices": [{"delta": {"content": "lo"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 1},
            },
        },
        "[DONE]",
    )
    assert _agent_semantics(await _run_agent(sse)) == _llm_semantics(
        await _run_llm(monkeypatch, sse)
    )


async def test_inline_think_split_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A <think> block split across content deltas lands on the reasoning
    channel on both sides, never in the answer text."""
    sse = _sse(
        {"choices": [{"delta": {"content": "<thi"}}]},
        {"choices": [{"delta": {"content": "nk>deep</think>ans"}}]},
        "[DONE]",
    )
    assert _agent_semantics(await _run_agent(sse)) == _llm_semantics(
        await _run_llm(monkeypatch, sse)
    )


async def test_inline_tool_call_fallback_parity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inline <tool_call> markup converts when the wire field stayed empty;
    the answer text carries no markup residue on either side."""
    sse = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "content": '<tool_call>{"name": "get_weather", "arguments": {"city": "SF"}}</tool_call>'
                    }
                }
            ]
        },
        "[DONE]",
    )
    agent = _agent_semantics(await _run_agent(sse))
    llm = _llm_semantics(await _run_llm(monkeypatch, sse))
    assert agent == llm
    assert agent.tool_calls == (("get_weather", {"city": "SF"}),)
    assert agent.text == llm.text == ""


async def test_fragment_reassembly_with_null_index_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool-call fragments reassemble by index; a null index degrades to slot
    0 on both sides (the drift class this parity suite exists for)."""
    sse = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": None, "id": "c1", "function": {"name": "f", "arguments": ""}}
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": None, "function": {"arguments": '{"a": 1}'}}]}}
            ]
        },
        "[DONE]",
    )
    agent = _agent_semantics(await _run_agent(sse))
    llm = _llm_semantics(await _run_llm(monkeypatch, sse))
    assert agent.tool_calls == (("f", {"a": 1}),)
    assert agent == llm


async def test_midstream_error_frame_never_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """An error object inside an HTTP-200 stream must surface on both sides:
    the llm domain raises ProviderError, the standalone client folds it into
    a degraded final — never a truncated normal-looking completion."""
    sse = _sse(
        {"choices": [{"delta": {"content": "partial"}}]},
        {"error": {"code": "content_filter", "message": "blocked mid-stream"}},
    )
    agent_events = await _run_agent(sse)
    agent = _agent_semantics(agent_events)
    assert agent.degraded is True
    assert "blocked mid-stream" in (agent.text or "")
    with pytest.raises(llm_client_mod.ProviderError, match="blocked mid-stream"):
        await _run_llm(monkeypatch, sse)
