"""Tests for the llm service: provider catalog, secret boundary, connection
test, usage stats.

All network egress is mocked (httpx.MockTransport); tests never touch the
network.
"""

import json
from typing import Any, ClassVar

import httpx
import pytest
from llm import client as client_mod
from llm.capabilities import Deps, init_deps, registry
from llm.store import ProviderStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_secrets import SecretStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path, monkeypatch):
    store = ProviderStore(tmp_path / "llm.db")
    secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
    init_deps(Deps(store=store, secrets=secrets))

    # Replace all network egress with a MockTransport (realistic chat replies)
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "pong"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                    "model": "gpt-4o-mini",
                },
            )
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "pong"}],
                "usage": {"input_tokens": 3, "output_tokens": 1},
                "model": "claude",
            },
        )

    orig = httpx.AsyncClient
    monkeypatch.setattr(
        client_mod.httpx,
        "AsyncClient",
        lambda **kw: orig(transport=httpx.MockTransport(mock_handler), **kw),
    )
    yield store, secrets
    store.close()
    secrets.close()


async def _add_sample() -> str:
    out = await execute(
        registry,
        "add_provider",
        USER_CTX,
        {
            "display_name": "Test Provider",
            "base_url": "https://api.test/v1",
            "api_format": "chat",
            "models": ["m1", "m2"],
        },
    )
    return out["id"]


class TestCatalog:
    async def test_builtin_catalog(self, deps) -> None:
        out = await execute(registry, "list_builtin_providers", AGENT_CTX, {})
        assert any(p["preset_id"] == "openai" for p in out)
        defaults = await execute(
            registry, "get_provider_defaults", AGENT_CTX, {"preset_id": "moonshot"}
        )
        assert defaults["api_format"] == "chat"

    async def test_bad_format_rejected(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "add_provider",
                USER_CTX,
                {
                    "display_name": "x",
                    "base_url": "https://x",
                    "api_format": "magic",
                },
            )
        assert exc.value.body.code == "LLM.INVALID_INPUT"


class TestSecretBoundary:
    async def test_agent_cannot_write_api_key(self, deps) -> None:
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "set_api_key", AGENT_CTX, {"provider_id": pid, "api_key": "sk-x"}
            )
        assert exc.value.body.code == "LLM.FORBIDDEN"  # user-only privacy rule

    async def test_user_writes_key_listing_shows_flag_only(self, deps) -> None:
        pid = await _add_sample()
        await execute(
            registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-secret"}
        )
        providers = await execute(registry, "list_providers", AGENT_CTX, {})
        mine = next(p for p in providers if p["id"] == pid)
        assert mine["has_api_key"] is True
        assert "sk-secret" not in repr(providers)  # the key never exits via capabilities

    async def test_agent_cannot_set_loopback_base_url(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "add_provider",
                AGENT_CTX,
                {
                    "display_name": "hijack",
                    "base_url": "http://127.0.0.1:9/v1",
                    "api_format": "chat",
                    "models": ["m"],
                },
            )
        assert exc.value.body.code == "LLM.FORBIDDEN"

    async def test_user_may_set_loopback_base_url(self, deps) -> None:
        out = await execute(
            registry,
            "add_provider",
            USER_CTX,
            {
                "display_name": "local",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_format": "chat",
                "models": ["llama"],
            },
        )
        assert "11434" in out["base_url"]

    async def test_agent_cannot_change_base_url_via_update(self, deps) -> None:
        """Changing base_url sends the stored key to a new host; update is
        user-only for that field."""
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "update_provider",
                AGENT_CTX,
                {
                    "provider_id": pid,
                    "base_url": "https://evil.example/v1",
                },
            )
        assert exc.value.body.code == "LLM.FORBIDDEN"
        store, _ = deps
        assert store.get(pid)["base_url"] == "https://api.test/v1"  # untouched by upsert

    async def test_agent_may_update_metadata_without_base_url(self, deps) -> None:
        """Metadata-only updates (name/model list) remain allowed for agents."""
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            AGENT_CTX,
            {
                "provider_id": pid,
                "display_name": "new name",
                "models": ["m9"],
            },
        )
        assert out["display_name"] == "new name"
        assert out["base_url"] == "https://api.test/v1"

    async def test_models_meta_round_trips_and_validates(self, deps) -> None:
        """Per-model metadata saves and reads back; malformed shapes are rejected."""
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            USER_CTX,
            {
                "provider_id": pid,
                "models_meta": {
                    "m": {"image_input": True, "thinking": True, "context_window": 200000}
                },
            },
        )
        assert out["models_meta"]["m"]["thinking"] is True
        store, _ = deps
        assert store.get(pid)["models_meta"]["m"]["context_window"] == 200000

        for bad in (
            {"m": {"image_input": "yes"}},  # bool fields take booleans only
            {"m": {"context_window": -1}},  # budgets are positive ints
            {"m": {"nonsense": True}},  # unknown fields are rejected, not ignored
            {"": {"thinking": True}},  # empty model id
        ):
            with pytest.raises(ServiceError) as exc:
                await execute(
                    registry,
                    "update_provider",
                    USER_CTX,
                    {"provider_id": pid, "models_meta": bad},
                )
            assert exc.value.body.code == "LLM.INVALID_INPUT"

    async def test_user_changes_base_url_ok(self, deps) -> None:
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            USER_CTX,
            {
                "provider_id": pid,
                "base_url": "https://api.new/v2",
            },
        )
        assert out["base_url"] == "https://api.new/v2"

    async def test_key_without_material_reads_back_guide(self, deps, monkeypatch) -> None:
        """No key material on this machine: the unified error body carries
        guidance instead of a 500."""
        from platform_secrets import SecretUnavailableError

        def boom(key: str, plain: str) -> None:
            raise SecretUnavailableError("no key material")

        monkeypatch.setattr(deps[1], "set", boom)
        pid = await _add_sample()
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"}
            )
        assert exc.value.body.code == "LLM.UNAVAILABLE"
        assert "SECRETS_ENCRYPTION_KEY" in exc.value.body.hint


