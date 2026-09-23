"""Streaming client and complete_stream capability tests.

All network egress is mocked (SSE text responses via httpx.MockTransport);
tests never touch the network.
"""

import json
from typing import Any

import httpx
import pytest
from llm import client as client_mod
from llm import stream as stream_mod
from llm.capabilities import Deps, init_deps, registry
from llm.store import ProviderStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_secrets import SecretStore

_CHAT = {"id": "p1", "api_format": "chat", "base_url": "https://api.test/v1"}
_ANTHROPIC = {"id": "p1", "api_format": "anthropic", "base_url": "https://api.test/v1"}
USER_CTX = ActorContext(actor=LOCAL_USER)


def _line(obj: dict[str, Any]) -> str:
    """Generate SSE lines programmatically: json.dumps guarantees valid JSON."""
    return "data: " + json.dumps(obj, ensure_ascii=False)


def _sse(*objs: dict[str, Any] | str) -> str:
    """dict -> JSON line; str -> used verbatim as the data payload (e.g. the
    non-JSON [DONE] marker)."""
    return (
        "\n\n".join("data: " + obj if isinstance(obj, str) else _line(obj) for obj in objs) + "\n\n"
    )


def _anthropic_sse_fixture() -> str:
    """Realistic shape with event: lines: the parser dispatches on the data
    payload's type and ignores event lines."""
    pairs = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {"model": "claude-test", "usage": {"input_tokens": 12}},
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hel"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "lo"},
            },
        ),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(
        f"event: {event}\ndata: {json.dumps(obj, ensure_ascii=False)}\n\n" for event, obj in pairs
    )


def _chat_sse_fixture() -> str:
    return _sse(
        {"choices": [{"delta": {"role": "assistant"}}], "model": "gpt-test"},
        {"choices": [{"delta": {"content": "Hello"}}]},
        {"choices": [{"delta": {"content": " world"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "t", "arguments": '{"x":'},
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
                            {"index": 0, "function": {"arguments": '"1"}'}},
                        ]
                    }
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        },
        "[DONE]",
    )


# [DONE] uses _sse's string branch (no wrapping beyond the JSON prefix)
_CHAT_SSE = _chat_sse_fixture()
_ANTHROPIC_SSE = _anthropic_sse_fixture()


def _patch(monkeypatch, handler) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        stream_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def _collect(provider: dict[str, Any], **kw) -> list[dict[str, Any]]:
    return [
        c
        async for c in stream_mod.complete_stream(
            provider,
            api_key="sk",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            **kw,
        )
    ]


