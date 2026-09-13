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
        assert reply.usage.cached_tokens == 0  # provider reported no cache fields

    async def test_usage_parses_cached_tokens_both_dialects(self) -> None:
        """prompt_tokens_details.cached_tokens (OpenAI) and
        cache_read_input_tokens (Anthropic-style gateway) both land."""

        def openai_style(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 5,
                        "prompt_tokens_details": {"cached_tokens": 80},
                    },
                },
            )

        def anthropic_style(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 5,
                        "cache_read_input_tokens": 64,
                    },
                },
            )

        reply = await _client(openai_style).complete(MSGS)
        assert reply.usage.cached_tokens == 80
        reply = await _client(anthropic_style).complete(MSGS)
        assert reply.usage.cached_tokens == 64

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


class TestTransientRetry:
    """Bounded retry for transient failures (mirrors the aggregate client):
    429 / 5xx / connect-phase errors retry; established-connection timeouts
    and non-transient statuses never retry."""

    @staticmethod
    def _zero_backoff(monkeypatch) -> list[float]:
        """Zero the backoff base and record sleep durations instead of really
        sleeping; returns the recorded delays."""
        sleeps: list[float] = []

        async def _sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr("agent.llm_http._RETRY_BACKOFF", 0)
        monkeypatch.setattr("agent.llm_http.asyncio.sleep", _sleep)
        return sleeps

    async def test_500_retried_then_succeeds(self, monkeypatch) -> None:
        self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(500, json={"error": {"message": "boom"}})
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}}
            )

        reply = await _client(handler).complete(MSGS)
        assert reply.text == "ok" and not reply.degraded
        assert calls["n"] == 2

    async def test_429_retry_after_hint_wins_over_backoff(self, monkeypatch) -> None:
        sleeps = self._zero_backoff(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"error": {"message": "slow down"}},
            )

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and "rate limited" in (reply.text or "")
        assert sleeps == [3.0, 3.0]  # hint (capped at 5s) beats the zero backoff

    async def test_500_exhaustion_degrades_provider_error(self, monkeypatch) -> None:
        self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503, json={"error": {"message": "down"}})

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and "provider server error" in (reply.text or "")
        assert calls["n"] == 3  # 1 original + 2 retries

    async def test_connect_error_retried_then_succeeds(self, monkeypatch) -> None:
        self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        reply = await _client(handler).complete(MSGS)
        assert reply.text == "ok"
        assert calls["n"] == 2

    async def test_read_timeout_never_retried(self, monkeypatch) -> None:
        sleeps = self._zero_backoff(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("established then stalled", request=request)

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and "timed out" in (reply.text or "")
        assert sleeps == []  # no retry once the connection was established

    async def test_nontransport_http_error_folds_immediately(self, monkeypatch) -> None:
        """HTTP-level but non-transient failures (e.g. redirect loops) must not
        burn the retry budget."""
        sleeps = self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.TooManyRedirects("loop", request=request)

        reply = await _client(handler).complete(MSGS)
        assert reply.degraded and "connection failed: TooManyRedirects" in (reply.text or "")
        assert calls["n"] == 1 and sleeps == []

    async def test_stream_500_before_first_delta_retried(self, monkeypatch) -> None:
        self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(502, json={"error": {"message": "bad gateway"}})
            return httpx.Response(
                200,
                content=b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\ndata: [DONE]\n\n',
            )

        deltas: list[str] = []
        final = None
        async for ev in _client(handler).complete_stream(MSGS):
            if ev.final is not None:
                final = ev.final
            else:
                deltas.append(ev.text_delta)
        assert deltas == ["ok"]
        assert final is not None and final.text == "ok"
        assert calls["n"] == 2

    async def test_stream_nontransient_status_not_retried(self, monkeypatch) -> None:
        sleeps = self._zero_backoff(monkeypatch)
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        final = None
        async for ev in _client(handler).complete_stream(MSGS):
            if ev.final is not None:
                final = ev.final
        assert final is not None and final.degraded and "authentication" in (final.text or "")
        assert calls["n"] == 1 and sleeps == []
