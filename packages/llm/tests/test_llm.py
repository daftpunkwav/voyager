"""Tests for the llm service: provider catalog, secret boundary, connection
test, usage stats.

All network egress is mocked (httpx.MockTransport); tests never touch the
network.
"""

import json
import os
import time
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

    async def test_provider_row_flags_are_bools(self, deps) -> None:
        """Flag contract of the provider dict (the REST/frontend shape):
        enabled / custom / private_endpoint are real booleans after the
        sqlite 0/1 round-trip, never raw ints."""
        store, _secrets = deps
        await _add_sample()
        (provider,) = store.list(include_disabled=True)
        assert isinstance(provider["enabled"], bool)
        assert isinstance(provider["custom"], bool)
        assert isinstance(provider["private_endpoint"], bool)


class TestSecretBoundary:
    async def test_remove_provider_deletes_row_and_key(self, deps) -> None:
        """Deleting a provider removes the row AND clears its stored API key:
        an orphaned secret must never outlive the provider it belongs to."""
        from llm.capabilities.common import key_name

        _store, secrets = deps
        pid = await _add_sample()
        await execute(
            registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-doomed"}
        )
        assert secrets.has(key_name(pid)) is True
        out = await execute(registry, "remove_provider", USER_CTX, {"provider_id": pid})
        assert out == {"removed": pid}
        providers = await execute(registry, "list_providers", USER_CTX, {})
        assert all(p["id"] != pid for p in providers)
        assert secrets.has(key_name(pid)) is False

    async def test_remove_unknown_provider_not_found(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "remove_provider", USER_CTX, {"provider_id": "ghost"})
        assert exc.value.body.code == "LLM.NOT_FOUND"

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

    async def test_complete_reports_cached_tokens(self, deps, monkeypatch) -> None:
        """The returned usage dict must carry the provider's cached prompt
        tokens: the agent side parses it into Usage.cached_tokens and the
        prefix-cache health watch keys warm/cold round detection off that —
        omitting it pins the agent's cache view at "never warm"."""
        import types

        import llm.capabilities.complete as complete_mod

        async def fake_complete(p, *, api_key, model, **kw):
            return types.SimpleNamespace(
                text="pong",
                model=model,
                tool_calls=[],
                input_tokens=10,
                output_tokens=2,
                cached_tokens=7,
                reasoning="",
                thinking_blocks=[],
                reasoning_tokens=0,
                cache_write_tokens=0,
                meta=types.SimpleNamespace(to_dict=dict),
            )

        monkeypatch.setattr(complete_mod, "llm_complete", fake_complete)
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(
            registry,
            "complete",
            AGENT_CTX,
            {"provider_id": pid, "model": "m1", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert out["usage"]["cached_tokens"] == 7


class TestDefaultModelRetired:
    """The provider-level default_model is gone: an untagged model resolves
    to the first enabled entry of the model list."""

    async def test_effective_model_skips_disabled(self) -> None:
        from llm.capabilities.common import effective_model

        p = {"models": ["m1", "m2", "m3"], "models_meta": {"m1": {"enabled": False}}}
        assert effective_model(p) == "m2"
        assert effective_model(p, "m3") == "m3"  # explicit pin wins verbatim
        # all models disabled: still return the first instead of nothing
        assert (
            effective_model({"models": ["m1"], "models_meta": {"m1": {"enabled": False}}}) == "m1"
        )
        assert effective_model({"models": [], "models_meta": {}}) == ""

    async def test_models_meta_accepts_enabled_flag(self, deps) -> None:
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            USER_CTX,
            {"provider_id": pid, "models_meta": {"m1": {"enabled": False}}},
        )
        assert out["models_meta"]["m1"]["enabled"] is False

    async def test_default_model_input_is_rejected(self, deps) -> None:
        """The retired default_model input no longer binds — stale callers fail
        loudly (now a 400 envelope via signature binding, formerly a bare
        TypeError 500) instead of the flag being silently ignored."""
        pid = await _add_sample()
        with pytest.raises(ServiceError, match="default_model") as exc:
            await execute(
                registry,
                "update_provider",
                USER_CTX,
                {"provider_id": pid, "default_model": "m1"},
            )
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_complete_without_model_uses_first_enabled(self, deps, monkeypatch) -> None:
        import types

        import llm.capabilities.complete as complete_mod

        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        await execute(
            registry,
            "update_provider",
            USER_CTX,
            {"provider_id": pid, "models_meta": {"m1": {"enabled": False}}},
        )
        seen: dict = {}

        async def fake_complete(p, *, api_key, model, **kw):
            seen.update(model=model)
            return types.SimpleNamespace(
                text="pong",
                model=model,
                tool_calls=[],
                input_tokens=3,
                output_tokens=1,
                cached_tokens=0,
                reasoning="",
                thinking_blocks=[],
                reasoning_tokens=0,
                cache_write_tokens=0,
                meta=types.SimpleNamespace(to_dict=dict),
            )

        monkeypatch.setattr(complete_mod, "llm_complete", fake_complete)
        await execute(
            registry,
            "complete",
            AGENT_CTX,
            {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert seen["model"] == "m2"

    async def test_thinking_variants_and_defaults_round_trip(self, deps) -> None:
        """ZCode-shaped thinking config: supported variants plus the default
        variant store as flat meta fields; the retired thinking_levels map is
        rejected as an unknown key."""
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            USER_CTX,
            {
                "provider_id": pid,
                "models_meta": {
                    "m1": {
                        "thinking_variants": ["low", "high", "max"],
                        "thinking_default": "max",
                        "output_modalities": ["text"],
                    },
                },
            },
        )
        assert out["models_meta"]["m1"]["thinking_variants"] == ["low", "high", "max"]
        assert out["models_meta"]["m1"]["thinking_default"] == "max"

        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "update_provider",
                USER_CTX,
                {
                    "provider_id": pid,
                    "models_meta": {"m1": {"thinking_levels": {"low": "minimal"}}},
                },
            )
        assert exc.value.body.code == "LLM.INVALID_INPUT"

    async def test_compat_and_name_meta_round_trip(self, deps) -> None:
        pid = await _add_sample()
        out = await execute(
            registry,
            "update_provider",
            USER_CTX,
            {
                "provider_id": pid,
                "models_meta": {
                    "m1": {
                        "name": "DeepSeek Flash",
                        "compat": {
                            "maxTokensField": "max_tokens",
                            "supportsStore": False,
                        },
                    },
                },
            },
        )
        assert out["models_meta"]["m1"]["name"] == "DeepSeek Flash"
        assert out["models_meta"]["m1"]["compat"]["supportsStore"] is False
        # nested objects in compat are rejected (flat scalar/null object only)
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "update_provider",
                USER_CTX,
                {
                    "provider_id": pid,
                    "models_meta": {"m1": {"compat": {"bad": {"nested": 1}}}},
                },
            )
        assert exc.value.body.code == "LLM.INVALID_INPUT"