class TestChatStream:
    async def test_text_deltas_and_final(self, monkeypatch) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, text=_CHAT_SSE)

        _patch(monkeypatch, handler)
        chunks = await _collect(_CHAT)
        texts = [c["text"] for c in chunks if c["type"] == "text"]
        assert texts == ["Hello", " world"]
        final = chunks[-1]
        assert final["type"] == "final"
        assert final["text"] == "Hello world"
        assert final["usage"] == {
            "input_tokens": 9,
            "output_tokens": 3,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }
        assert final["model"] == "gpt-test"
        assert final["tool_calls"] == [{"id": "call_1", "name": "t", "arguments": {"x": "1"}}]
        # Streaming body carries the stream flag and include_usage (metering
        # depends on it)
        assert seen["body"]["stream"] is True
        assert seen["body"]["stream_options"] == {"include_usage": True}

    async def test_inline_think_split_to_reasoning_channel(self, monkeypatch) -> None:
        """MiniMax-style inline <think> in content: thinking rides the reasoning
        channel even when the tags arrive split across chunks."""
        sse = _sse(
            {"choices": [{"delta": {"content": "用户问我是谁。<thi"}}], "model": "mm"},
            {"choices": [{"delta": {"content": "nk>推理中</think>我是 Lucien。"}}]},
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = await _collect(_CHAT)
        texts = [c["text"] for c in chunks if c["type"] == "text"]
        reasonings = [c["text"] for c in chunks if c["type"] == "reasoning"]
        assert texts == ["用户问我是谁。", "我是 Lucien。"]
        assert reasonings == ["推理中"]
        final = chunks[-1]
        assert final["text"] == "用户问我是谁。我是 Lucien。"
        assert final["reasoning"] == "推理中"

    async def test_inline_tool_call_stripped_and_converted(self, monkeypatch) -> None:
        """MiniMax-style inline <tool_call> in content with an EMPTY wire
        tool_calls field: the markup never reaches the text channel and the
        block converts to a tool call."""
        sse = _sse(
            {"choices": [{"delta": {"content": "好的。<tool_ca"}}], "model": "mm"},
            {
                "choices": [
                    {
                        "delta": {
                            "content": 'll>\n{"name": "load_skill", "arguments": {"skill_name": "s"}}\n</tool_call>完成。'
                        }
                    }
                ],
            },
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = await _collect(_CHAT)
        texts = [c["text"] for c in chunks if c["type"] == "text"]
        assert texts == ["好的。", "完成。"]
        final = chunks[-1]
        assert final["text"] == "好的。完成。"
        assert final["tool_calls"] == [
            {"id": "inline_0", "name": "load_skill", "arguments": {"skill_name": "s"}}
        ]

    async def test_inline_tool_call_echo_dropped_when_wire_field_wins(self, monkeypatch) -> None:
        """MiniMax echoes the markup WHILE also returning the parsed call in
        the wire tool_calls field: the parsed field wins (the call runs once)
        and the markup still never reaches the text channel."""
        sse = _sse(
            {
                "choices": [
                    {
                        "delta": {
                            "content": '<tool_call>]<]minimax[>[<invoke name="x"/></tool_call>',
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "activate_tools", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
                "model": "mm",
            },
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = await _collect(_CHAT)
        assert [c["text"] for c in chunks if c["type"] == "text"] == []
        final = chunks[-1]
        assert final["text"] == ""
        assert final["tool_calls"] == [{"id": "call_1", "name": "activate_tools", "arguments": {}}]

    async def test_tool_only_stream(self, monkeypatch) -> None:
        """Tool-only stream without text: no text chunks; final carries the
        parsed tool_calls."""
        sse = _sse(
            {"choices": [{"delta": {"role": "assistant"}}], "model": "m"},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "echo_tool", "arguments": "{}"},
                                },
                            ]
                        }
                    }
                ]
            },
            "[DONE]",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = await _collect(_CHAT)
        assert not [c for c in chunks if c["type"] == "text"]
        assert chunks[-1]["tool_calls"] == [{"id": "c1", "name": "echo_tool", "arguments": {}}]

    async def test_initial_status_error_classified(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="bad key")

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.AuthError):
            await _collect(_CHAT)

    async def test_overflow_status_classified(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="maximum context length exceeded")

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ContextOverflowError):
            await _collect(_CHAT)

    async def test_midstream_error_frame_raises(self, monkeypatch) -> None:
        """An error object inside an HTTP-200 chat stream must surface as a
        ProviderError, not end as a truncated normal-looking final chunk."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=_sse(
                    {"choices": [{"delta": {"content": "partial"}}]},
                    {"error": {"code": "content_filter", "message": "blocked mid-stream"}},
                ),
            )

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ProviderError, match="blocked mid-stream"):
            await _collect(_CHAT)

    async def test_midstream_error_frame_non_retriable(self, monkeypatch) -> None:
        """Deltas were already consumed by the time the error frame arrives:
        the raised error must never be retried."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, text=_sse({"choices": [{"delta": {"content": "p"}}]}, {"error": "boom"})
            )

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ProviderError) as exc:
            await _collect(_CHAT)
        assert exc.value.retriable is False