class TestConnectionAndUsage:
    async def test_test_connection_ok(self, deps) -> None:
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(
            registry, "test_connection", USER_CTX, {"provider_id": pid, "model": "m1"}
        )
        assert out["ok"] is True and out["latency_ms"] >= 0

    async def test_test_connection_without_key(self, deps) -> None:
        pid = await _add_sample()
        with pytest.raises(ServiceError, match="api key"):
            await execute(registry, "test_connection", USER_CTX, {"provider_id": pid})

    async def test_complete_records_usage(self, deps) -> None:
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(
            registry,
            "complete",
            AGENT_CTX,
            {
                "provider_id": pid,
                "model": "m1",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert out["text"] == "pong"
        stats = await execute(registry, "get_usage_stats", USER_CTX, {"days": 1})
        assert stats["calls"] == 1 and stats["input_tokens"] == 3
        assert stats["by_model"][0]["model"] == "gpt-4o-mini"


class TestCompleteWithTools:
    """Dual tool formats: neutral input, request bodies converted per
    api_format, tool_calls parsed uniformly."""

    TOOLS: ClassVar[list[dict]] = [
        {
            "name": "create_note",
            "description": "create a note",
            "schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        }
    ]
    # Bind the real constructor at class definition time: the deps fixture
    # already patched httpx.AsyncClient, so a second patch must bypass it
    _real_client: ClassVar[type] = httpx.AsyncClient

    def _patch(self, monkeypatch, handler) -> None:
        real = self._real_client
        monkeypatch.setattr(
            client_mod.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

    async def _add(self, api_format: str) -> str:
        out = await execute(
            registry,
            "add_provider",
            USER_CTX,
            {
                "display_name": "Test Provider",
                "base_url": "https://api.test/v1",
                "api_format": api_format,
                "models": ["m1"],
            },
        )
        await execute(
            registry, "set_api_key", USER_CTX, {"provider_id": out["id"], "api_key": "sk-x"}
        )
        return out["id"]

    async def test_chat_format(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["tools"] = json.loads(request.content).get("tools")
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "create_note",
                                            "arguments": '{"title": "t"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    "model": "gpt-4o-mini",
                },
            )

        self._patch(monkeypatch, handler)
        pid = await self._add("chat")
        out = await execute(
            registry,
            "complete",
            AGENT_CTX,
            {
                "provider_id": pid,
                "model": "m1",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": self.TOOLS,
            },
        )
        # Request body converted to the OpenAI function format
        assert seen["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "create_note",
                    "description": "create a note",
                    "parameters": self.TOOLS[0]["schema"],
                },
            }
        ]
        # JSON-string arguments in the reply parsed into a dict
        assert out["tool_calls"] == [
            {"id": "call_1", "name": "create_note", "arguments": {"title": "t"}}
        ]

    async def test_anthropic_format(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["tools"] = json.loads(request.content).get("tools")
            return httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "text", "text": "calling tool"},
                        {
                            "type": "tool_use",
                            "id": "tu_1",
                            "name": "create_note",
                            "input": {"title": "t"},
                        },
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                    "model": "claude",
                },
            )

        self._patch(monkeypatch, handler)
        pid = await self._add("anthropic")
        out = await execute(
            registry,
            "complete",
            AGENT_CTX,
            {
                "provider_id": pid,
                "model": "m1",
                "messages": [{"role": "user", "content": "hi"}],
                "tools": self.TOOLS,
            },
        )
        assert seen["tools"] == [
            {
                "name": "create_note",
                "description": "create a note",
                "input_schema": self.TOOLS[0]["schema"],
            }
        ]
        assert out["text"] == "calling tool"
        assert out["tool_calls"] == [
            {"id": "tu_1", "name": "create_note", "arguments": {"title": "t"}}
        ]

    async def test_without_tools_no_field_in_body(self, deps, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "pong"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m1",
                },
            )

        self._patch(monkeypatch, handler)
        pid = await self._add("chat")
        out = await execute(
            registry,
            "complete",
            AGENT_CTX,
            {
                "provider_id": pid,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert "tools" not in seen["body"]  # no tools passed: field absent from body
        assert out["tool_calls"] == []

    async def test_anthropic_thinking_with_tools_coexists(self, deps, monkeypatch) -> None:
        """Extended thinking coexists with tool use (interleaved thinking):
        both ride the same request and no temperature is sent."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"content": [], "usage": {}})

        self._patch(monkeypatch, handler)
        from llm.client import complete as raw_complete

        await raw_complete(
            {
                "id": "p",
                "base_url": "https://api.test/v1",
                "api_format": "anthropic",
            },
            api_key="sk-x",
            model="m1",
            messages=[{"role": "user", "content": "hi"}],
            tools=self.TOOLS,
            reasoning_effort="low",
        )
        body = seen["body"]
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 2048}
        assert body["tools"][0]["name"] == "create_note"
        assert "temperature" not in body  # forbidden with thinking enabled

    async def test_anthropic_thinking_blocks_captured(self, deps, monkeypatch) -> None:
        """Thinking text lands in reasoning (never in text); raw thinking and
        redacted blocks are kept verbatim for echo-back."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "weigh options",
                            "signature": "sig-1",
                        },
                        {"type": "redacted_thinking", "data": "opaque"},
                        {"type": "text", "text": "answer"},
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 9},
                    "model": "claude",
                },
            )

        self._patch(monkeypatch, handler)
        from llm.client import complete as raw_complete

        out = await raw_complete(
            {
                "id": "p",
                "base_url": "https://api.test/v1",
                "api_format": "anthropic",
            },
            api_key="sk-x",
            model="m1",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort="low",
        )
        assert out.text == "answer"
        assert out.reasoning == "weigh options"
        assert out.thinking_blocks == (
            {"type": "thinking", "thinking": "weigh options", "signature": "sig-1"},
            {"type": "redacted_thinking", "data": "opaque"},
        )

    async def test_anthropic_thinking_blocks_echoed_verbatim(self, deps, monkeypatch) -> None:
        """Stored thinking blocks go back first and verbatim while tool use
        continues, satisfying the provider's echo requirement."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"content": [{"type": "text", "text": "done"}], "usage": {}}
            )

        self._patch(monkeypatch, handler)
        from llm.client import complete as raw_complete

        stored = {"type": "thinking", "thinking": "weigh options", "signature": "sig-1"}
        await raw_complete(
            {
                "id": "p",
                "base_url": "https://api.test/v1",
                "api_format": "anthropic",
            },
            api_key="sk-x",
            model="m1",
            messages=[
                {
                    "role": "assistant",
                    "content": "calling tool",
                    "tool_calls": [{"id": "tu_1", "name": "create_note", "arguments": {}}],
                    "thinking_blocks": [stored, {"type": "bogus", "x": 1}],
                },
                {"role": "tool", "tool_call_id": "tu_1", "content": "ok"},
            ],
            tools=self.TOOLS,
            reasoning_effort="low",
        )
        assistant = seen["body"]["messages"][0]
        assert assistant["role"] == "assistant"
        assert assistant["content"][0] == stored  # thinking first, verbatim
        assert assistant["content"][1] == {"type": "text", "text": "calling tool"}
        assert all(b.get("type") != "bogus" for b in assistant["content"])

    async def test_chat_reasoning_content_captured(self, deps, monkeypatch) -> None:
        """OpenAI-style reasoning_content lands in reasoning, not text."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "answer",
                                "reasoning_content": "inner monologue",
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 9},
                    "model": "m1",
                },
            )

        self._patch(monkeypatch, handler)
        from llm.client import complete as raw_complete

        out = await raw_complete(
            {
                "id": "p",
                "base_url": "https://api.test/v1",
                "api_format": "chat",
            },
            api_key="sk-x",
            model="m1",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert out.text == "answer"
        assert out.reasoning == "inner monologue"
        assert out.thinking_blocks == ()


class TestMessageTranslation:
    """Neutral history -> provider request bodies: paired history uses native
    tool protocols, orphans are downgraded, errors carry the response body.

    The translation layer encodes paired history into OpenAI tool_call_id /
    Anthropic tool_use_id native shapes. Orphans can still remain in history
    (old sessions, compressor pruning dropping the assistant message,
    interrupted loops); sent verbatim they get 400s from Anthropic-style
    endpoints (e.g. the MiniMax compat layer, error 2013 "tool result's tool
    id not found") and strict OpenAI endpoints — and once in history every
    later turn of the session is rejected too, so orphans degrade to user
    text as a fallback.
    """

    _real_client: ClassVar[type] = httpx.AsyncClient

    def _patch(self, monkeypatch, handler) -> None:
        real = self._real_client
        monkeypatch.setattr(
            client_mod.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

    _ANTHROPIC: ClassVar[dict] = {
        "id": "p",
        "base_url": "https://api.test/anthropic",
        "api_format": "anthropic",
    }
    _CHAT: ClassVar[dict] = {"id": "p", "base_url": "https://api.test/v1", "api_format": "chat"}
    _HISTORY: ClassVar[list] = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "add a provider for me"},
        {"role": "tool", "name": "ask_user", "content": "[tool result] user did not respond"},
    ]
    # Paired history (simulating _react backfill): results share tool_call ids
    _PAIRED: ClassVar[list] = [
        {"role": "system", "content": "You are an assistant."},
        {"role": "user", "content": "call the tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "echo_tool", "arguments": {"x": "a"}},
                {"id": "call_2", "name": "echo_tool", "arguments": {"x": "b"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "echo_tool", "content": "echo:a"},
        {"role": "tool", "tool_call_id": "call_2", "name": "echo_tool", "content": "echo:b"},
        {"role": "user", "content": "continue"},
    ]

    async def test_anthropic_flattens_bare_tool_role(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        out = await client_mod.complete(
            self._ANTHROPIC, api_key="sk", model="m", messages=self._HISTORY
        )
        assert out.text == "ok"
        roles = [m["role"] for m in seen["body"]["messages"]]
        assert "tool" not in roles  # the endpoint rejects role:"tool"
        last = seen["body"]["messages"][-1]
        assert last["role"] == "user"
        assert "ask_user" in last["content"] and "user did not respond" in last["content"]

    async def test_chat_format_flattens_bare_tool_role(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=self._HISTORY)
        roles = [m["role"] for m in seen["body"]["messages"]]
        assert "tool" not in roles

    async def test_chat_paired_tool_calls_native_shape(self, monkeypatch) -> None:
        """Paired history uses the native OpenAI tool protocol in chat format,
        no flattening."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=self._PAIRED)
        msgs = seen["body"]["messages"]
        # Paired messages keep their native roles, no downgrade
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "tool", "user"]
        # assistant.tool_calls reshaped to OpenAI form: type:function + JSON-string args
        assert msgs[2]["tool_calls"] == [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "echo_tool", "arguments": '{"x": "a"}'},
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "echo_tool", "arguments": '{"x": "b"}'},
            },
        ]
        # tool results carry tool_call_id, paired with the assistant
        assert [m["tool_call_id"] for m in msgs[3:5]] == ["call_1", "call_2"]

    async def test_anthropic_paired_tool_use_blocks(self, monkeypatch) -> None:
        """Paired history sends tool_use / tool_result content blocks in
        anthropic format, not flattened strings."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m", messages=self._PAIRED)
        msgs = seen["body"]["messages"]
        # system extracted; assistant uses content blocks, empty content makes
        # no empty text block
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "user"]
        assert msgs[1]["content"] == [
            {"type": "tool_use", "id": "call_1", "name": "echo_tool", "input": {"x": "a"}},
            {"type": "tool_use", "id": "call_2", "name": "echo_tool", "input": {"x": "b"}},
        ]
        # Multiple results of one assistant turn merge into a single user
        # message, tool_use_id matching its tool_use
        assert msgs[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "echo:a"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "echo:b"},
        ]

    async def test_chat_strips_thinking_blocks(self, monkeypatch) -> None:
        """Stored thinking blocks are Anthropic-only: a mid-session provider
        switch to chat format must not leak unknown message fields (strict
        OpenAI endpoints 400 on additional properties)."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        history = [
            dict(m, thinking_blocks=[{"type": "thinking", "thinking": "t", "signature": "s"}])
            if m.get("role") == "assistant"
            else m
            for m in self._PAIRED
        ]
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=history)
        assert "thinking_blocks" not in json.dumps(seen["body"])

    async def test_anthropic_echo_drops_unsigned_and_dataless(self, monkeypatch) -> None:
        """Echo sanitizer: unsigned thinking replays without the signature
        key and dataless redacted blocks are dropped rather than echoed."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        history: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "name": "echo_tool", "arguments": {}}],
                "thinking_blocks": [
                    {"type": "thinking", "thinking": "unsigned"},
                    {"type": "redacted_thinking"},
                    {"type": "redacted_thinking", "data": "opaque"},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "echo:a"},
        ]
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m", messages=history)
        assert seen["body"]["messages"][0]["content"] == [
            {"type": "thinking", "thinking": "unsigned"},
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "tool_use", "id": "call_1", "name": "echo_tool", "input": {}},
        ]

    async def test_orphan_tool_flattens_alongside_paired(self, monkeypatch) -> None:
        """Mixed paired + orphan history: pairs keep native shapes while
        orphans (legacy/pruned leftovers) still degrade to user text."""
        seen = {}
        history = [*self._PAIRED, {"role": "tool", "name": "legacy", "content": "stale leftover"}]

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m", messages=history)
        msgs = seen["body"]["messages"]
        assert any(
            m["role"] == "assistant"
            and isinstance(m["content"], list)
            and any(b.get("type") == "tool_use" for b in m["content"])
            for m in msgs
        )
        last = msgs[-1]
        assert last["role"] == "user" and isinstance(last["content"], str)
        assert "legacy" in last["content"] and "stale leftover" in last["content"]

    async def test_incomplete_pair_strips_unmatched_tool_calls(self, monkeypatch) -> None:
        """assistant declared a/b but only a got a result: the outgoing copy
        keeps only a, avoiding endpoint 400."""
        seen = {}
        history: list[dict[str, Any]] = [
            {"role": "user", "content": "call the tool"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "echo_tool", "arguments": {"x": "a"}},
                    {"id": "call_2", "name": "echo_tool", "arguments": {"x": "b"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "echo_tool", "content": "echo:a"},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=history)
        msgs = seen["body"]["messages"]
        assistant = next(m for m in msgs if m["role"] == "assistant")
        assert [tc["id"] for tc in assistant["tool_calls"]] == ["call_1"]
        tools = [m for m in msgs if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tools] == ["call_1"]

    async def test_chat_empty_messages_never_sends_empty_array(self, monkeypatch) -> None:
        """Empty history in the chat branch likewise never sends an empty
        messages array."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(self._CHAT, api_key="sk", model="m", messages=[])
        assert seen["body"]["messages"]

    async def test_anthropic_rest_empty_never_sends_empty_messages(self, monkeypatch) -> None:
        """System-only history: no empty messages array (MiniMax 2013 on
        empty messages)."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        self._patch(monkeypatch, handler)
        await client_mod.complete(
            self._ANTHROPIC,
            api_key="sk",
            model="m",
            messages=[{"role": "system", "content": "only a system prompt"}],
        )
        assert seen["body"]["messages"]

        def handler_400(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "type": "error",
                    "error": {
                        "type": "invalid_request_error",
                        "message": "invalid params, tool result's tool id() not found (2013)",
                    },
                },
            )

        self._patch(monkeypatch, handler_400)
        with pytest.raises(client_mod.ProviderError) as exc:
            await client_mod.complete(
                self._ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert "2013" in str(exc.value)  # provider's real error reason is visible