class TestRemoteModels:
    """list_remote_models: one GET /models against the provider base_url."""

    @staticmethod
    def _fake_client(monkeypatch, payload=None, status=200):
        import httpx as httpx_mod

        class FakeAsyncClient:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def build_request(self, method, url, **kw):
                return httpx_mod.Request(method, url, **kw)

            async def send(self, request, **kw):
                if status == 200:
                    return httpx_mod.Response(200, json=payload or {"data": []})
                return httpx_mod.Response(status, text="boom")

        monkeypatch.setattr(httpx_mod, "AsyncClient", FakeAsyncClient)

    async def test_returns_sorted_unique_ids(self, deps, monkeypatch) -> None:
        self._fake_client(monkeypatch, {"data": [{"id": "m-b"}, {"id": "m-a"}, {"id": "m-b"}]})
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        out = await execute(registry, "list_remote_models", USER_CTX, {"provider_id": pid})
        assert out["models"] == ["m-a", "m-b"]

    async def test_requires_key(self, deps) -> None:
        pid = await _add_sample()
        with pytest.raises(ServiceError, match="api key"):
            await execute(registry, "list_remote_models", USER_CTX, {"provider_id": pid})

    async def test_http_error_maps_to_unavailable(self, deps, monkeypatch) -> None:
        self._fake_client(monkeypatch, status=401)
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "list_remote_models", USER_CTX, {"provider_id": pid})
        assert exc.value.body.code == "LLM.UNAVAILABLE"

    async def test_anthropic_base_url_gets_version_segment(self, deps, monkeypatch) -> None:
        """The anthropic format expects a bare host (chat posts {base}/v1/messages),
        so the catalog request must mirror that and hit {base}/v1/models."""
        import httpx as httpx_mod

        seen: dict = {}

        class UrlCaptureClient:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def build_request(self, method, url, **kw):
                return httpx_mod.Request(method, url, **kw)

            async def send(self, request, **kw):
                seen["url"] = str(request.url)
                seen["host_header"] = request.headers.get("host")
                return httpx_mod.Response(200, json={"data": [{"id": "m-a"}]})

        monkeypatch.setattr(httpx_mod, "AsyncClient", UrlCaptureClient)
        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        await execute(
            registry,
            "update_provider",
            USER_CTX,
            {
                "provider_id": pid,
                "base_url": "https://api.anthropic.com",
                "api_format": "anthropic",
            },
        )
        await execute(registry, "list_remote_models", USER_CTX, {"provider_id": pid})
        # The connection is IP-pinned, but the version segment path and the
        # original Host header survive the rewrite
        assert seen["url"].endswith("/v1/models")
        assert seen["host_header"] == "api.anthropic.com"


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
        # assistant-first history gains the leading user turn (see
        # test_anthropic_assistant_first_history_leads_with_user)
        assistant = seen["body"]["messages"][1]
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

    async def test_chat_inline_tool_call_echo_wire_field_wins(self, deps, monkeypatch) -> None:
        """complete path (stream's mirror): MiniMax echoes inline <tool_call>
        markup in content WHILE also returning the parsed call in the wire
        tool_calls field — the parsed field wins (call runs once) and the
        markup never reaches the answer text."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '<tool_call>]<]minimax[>[<invoke name="x"/></tool_call>',
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "activate_tools",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    "model": "m1",
                },
            )

        self._patch(monkeypatch, handler)
        out = await client_mod.complete(
            {"id": "p", "base_url": "https://api.test/v1", "api_format": "chat"},
            api_key="sk-x",
            model="m1",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert out.text == ""
        assert out.tool_calls == ({"id": "call_1", "name": "activate_tools", "arguments": {}},)
        # Inline <think> reasoning joins the reasoning_content channel on the
        # complete path too.
        assert out.reasoning == ""

    async def test_chat_inline_tool_call_converted_when_wire_field_empty(
        self, deps, monkeypatch
    ) -> None:
        """complete path with an EMPTY wire tool_calls field: inline markup is
        the only carrier and converts; ids stay unique per entry."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "<think>plan</think>好的。\n<tool_call>"
                                    '[{"name": "a"}, {"name": "b"}]</tool_call>'
                                ),
                                "tool_calls": None,
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                    "model": "m1",
                },
            )

        self._patch(monkeypatch, handler)
        out = await client_mod.complete(
            {"id": "p", "base_url": "https://api.test/v1", "api_format": "chat"},
            api_key="sk-x",
            model="m1",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert out.text == "好的。\n"
        assert out.reasoning == "plan"
        assert [c["id"] for c in out.tool_calls] == ["inline_0", "inline_1"]
        assert [c["name"] for c in out.tool_calls] == ["a", "b"]


class TestReasoningEffortResolution:
    """llm.reasoning_effort resolves against the serving model's configured
    thinking variants (the settings page is the single source of truth): the
    empty setting follows the model's thinking_default, "off" disables, an
    override must be one of the model's variants. Models without a variants
    list keep the legacy canonical-only pass-through. The wire accepts any
    resolved value verbatim on chat/responses; anthropic maps only the
    canonical names (they carry budgets)."""

    VARIANTS_META: ClassVar[dict] = {
        "thinking": True,
        "thinking_variants": ["low", "high", "max"],
        "thinking_default": "max",
    }
    # Bind the real constructor at class definition time (same trick as
    # TestCompleteWithTools: the deps fixture already patched httpx).
    _real_client: ClassVar[type] = httpx.AsyncClient

    def _patch(self, monkeypatch, handler) -> None:
        real = self._real_client
        monkeypatch.setattr(
            client_mod.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

    def test_off_sentinel_disables(self) -> None:
        from llm.capabilities.complete import OFF_SENTINEL, resolve_reasoning_effort

        assert resolve_reasoning_effort(OFF_SENTINEL, self.VARIANTS_META) == ""
        assert resolve_reasoning_effort(OFF_SENTINEL, {}) == ""

    def test_variants_model_follows_default_when_unset(self) -> None:
        from llm.capabilities.complete import resolve_reasoning_effort

        assert resolve_reasoning_effort("", self.VARIANTS_META) == "max"
        # declared thinking without a default -> nothing to follow
        assert resolve_reasoning_effort("", {"thinking": True}) == ""

    def test_variants_model_validates_override(self) -> None:
        from llm.capabilities.complete import resolve_reasoning_effort

        assert resolve_reasoning_effort("high", self.VARIANTS_META) == "high"
        # stale value from a previous model (or a typo) falls back to the default
        assert resolve_reasoning_effort("medium", self.VARIANTS_META) == "max"
        assert resolve_reasoning_effort("xhigh", self.VARIANTS_META) == "max"

    def test_legacy_model_keeps_canonical_pass_through(self) -> None:
        from llm.capabilities.complete import resolve_reasoning_effort

        # no variants list: canonical names pass, unknown names stay unset
        assert resolve_reasoning_effort("low", {}) == "low"
        assert resolve_reasoning_effort("max", {}) == ""
        assert resolve_reasoning_effort("", {}) == ""

    def test_wire_passes_resolved_value_verbatim(self) -> None:
        from llm.client import reasoning_fields

        assert reasoning_fields("chat", "max", max_tokens=4096) == {"reasoning_effort": "max"}
        assert reasoning_fields("responses", "max", max_tokens=4096) == {
            "reasoning": {"effort": "max"}
        }
        assert reasoning_fields("chat", "", max_tokens=4096) == {}

    def test_anthropic_variant_without_budget_stays_unset(self) -> None:
        from llm.client import reasoning_fields

        # not in the model's variants list: nothing derivable, stays unset
        assert reasoning_fields("anthropic", "max", max_tokens=4096) == {}
        assert reasoning_fields("anthropic", "low", max_tokens=2048) == {
            "thinking": {"type": "enabled", "budget_tokens": 2048},
            "max_tokens": 2048 + 1024,  # raised above the budget
        }

    def test_anthropic_interpolates_variant_budget_by_position(self) -> None:
        from llm.client import reasoning_fields

        variants = ["low", "medium", "high", "xhigh", "max"]
        out = reasoning_fields("anthropic", "max", max_tokens=4096, variants=variants)
        assert out["thinking"] == {"type": "enabled", "budget_tokens": 16384}
        # xhigh sits between high and max on the declared list
        assert reasoning_fields("anthropic", "xhigh", max_tokens=4096, variants=variants)[
            "thinking"
        ] == {"type": "enabled", "budget_tokens": 12800}
        # canonical names keep their exact budgets even when listed
        assert reasoning_fields("anthropic", "high", max_tokens=4096, variants=variants)[
            "thinking"
        ] == {"type": "enabled", "budget_tokens": 16384}
        assert reasoning_fields("anthropic", "low", max_tokens=4096, variants=variants)[
            "thinking"
        ] == {"type": "enabled", "budget_tokens": 2048}
        # a name outside the list has no position to interpolate from
        assert reasoning_fields("anthropic", "turbo", max_tokens=4096, variants=variants) == {}

    async def test_complete_resolves_default_from_model_meta(self, tmp_path, monkeypatch) -> None:
        """End to end: empty override + a configured thinking_default -> the
        default variant lands on the wire verbatim (settings page decides)."""
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
        from llm.capabilities import Deps, init_deps
        from llm.capabilities.complete import OFF_SENTINEL
        from llm.settings import DEFS
        from platform_settings import SettingsStore

        settings = SettingsStore(tmp_path / "settings.db")
        settings.register_fresh(DEFS)
        init_deps(
            Deps(
                store=ProviderStore(tmp_path / "llm2.db"),
                secrets=SecretStore(tmp_path / "secrets2.db", key_material="test"),
                settings=settings,
            )
        )
        out = await execute(
            registry,
            "add_provider",
            USER_CTX,
            {
                "display_name": "Test Provider",
                "base_url": "https://api.test/v1",
                "api_format": "chat",
                "models": ["m1"],
                "models_meta": {"m1": self.VARIANTS_META},
            },
        )
        await execute(
            registry, "set_api_key", USER_CTX, {"provider_id": out["id"], "api_key": "sk-x"}
        )
        call = {"provider_id": out["id"], "messages": [{"role": "user", "content": "hi"}]}
        await execute(registry, "complete", AGENT_CTX, call)
        assert seen["body"]["reasoning_effort"] == "max"  # the configured default
        await settings.set("llm.reasoning_effort", OFF_SENTINEL, LOCAL_USER)
        await execute(registry, "complete", AGENT_CTX, call)
        assert "reasoning_effort" not in seen["body"]  # explicit off wins
        await settings.set("llm.reasoning_effort", "low", LOCAL_USER)
        await execute(registry, "complete", AGENT_CTX, call)
        assert seen["body"]["reasoning_effort"] == "low"  # validated override


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

    async def test_anthropic_tools_strip_default_and_backfill_type(self, monkeypatch) -> None:
        """Strict anthropic layers reject non-standard schema members: a
        top-level `default` (JSON-Schema-legal, not part of the anthropic tool
        dialect) is stripped, and a bare fragment still declares type object.
        Property-level schema stays untouched - the cleaning never widens."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["tools"] = json.loads(request.content).get("tools")
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "ok"}], "usage": {}, "model": "m"},
            )

        self._patch(monkeypatch, handler)
        tools = [
            {
                "name": "write",
                "description": "d",
                "schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": "a.txt"}},
                    "default": {"path": "a.txt"},
                },
            },
            {"name": "bare", "description": "d", "schema": {}},
        ]
        await client_mod.complete(
            self._ANTHROPIC,
            api_key="sk",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )
        write, bare = seen["tools"]
        assert write["input_schema"] == {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "a.txt"}},
        }
        assert bare["input_schema"] == {"type": "object"}

    async def test_rejected_request_dumps_into_debug_dir(self, tmp_path, monkeypatch) -> None:
        """A rejected request (4xx) writes the full request/response pair into
        LLM_DEBUG_DUMP_DIR - the only way to see what a strict provider
        actually disliked - and the dump never masks the raised error."""
        from llm.client import ProviderError

        dump_dir = tmp_path / "dump"
        monkeypatch.setenv("LLM_DEBUG_DUMP_DIR", str(dump_dir))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "2013 schema invalid"}})

        self._patch(monkeypatch, handler)
        with pytest.raises(ProviderError):
            await client_mod.complete(
                self._ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"name": "write", "description": "d", "schema": {"type": "object"}}],
            )
        dumps = list(dump_dir.glob("llm-*.json"))
        assert len(dumps) == 1
        dump = json.loads(dumps[0].read_text(encoding="utf-8"))
        assert dump["status"] == 400
        assert dump["url"].endswith("/v1/messages")
        assert dump["request"]["tools"][0]["name"] == "write"
        assert "2013" in dump["response"]

    async def test_no_dump_dir_means_no_dump(self, tmp_path, monkeypatch) -> None:
        """Without LLM_DEBUG_DUMP_DIR nothing is written (default quiet path)."""
        from llm.client import ProviderError

        monkeypatch.delenv("LLM_DEBUG_DUMP_DIR", raising=False)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "nope"}})

        self._patch(monkeypatch, handler)
        with pytest.raises(ProviderError):
            await client_mod.complete(
                self._ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert not (tmp_path / "dump").exists()

    @pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are a Unix-only contract")
    async def test_dump_file_is_created_owner_only(self, tmp_path, monkeypatch) -> None:
        """The dump carries conversation plaintext, so it must land 0o600 on
        disk: a regression to a plain write (0644) would expose it to every
        local account. Windows deliberately relies on the profile ACL."""
        from llm.client import ProviderError

        dump_dir = tmp_path / "dump"
        monkeypatch.setenv("LLM_DEBUG_DUMP_DIR", str(dump_dir))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "nope"}})

        self._patch(monkeypatch, handler)
        with pytest.raises(ProviderError):
            await client_mod.complete(
                self._ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        (dump,) = dump_dir.glob("llm-*.json")
        assert dump.stat().st_mode & 0o777 == 0o600

    async def test_dump_never_overwrites_an_existing_file(self, tmp_path, monkeypatch) -> None:
        """The dump is created O_EXCL under a pinned filename: a collision
        (replayed filename, concurrent retry) must skip the dump — never
        overwrite the earlier rejection's file — and the raised error carries
        no dump_path (the diagnostics write failed)."""

        class _FixedTimeNs:
            """time module stand-in for llm.client: only time_ns is pinned so
            the dump filename is predictable; everything else delegates."""

            def __getattr__(self, name: str):
                return getattr(time, name)

            @staticmethod
            def time_ns() -> int:
                return 1_760_000_000_000_000_000

        from llm.client import ProviderError

        dump_dir = tmp_path / "dump"
        dump_dir.mkdir()
        sentinel = dump_dir / "llm-1760000000000000000.json"
        sentinel.write_text('{"earlier": "rejection"}', encoding="utf-8")
        monkeypatch.setenv("LLM_DEBUG_DUMP_DIR", str(dump_dir))
        monkeypatch.setattr(client_mod, "time", _FixedTimeNs())

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {"message": "nope"}})

        self._patch(monkeypatch, handler)
        with pytest.raises(ProviderError) as exc:
            await client_mod.complete(
                self._ANTHROPIC,
                api_key="sk",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert exc.value.dump_path == ""
        assert "dump" not in exc.value.detail_suffix()
        assert sentinel.read_text(encoding="utf-8") == '{"earlier": "rejection"}'

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
        # no empty text block. The trailing user text ("continue") merges into
        # the tool_result user message: Anthropic requires roles to alternate,
        # two adjacent user rows are a 400.
        assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
        assert msgs[1]["content"] == [
            {"type": "tool_use", "id": "call_1", "name": "echo_tool", "input": {"x": "a"}},
            {"type": "tool_use", "id": "call_2", "name": "echo_tool", "input": {"x": "b"}},
        ]
        # Multiple results of one assistant turn merge into a single user
        # message, tool_use_id matching its tool_use; the next user row joins
        # the same message as a trailing text block
        assert msgs[2]["content"] == [
            {"type": "tool_result", "tool_use_id": "call_1", "content": "echo:a"},
            {"type": "tool_result", "tool_use_id": "call_2", "content": "echo:b"},
            {"type": "text", "text": "continue"},
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

    async def test_anthropic_echo_legacy_unsigned_stays_dataless_dropped(self, monkeypatch) -> None:
        """Legacy rows (no thinking_source stamp) keep the echo-anywhere
        behaviour — no silent history rewrite — while dataless redacted
        blocks are still dropped."""
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
        # index 1: the assistant-first history gains the leading user turn
        assert seen["body"]["messages"][1]["content"] == [
            {"type": "thinking", "thinking": "unsigned"},
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "tool_use", "id": "call_1", "name": "echo_tool", "input": {}},
        ]

    async def test_anthropic_echo_source_filter(self, monkeypatch) -> None:
        """Stamped blocks echo only to the model that issued them: same-model
        unsigned blocks pass (continuity on lenient endpoints), blocks from
        another model are dropped (a strict endpoint 400s on unsigned
        thinking replays)."""
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

        def _entry(source: str | None) -> dict[str, Any]:
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "name": "echo_tool", "arguments": {}}],
                "thinking_blocks": [{"type": "thinking", "thinking": "unsigned"}],
            }
            if source is not None:
                entry["thinking_source"] = source
            return entry

        # same model as the current request ("m"): echoed
        history = [_entry("m"), {"role": "tool", "tool_call_id": "call_1", "content": "x"}]
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m", messages=history)
        kinds = [b["type"] for b in seen["body"]["messages"][1]["content"]]
        assert "thinking" in kinds

        # a different model: dropped
        history = [
            _entry("other-model"),
            {"role": "tool", "tool_call_id": "call_1", "content": "x"},
        ]
        await client_mod.complete(self._ANTHROPIC, api_key="sk", model="m", messages=history)
        kinds = [b["type"] for b in seen["body"]["messages"][1]["content"]]
        assert "thinking" not in kinds
        assert any(b["type"] == "tool_use" for b in seen["body"]["messages"][1]["content"])

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
        # The orphan lands in the trailing merged user message as a text block
        # (adjacent user rows would be an alternation 400); its text survives
        # verbatim apart from the block framing.
        last = msgs[-1]
        assert last["role"] == "user" and isinstance(last["content"], list)
        assert any(
            isinstance(b, dict)
            and b.get("type") == "text"
            and "legacy" in b["text"]
            and "stale leftover" in b["text"]
            for b in last["content"]
        )

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

    async def test_anthropic_assistant_first_history_leads_with_user(self, monkeypatch) -> None:
        """Task-mode subagents carry the goal in system, so round 2+ opens
        with the assistant's tool_use (no user turn exists yet). Volcengine's
        anthropic layer rejects an assistant-first history with HTTP 400
        InvalidParameter — the wire request must lead with a user turn."""
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
            messages=[
                {"role": "system", "content": "goal lives here"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "call_1", "name": "echo_tool", "arguments": {"x": "a"}},
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "echo_tool",
                    "content": "echo:a",
                },
            ],
        )
        msgs = seen["body"]["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
        # The leading user turn is the same placeholder the empty-history
        # path uses; the assistant prefill keeps its tool_use blocks intact
        assert msgs[0]["content"] == "(no content, please continue)"
        assert msgs[1]["content"][0]["type"] == "tool_use"

        # A history that already opens with user passes through untouched
        await client_mod.complete(
            self._ANTHROPIC,
            api_key="sk",
            model="m",
            messages=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "hi"},
            ],
        )
        assert [m["role"] for m in seen["body"]["messages"]] == ["user"]

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


class TestCompleteTimeout:
    """_complete_timeout: the non-streaming read cap scales with the request's
    output budget (/8), floored at the shared _TIMEOUT (small answers must not
    shrink the default) and capped so a hung connection still fails in bounded
    time. The other three arms never move."""

    @pytest.mark.parametrize("max_tokens", [1, 100, 383])
    def test_small_output_budget_identical_to_shared_timeout(self, max_tokens: int) -> None:
        # 383/8 < 60s: the scaling must not lower the default read cap
        assert client_mod._complete_timeout(max_tokens) == client_mod._TIMEOUT

    def test_read_scales_with_the_output_budget(self) -> None:
        # pins the /8 factor in the uncapped band: 2000 output tokens -> 250s
        assert client_mod._complete_timeout(2000).read == 250.0

    def test_read_is_capped_so_hung_connections_fail_bounded(self) -> None:
        assert client_mod._COMPLETE_READ_CAP_S == 480.0  # pin the constant itself
        assert client_mod._complete_timeout(100_000).read == 480.0
        # 480*8 output tokens is the exact entry into the cap; one below scales
        assert client_mod._complete_timeout(3840).read == 480.0
        assert client_mod._complete_timeout(3839).read == pytest.approx(479.875)

    def test_other_timeout_arms_stay_at_the_shared_defaults(self) -> None:
        scaled = client_mod._complete_timeout(100_000)
        assert scaled.connect == client_mod._TIMEOUT.connect
        assert scaled.write == client_mod._TIMEOUT.write
        assert scaled.pool == client_mod._TIMEOUT.pool

    async def test_non_streaming_call_carries_the_scaled_read_timeout(self, monkeypatch) -> None:
        """complete() must actually pass the scaled timeout to the HTTP client
        (the wire contract, not just the helper's arithmetic)."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "model": "m",
                },
            )

        real = TestMessageTranslation._real_client

        def spy(**kw):
            seen["timeout"] = kw["timeout"]
            return real(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(client_mod.httpx, "AsyncClient", spy)
        await client_mod.complete(
            TestMessageTranslation._ANTHROPIC,
            api_key="sk",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=2000,
        )
        assert seen["timeout"].read == 250.0


class TestMaxOutputTokensSetting:
    """0 = caller omitted the cap: the wire max_tokens falls back to the
    llm.max_output_tokens setting (user-configured) instead of a hardcoded
    transport default; an explicit caller value always wins."""

    @staticmethod
    def _fake_result(model: str) -> Any:
        import types

        return types.SimpleNamespace(
            text="pong",
            model=model,
            tool_calls=[],
            input_tokens=3,
            output_tokens=1,
            cached_tokens=0,
            reasoning="",
            thinking_blocks=[],
            reasoning_tokens=0,
            cache_write_tokens=0,
            meta=types.SimpleNamespace(to_dict=dict),
        )

    async def test_unset_falls_back_and_setting_wins(self, deps, monkeypatch) -> None:
        import llm.capabilities.complete as complete_mod
        from llm.capabilities.common import Deps, init_deps, require_deps

        pid = await _add_sample()
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk-x"})
        seen: dict = {}

        async def fake_complete(p, *, api_key, model, max_tokens, **kw):
            seen["max_tokens"] = max_tokens
            return self._fake_result(model)

        monkeypatch.setattr(complete_mod, "llm_complete", fake_complete)

        # No setting wired: built-in fallback (was the old hardcoded default).
        await execute(
            registry,
            "complete",
            AGENT_CTX,
            {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert seen["max_tokens"] == 4096

        # Setting present: the user's value is the default.
        cur = require_deps()

        class _Settings:
            def get(self, key: str) -> int:
                return 7777

        init_deps(Deps(store=cur.store, secrets=cur.secrets, settings=_Settings()))
        await execute(
            registry,
            "complete",
            AGENT_CTX,
            {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert seen["max_tokens"] == 7777

        # Explicit caller value wins over the setting.
        await execute(
            registry,
            "complete",
            AGENT_CTX,
            {
                "provider_id": pid,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 123,
            },
        )
        assert seen["max_tokens"] == 123

    async def test_dirty_setting_falls_back(self, deps, monkeypatch) -> None:
        from llm.capabilities.common import Deps, init_deps, require_deps

        class _Dirty:
            def get(self, key: str) -> Any:
                return "not-a-number"

        cur = require_deps()
        init_deps(Deps(store=cur.store, secrets=cur.secrets, settings=_Dirty()))
        from llm.capabilities.common import configured_max_output_tokens

        assert configured_max_output_tokens() == 4096

        class _Zero:
            def get(self, key: str) -> int:
                return 0

        init_deps(Deps(store=cur.store, secrets=cur.secrets, settings=_Zero()))
        assert configured_max_output_tokens() == 4096


class TestMultimodalListContent:
    """List content (the neutral protocol's multi-modal part list) must never
    reach the anthropic / responses encoders as Python repr garbage or crash
    them: those two formats degrade part lists to their text projection, while
    chat keeps forwarding the list structurally (vision models)."""

    _PARTS: ClassVar[list] = [
        {"type": "text", "text": "看看这张图:"},
        {"type": "image_url", "image_url": {"url": "https://example.test/x.png"}},
        {"type": "text", "text": "描述一下"},
    ]

    def _history(self) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": [{"type": "text", "text": "You are an assistant."}]},
            {"role": "user", "content": self._PARTS},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "收到"}],
                "tool_calls": [{"id": "c1", "name": "look", "arguments": {"u": "x"}}],
            },
            {
                "role": "tool",
                "tool_call_id": "c1",
                "name": "look",
                "content": [{"type": "text", "text": "画面里有猫"}],
            },
        ]

    async def test_anthropic_encodes_text_projection(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"content": [{"type": "text", "text": "ok"}], "usage": {}}
            )

        real = httpx.AsyncClient
        monkeypatch.setattr(
            client_mod.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )
        await client_mod.complete(
            TestMessageTranslation._ANTHROPIC,
            api_key="sk",
            model="m",
            messages=self._history(),
        )
        body = seen["body"]
        assert body["system"] == "You are an assistant."
        wire = json.dumps(body["messages"], ensure_ascii=False)
        # Text members survive as real text...
        assert "看看这张图:" in wire and "画面里有猫" in wire and "收到" in wire
        # ...never as Python repr of the part list
        assert "'type':" not in wire and "image_url" not in wire

    async def test_responses_encodes_text_projection(self) -> None:
        from llm.wire_responses import responses_input

        instructions, items = responses_input(self._history())
        assert instructions == "You are an assistant."
        blob = json.dumps(items, ensure_ascii=False)
        assert "看看这张图:" in blob and "画面里有猫" in blob
        assert "image_url" not in blob

    async def test_chat_keeps_list_content_structural(self, monkeypatch) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "ok"}}], "usage": {}, "model": "m"},
            )

        real = httpx.AsyncClient
        monkeypatch.setattr(
            client_mod.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )
        await client_mod.complete(
            TestMessageTranslation._CHAT,
            api_key="sk",
            model="m",
            messages=[{"role": "user", "content": self._PARTS}],
        )
        (msg,) = seen["body"]["messages"]
        assert isinstance(msg["content"], list)
        assert msg["content"][1]["type"] == "image_url"

    def test_duplicate_tool_call_ids_made_unique(self) -> None:
        """A compat provider echoing the same id on two calls would replay
        duplicate tool_use ids in the history, which strict endpoints reject
        on every later round; the duplicate is renamed at parse time and the
        empty id stays empty (it degrades downstream)."""
        calls = client_mod._parse_tool_calls(
            [
                {"id": "call_0", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_0", "function": {"name": "b", "arguments": "{}"}},
                {"id": "", "function": {"name": "c", "arguments": "{}"}},
                {"id": "call_0_dup", "function": {"name": "d", "arguments": "{}"}},
            ]
        )
        assert [c["id"] for c in calls] == ["call_0", "call_0_dup", "", "call_0_dup_dup"]
        assert [c["name"] for c in calls] == ["a", "b", "c", "d"]
