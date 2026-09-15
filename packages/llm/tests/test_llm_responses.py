"""OpenAI Responses wire-format tests (api_format='responses').

All network egress is mocked via httpx.MockTransport; tests never touch the
network. Covers the complete capability, the streaming capability, the input
mapping (system -> instructions, tool_calls -> function_call, tool ->
function_call_output), reasoning_fields, and catalog validation.
"""

import json
from typing import Any

import httpx
import pytest
from llm import client as client_mod
from llm import stream as stream_mod
from llm.catalog import valid_format
from platform_actor import ActorContext
from platform_contracts import LOCAL_USER

_PROVIDER = {"id": "p1", "api_format": "responses", "base_url": "https://api.test/v1"}
USER_CTX = ActorContext(actor=LOCAL_USER)

_MESSAGES = [
    {"role": "system", "content": "You are Lucien."},
    {"role": "user", "content": "hi"},
]


def _patch(monkeypatch, handler) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        client_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(
        stream_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


def _sse(*objs: dict[str, Any] | str) -> str:
    return (
        "\n\n".join("data: " + json.dumps(o) if isinstance(o, dict) else "data: " + o for o in objs)
        + "\n\n"
    )


def _full_response() -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "model": "gpt-test",
        "output": [
            {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "pondering"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello"}],
            },
        ],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 4,
            "input_tokens_details": {"cached_tokens": 6},
        },
    }


class TestComplete:
    async def test_text_reasoning_usage(self, monkeypatch) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_full_response())

        _patch(monkeypatch, handler)
        out = await client_mod.complete(
            _PROVIDER,
            api_key="sk",
            model="gpt-test",
            messages=_MESSAGES,
            reasoning_effort="high",
        )
        # Request shape: /responses endpoint, system as instructions, effort
        assert seen["url"].endswith("/responses")
        assert seen["body"]["instructions"] == "You are Lucien."
        assert seen["body"]["input"][0] == {
            "role": "user",
            "content": [{"type": "input_text", "text": "hi"}],
        }
        assert seen["body"]["reasoning"] == {"effort": "high"}
        assert seen["body"]["max_output_tokens"] == 4096
        # Reasoning models reject temperature; store=False opts out of
        # provider-side retention
        assert "temperature" not in seen["body"]
        assert seen["body"]["store"] is False
        # Response parsing: reasoning stays off the answer text
        assert out.text == "Hello"
        assert out.reasoning == "pondering"
        assert out.input_tokens == 11
        assert out.output_tokens == 4
        assert out.cached_tokens == 6
        assert out.model == "gpt-test"

    async def test_function_call_parsed(self, monkeypatch) -> None:
        response = _full_response()
        response["output"] = [
            {
                "type": "function_call",
                "call_id": "call_9",
                "name": "echo_tool",
                "arguments": '{"x": 1}',
            }
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response)

        _patch(monkeypatch, handler)
        out = await client_mod.complete(
            _PROVIDER, api_key="sk", model="gpt-test", messages=_MESSAGES
        )
        assert out.text == ""
        assert out.tool_calls == ({"id": "call_9", "name": "echo_tool", "arguments": {"x": 1}},)

    async def test_history_tool_loop_mapping(self, monkeypatch) -> None:
        """assistant tool_calls -> function_call items; tool result ->
        function_call_output keyed by call_id."""
        seen: dict = {}
        history: list[dict[str, Any]] = [
            *_MESSAGES,
            {
                "role": "assistant",
                "tool_calls": [{"id": "call_9", "name": "echo_tool", "arguments": {"x": 1}}],
            },
            {"role": "tool", "tool_call_id": "call_9", "content": "ok"},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_full_response())

        _patch(monkeypatch, handler)
        await client_mod.complete(_PROVIDER, api_key="sk", model="gpt-test", messages=history)
        inp = seen["body"]["input"]
        assert {
            "type": "function_call",
            "call_id": "call_9",
            "name": "echo_tool",
            "arguments": '{"x": 1}',
        } in inp
        assert {"type": "function_call_output", "call_id": "call_9", "output": "ok"} in inp


class TestStream:
    async def test_deltas_and_completed_final(self, monkeypatch) -> None:
        sse = _sse(
            {"type": "response.output_text.delta", "delta": "Hel"},
            {"type": "response.output_text.delta", "delta": "lo"},
            {"type": "response.reasoning_summary_text.delta", "delta": "thin"},
            {"type": "response.reasoning_summary_text.delta", "delta": "king"},
            {"type": "response.completed", "response": _full_response()},
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = [
            c
            async for c in stream_mod.complete_stream(
                _PROVIDER,
                api_key="sk",
                model="gpt-test",
                messages=_MESSAGES,
                reasoning_effort="medium",
            )
        ]
        texts = [c["text"] for c in chunks if c["type"] == "text"]
        reasonings = [c["text"] for c in chunks if c["type"] == "reasoning"]
        assert texts == ["Hel", "lo"]
        assert reasonings == ["thin", "king"]
        final = chunks[-1]
        assert final["type"] == "final"
        assert final["text"] == "Hello"
        assert final["reasoning"] == "pondering"
        assert final["usage"]["input_tokens"] == 11
        assert final["usage"]["cached_tokens"] == 6

    async def test_missing_completed_falls_back_to_deltas(self, monkeypatch) -> None:
        sse = _sse(
            {"type": "response.output_text.delta", "delta": "partial"},
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = [
            c
            async for c in stream_mod.complete_stream(
                _PROVIDER, api_key="sk", model="gpt-test", messages=_MESSAGES
            )
        ]
        final = chunks[-1]
        assert final["text"] == "partial"


class TestTerminalEvents:
    async def test_incomplete_keeps_tool_calls(self, monkeypatch) -> None:
        """max_output_tokens truncation emits response.incomplete (never
        completed): the parser must still surface the function_call."""
        response = _full_response()
        response["status"] = "incomplete"
        response["output"] = [
            {"type": "function_call", "call_id": "c1", "name": "echo_tool", "arguments": '{"x"'},
        ]
        sse = _sse(
            {"type": "response.output_text.delta", "delta": "par"},
            {"type": "response.incomplete", "response": response},
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = [
            c
            async for c in stream_mod.complete_stream(
                _PROVIDER, api_key="sk", model="gpt-test", messages=_MESSAGES
            )
        ]
        final = chunks[-1]
        assert final["tool_calls"] == [
            {"id": "c1", "name": "echo_tool", "arguments": {}}
        ]  # truncated arguments degrade to {}
        assert final["usage"]["input_tokens"] == 11

    async def test_failed_raises_provider_error(self, monkeypatch) -> None:
        sse = _sse(
            {
                "type": "response.failed",
                "response": {"error": {"code": "content_policy", "message": "blocked"}},
            },
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ProviderError, match="blocked"):
            async for _ in stream_mod.complete_stream(
                _PROVIDER, api_key="sk", model="gpt-test", messages=_MESSAGES
            ):
                pass

    async def test_complete_failed_status_raises(self, monkeypatch) -> None:
        response = _full_response()
        response["status"] = "failed"
        response["error"] = {"code": "x", "message": "nope"}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=response)

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ProviderError, match="nope"):
            await client_mod.complete(_PROVIDER, api_key="sk", model="gpt-test", messages=_MESSAGES)


def test_valid_format_includes_responses() -> None:
    assert valid_format("responses")
    assert not valid_format("wat")