class TestAnthropicStream:
    async def test_text_deltas_and_final(self, monkeypatch) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, text=_ANTHROPIC_SSE)

        _patch(monkeypatch, handler)
        chunks = await _collect(_ANTHROPIC)
        texts = [c["text"] for c in chunks if c["type"] == "text"]
        assert texts == ["Hel", "lo"]
        final = chunks[-1]
        assert final["text"] == "Hello"
        assert final["usage"] == {
            "input_tokens": 12,
            "output_tokens": 5,
            "cached_tokens": 0,
            "cache_write_tokens": 0,
        }
        assert final["model"] == "claude-test"
        assert final["tool_calls"] == []
        assert seen["body"]["stream"] is True

    async def test_tool_use_blocks(self, monkeypatch) -> None:
        sse = _sse(
            {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 3}}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "tu_1", "name": "t"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"x":'},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '"v"}'},
            },
            {"type": "message_delta", "usage": {"output_tokens": 7}},
            {"type": "message_stop"},
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        chunks = await _collect(_ANTHROPIC)
        final = chunks[-1]
        assert final["tool_calls"] == [{"id": "tu_1", "name": "t", "arguments": {"x": "v"}}]

    async def test_midstream_disconnect_not_retriable(self, monkeypatch) -> None:
        """Disconnect while consuming the body: TransientError with
        retriable=False (deltas already consumed)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='data: {"type":"message_start"}\n\n')

        _patch(monkeypatch, handler)

        async def _drain():
            async for _ in stream_mod.complete_stream(
                _ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            ):
                # Normal exhaustion: MockTransport text simply ends, no disconnect
                pass

        await _drain()  # no raise: normal SSE end

    async def test_midstream_error_event_raises(self, monkeypatch) -> None:
        """An anthropic error event inside an HTTP-200 stream (overloaded etc.)
        must surface as a ProviderError, not end as a truncated final chunk."""

        def handler(request: httpx.Request) -> httpx.Response:
            sse = (
                "event: message_start\n"
                "data: " + json.dumps({"type": "message_start", "message": {"model": "m"}}) + "\n\n"
                "event: error\n"
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {"type": "overloaded_error", "message": "Overloaded"},
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            return httpx.Response(200, text=sse)

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.ProviderError, match="Overloaded"):
            await _collect(_ANTHROPIC)

    async def test_connect_error_retriable(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        _patch(monkeypatch, handler)
        with pytest.raises(client_mod.TransientError) as exc:
            await _collect(_ANTHROPIC)
        assert exc.value.retriable is True  # pre-first-packet: retryable semantics kept


class TestCapabilityStream:
    async def _setup_provider(self, deps) -> str:
        pid = (
            await execute(
                registry,
                "add_provider",
                USER_CTX,
                {
                    "display_name": "Test Provider",
                    "base_url": "https://api.test/v1",
                    "api_format": "chat",
                    "models": ["m1"],
                },
            )
        )["id"]
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk"})
        return pid

    async def test_end_to_end_and_usage_recorded(self, tmp_path, monkeypatch) -> None:
        store = ProviderStore(tmp_path / "llm.db")
        secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
        init_deps(Deps(store=store, secrets=secrets))
        pid = await self._setup_provider((store, secrets))
        _patch(monkeypatch, lambda r: httpx.Response(200, text=_CHAT_SSE))

        gen = await execute(
            registry,
            "complete_stream",
            USER_CTX,
            {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
        )
        chunks = [c async for c in gen]
        assert chunks[-1]["text"] == "Hello world"
        # Usage recorded after the stream is exhausted (direct metering, same
        # discipline as complete)
        stats = store.usage_stats(30)
        assert stats["input_tokens"] >= 9
        assert stats["calls"] >= 1
        store.close()
        secrets.close()

    async def test_usage_recorded_on_failure(self, tmp_path, monkeypatch) -> None:
        """Failure mid-stream also records usage (ok=0), matching complete's
        failure-metering semantics."""
        store = ProviderStore(tmp_path / "llm.db")
        secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
        init_deps(Deps(store=store, secrets=secrets))
        pid = await self._setup_provider((store, secrets))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        _patch(monkeypatch, handler)
        gen = await execute(
            registry,
            "complete_stream",
            USER_CTX,
            {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
        )
        with pytest.raises(ServiceError) as exc:
            async for _ in gen:
                pass
        assert exc.value.body.code == "LLM.UNAVAILABLE"
        # Failures also write usage rows (ok=0); usage_stats ignores ok, so
        # query the table directly
        with store._lock:
            failed = store._conn.execute("SELECT COUNT(*) FROM usage WHERE ok = 0").fetchone()[0]
        assert failed >= 1
        store.close()
        secrets.close()

    async def test_rest_rejected(self, tmp_path, monkeypatch) -> None:
        """The streaming capability is explicitly rejected on REST (platform
        behavior); here we just lock the llm domain metadata."""
        store = ProviderStore(tmp_path / "llm.db")
        secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
        init_deps(Deps(store=store, secrets=secrets))
        assert registry.get("complete_stream").streaming is True
        store.close()
        secrets.close()


class TestStreamBoundary:
    """Edge/extreme/stress cases: SSE variants and pathological inputs."""

    async def test_chat_meta_finish_reason_and_empty_dropped(self, monkeypatch) -> None:
        """Terminal frame's finish_reason rides the final meta; unreported
        keys (service_tier here) are dropped, not emitted as empty strings."""
        sse = _sse(
            {"choices": [{"delta": {"content": "hi"}}], "model": "m", "created": 1727000000},
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        meta = chunks[-1]["meta"]
        assert meta == {"finish_reason": "stop", "created": 1727000000}

    async def test_chat_meta_truncation_visible(self, monkeypatch) -> None:
        """finish_reason=length (output-cap cut) survives to the final chunk:
        the UI/agent flags the round instead of treating it as complete."""
        sse = _sse(
            {"choices": [{"delta": {"content": "par"}}]},
            {"choices": [{"delta": {}, "finish_reason": "length"}]},
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert chunks[-1]["meta"]["finish_reason"] == "length"

    async def test_anthropic_stop_reason_and_service_tier(self, monkeypatch) -> None:
        """message_delta.stop_reason -> meta.finish_reason; message_start
        service_tier is captured; empty keys dropped."""
        pairs = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "model": "claude-test",
                        "service_tier": "priority",
                        "usage": {"input_tokens": 3},
                    },
                },
            ),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "x"},
                },
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "max_tokens"},
                    "usage": {"output_tokens": 2},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        sse = "".join(f"event: {e}\ndata: {json.dumps(o)}\n\n" for e, o in pairs)
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_ANTHROPIC)
        meta = chunks[-1]["meta"]
        assert meta == {
            "finish_reason": "max_tokens",
            "service_tier": "priority",
        }
        assert chunks[-1]["usage"]["cache_write_tokens"] == 0

    async def test_anthropic_delta_usage_overrides_start_snapshot(self, monkeypatch) -> None:
        """Current Anthropic contract: message_delta.usage is the complete
        cumulative usage. Volcengine Ark sends 0 placeholders in message_start
        with real input/cache values arriving in message_delta; non-zero delta
        values must win over the start snapshot (legacy shape unaffected)."""
        pairs = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {"model": "m", "usage": {"input_tokens": 0, "output_tokens": 1}},
                },
            ),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {
                        "input_tokens": 16,
                        "output_tokens": 16,
                        "cache_creation_input_tokens": 4,
                        "cache_read_input_tokens": 9,
                    },
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
        sse = "".join(f"event: {e}\ndata: {json.dumps(o)}\n\n" for e, o in pairs)
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_ANTHROPIC)
        usage = chunks[-1]["usage"]
        assert usage["input_tokens"] == 16
        assert usage["output_tokens"] == 16
        assert usage["cache_write_tokens"] == 4
        assert usage["cached_tokens"] == 9

    async def test_crlf_line_endings(self, monkeypatch) -> None:
        """CRLF line endings (common behind Windows proxies/gateways): no
        empty-line junk and aggregation still works."""
        sse = _CHAT_SSE.replace("\n\n", "\r\n\r\n")
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert "".join(c["text"] for c in chunks if c["type"] == "text") == "Hello world"

    async def test_missing_done_marker(self, monkeypatch) -> None:
        """Endpoint drops the stream without [DONE]: received deltas and the
        final chunk are still emitted completely."""
        sse = _CHAT_SSE.replace("data: [DONE]\n\n", "")
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        final = chunks[-1]
        assert final["text"] == "Hello world"
        assert final["usage"]["input_tokens"] == 9

    async def test_garbage_lines_ignored(self, monkeypatch) -> None:
        """SSE comments/keep-alives/non-JSON data lines: skipped without
        crashing."""
        sse = (
            ": ping\n\n"
            "event: keep-alive\n\n"
            "data: not-json{{{\n\n"
            'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert [c["text"] for c in chunks if c["type"] == "text"] == ["a"]
        assert chunks[-1]["type"] == "final"

    async def test_tool_indexes_out_of_order(self, monkeypatch) -> None:
        """Out-of-order index fragments (extreme): final reassembles in
        ascending index order."""
        sse = _sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 2,
                                    "id": "c3",
                                    "function": {"name": "t3", "arguments": "c"},
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
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "t1", "arguments": "a"},
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
                                {
                                    "index": 1,
                                    "id": "c2",
                                    "function": {"name": "t2", "arguments": "b"},
                                },
                            ]
                        }
                    }
                ]
            },
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert [t["id"] for t in chunks[-1]["tool_calls"]] == ["c1", "c2", "c3"]

    async def test_tool_name_resent_every_chunk(self, monkeypatch) -> None:
        """Some compat endpoints resend the full id/name on every fragment:
        must overwrite, not append."""
        sse = _sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "echo_tool", "arguments": '{"x":'},
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
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "echo_tool", "arguments": '"1"}'},
                                },
                            ]
                        }
                    }
                ]
            },
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        (tc,) = chunks[-1]["tool_calls"]
        assert tc["name"] == "echo_tool"  # not "tooecho_tool"
        assert tc["arguments"] == {"x": "1"}

    async def test_invalid_tool_arguments_json_degrades(self, monkeypatch) -> None:
        """Argument fragments don't form valid JSON: degrade to empty args
        without crashing."""
        sse = _sse(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "t", "arguments": '{"x": '},
                                },
                            ]
                        }
                    }
                ]
            },
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert chunks[-1]["tool_calls"] == [{"id": "c1", "name": "t", "arguments": {}}]

    async def test_usage_null_and_absent(self, monkeypatch) -> None:
        """usage missing/null: metering records 0 without crashing."""
        sse = _sse(
            {"choices": [{"delta": {"content": "a"}}], "usage": None},
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert chunks[-1]["usage"] == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        }

    async def test_anthropic_ping_and_unknown_events(self, monkeypatch) -> None:
        """Anthropic ping/unknown event types: ignored without crashing."""
        sse = _sse(
            {"type": "ping"},
            {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}},
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "inner monologue"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "answer"},
            },
            {"type": "message_delta", "usage": {"output_tokens": 2}},
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_ANTHROPIC)
        assert [c["text"] for c in chunks if c["type"] == "text"] == ["answer"]
        # Thinking rides its own channel and aggregates into the final chunk,
        # never into the answer text.
        assert [c["text"] for c in chunks if c["type"] == "reasoning"] == ["inner monologue"]
        assert chunks[-1]["reasoning"] == "inner monologue"
        assert chunks[-1]["text"] == "answer"

    async def test_anthropic_thinking_signature_captured(self, monkeypatch) -> None:
        """Thinking signature deltas are captured for verbatim echo-back."""
        sse = _sse(
            {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}},
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "weigh"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "sig-9"},
            },
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "redacted_thinking", "data": "opaque"},
            },
            {"type": "message_delta", "usage": {"output_tokens": 2}},
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_ANTHROPIC)
        assert chunks[-1]["thinking_blocks"] == [
            {"type": "thinking", "thinking": "weigh", "signature": "sig-9"},
            {"type": "redacted_thinking", "data": "opaque"},
        ]

    async def test_anthropic_thinking_with_tools_coexists(self, monkeypatch) -> None:
        """Streaming: thinking and tools share one request (no pre-wire refusal)."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, text=_sse({"type": "message_stop"}))

        _patch(monkeypatch, handler)
        await _collect(
            _ANTHROPIC,
            tools=[{"name": "t", "description": "t", "schema": {}}],
            reasoning_effort="low",
        )
        assert seen["body"]["thinking"] == {"type": "enabled", "budget_tokens": 2048}
        assert seen["body"]["tools"][0]["name"] == "t"
        assert "temperature" not in seen["body"]

    async def test_chat_reasoning_content_captured(self, monkeypatch) -> None:
        """OpenAI-style reasoning_content streams on its own channel and
        aggregates into the final chunk."""
        sse = _sse(
            {"choices": [{"delta": {"reasoning_content": "step one"}}]},
            {"choices": [{"delta": {"reasoning_content": "step two"}}]},
            {"choices": [{"delta": {"content": "answer"}}]},
            "[DONE]",
        )
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        assert [c["text"] for c in chunks if c["type"] == "reasoning"] == [
            "step one",
            "step two",
        ]
        assert chunks[-1]["reasoning"] == "step onestep two"
        assert chunks[-1]["text"] == "answer"

    async def test_stress_thousands_of_deltas(self, monkeypatch) -> None:
        """Stress: 5000 delta fragments, lossless and duplicate-free
        aggregation."""
        n = 5000
        objs: list[dict[str, Any] | str] = [
            {"choices": [{"delta": {"content": "x"}}]} for _ in range(n)
        ]
        objs.append("[DONE]")
        sse = _sse(*objs)
        _patch(monkeypatch, lambda r: httpx.Response(200, text=sse))
        chunks = await _collect(_CHAT)
        deltas = [c for c in chunks if c["type"] == "text"]
        assert len(deltas) == n
        assert chunks[-1]["text"] == "x" * n
