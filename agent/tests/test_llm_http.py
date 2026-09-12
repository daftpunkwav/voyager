"""Tests for the standalone OpenAI-compatible client: wire-format
translation, reply parsing, streaming aggregation, and the overflow
degradation path (all against httpx.MockTransport - no network).
"""

import json
from typing import Any

import httpx
from agent.llm_http import HttpLLM, HttpLlmConfig, _is_context_overflow, _messages_to_wire

CFG = HttpLlmConfig(base_url="http://fake/v1", api_key="k", model="m1")
MSGS = [{"role": "user", "content": "hi"}]


def _client(handler) -> HttpLLM:
    return HttpLLM(CFG, transport=httpx.MockTransport(handler))


class TestWire:
    def test_assistant_tool_calls_arguments_become_json_strings(self) -> None:
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "t", "arguments": {"a": 1}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "t", "content": "r"},
        ]
        wire = _messages_to_wire(msgs)
        assert wire[1]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
        assert wire[2] == {"role": "tool", "content": "r"}


class TestComplete:
    async def test_reply_text_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == "m1" and body["stream"] is False
            assert request.url.path == "/v1/chat/completions"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok", "tool_calls": None}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                },
            )

        reply = await _client(handler).complete(MSGS)
        assert reply.text == "ok" and reply.final
        assert (reply.usage.input_tokens, reply.usage.output_tokens) == (3, 5)

    async def test_tool_calls_arguments_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "function": {"name": "t", "arguments": '{"a": 2}'},
                                    },
                                ],
                            }
                        }
                    ],
                },
            )

        reply = await _client(handler).complete(MSGS)
        assert reply.final is False
        call = reply.tool_calls[0]
        assert (call.id, call.name, call.arguments) == ("c1", "t", {"a": 2})

    async def test_http_error_degrades_readable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and "authentication" in (reply.text or "")

    async def test_context_overflow_marked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error": {"message": "This model's maximum context length is exceeded"},
                },
            )

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and reply.overflow is True


class TestStream:
    async def test_deltas_aggregate_to_final(self) -> None:
        def sse(text: dict | str) -> bytes:
            return f"data: {json.dumps(text)}\n\n".encode()

        def handler(request: httpx.Request) -> httpx.Response:
            chunks = [
                {"choices": [{"delta": {"content": "你"}}]},
                {"choices": [{"delta": {"content": "好"}}]},
                {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}},
                "DONE",
            ]
            body = b"".join(sse(c) if isinstance(c, dict) else b"data: [DONE]\n\n" for c in chunks)
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

        llm = _client(handler)
        deltas: list[str] = []
        final = None
        async for ev in llm.complete_stream(MSGS):
            if ev.final is not None:
                final = ev.final
            else:
                deltas.append(ev.text_delta)
        assert deltas == ["你", "好"]
        assert final is not None and final.text == "你好"
        assert final.usage.output_tokens == 2

    async def test_stream_tool_fragments_merge(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            chunks = [
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "c1",
                                        "function": {"name": "too", "arguments": '{"a"'},
                                    },
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "function": {"arguments": ": 1}"}},
                                ]
                            }
                        }
                    ]
                },
                "DONE",
            ]
            body = b"".join(
                f"data: {json.dumps(c)}\n\n".encode()
                if isinstance(c, dict)
                else b"data: [DONE]\n\n"
                for c in chunks
            )
            return httpx.Response(200, content=body)

        final = None
        async for ev in _client(handler).complete_stream(MSGS):
            if ev.final is not None:
                final = ev.final
        assert final is not None
        assert final.tool_calls[0].name == "too"  # split name reassembled
        assert final.tool_calls[0].arguments == {"a": 1}

    async def test_stream_options_400_retries_without(self) -> None:
        attempts: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            attempts.append(body)
            if "stream_options" in body:
                return httpx.Response(400, json={"error": {"message": "unknown field"}})
            return httpx.Response(
                200,
                content=b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n',
            )

        final = None
        async for ev in _client(handler).complete_stream(MSGS):
            if ev.final is not None:
                final = ev.final
        assert len(attempts) == 2 and "stream_options" not in attempts[1]
        assert final is not None and final.text == "ok"


def test_overflow_heuristic() -> None:
    assert _is_context_overflow(400, "maximum context length exceeded")
    assert _is_context_overflow(400, "context_length_exceeded")
    assert not _is_context_overflow(400, "invalid model parameter")
    assert not _is_context_overflow(500, "context length exceeded")
