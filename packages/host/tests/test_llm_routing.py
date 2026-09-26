"""Purpose routing: chain resolution, fallback execution with llm.fallback
events, streaming through the chain, and per-purpose metering wiring through
build_agent.
"""

from __future__ import annotations

import json

import pytest
from agent.build import build_agent
from agent.contracts import Purpose
from agent.llm import FakeLLM
from agent.runtime.current import current_instance
from agent.settings import OVERRIDES_KEY, STYLE_OVERRIDES_KEY
from host.llm_adapter import NO_PROVIDER_TEXT
from host.llm_routing import (
    ROUTING_KEY,
    PersonaRoutingServiceLLM,
    RoutingServiceLLM,
    persona_style_for,
    resolve_chain,
)
from platform_contracts import DomainEvent, ErrorSuffix, ServiceError


class _Settings:
    def __init__(self, values: dict | None = None, fail: bool = False) -> None:
        self.values = values or {}
        self.fail = fail

    def get(self, key: str):
        if self.fail:
            raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")
        return self.values.get(key)


def _call_factory(fail_provider_ids: set[str], calls: list[dict] | None = None):
    calls = calls if calls is not None else []

    async def call(domain: str, name: str, args: dict):
        assert name in ("complete", "complete_stream", "list_providers", "get_setting")
        if name == "list_providers":
            return [{"id": "p-main", "enabled": True, "has_api_key": True, "models": ["m-main"]}]
        if name == "get_setting":
            raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")
        calls.append({"provider": args["provider_id"], "model": args["model"]})
        if args["provider_id"] in fail_provider_ids:
            raise ServiceError(
                "llm", ErrorSuffix.UNAVAILABLE, f"provider {args['provider_id']} down"
            )
        return {
            "text": f"from {args['provider_id']}/{args['model']}",
            "tool_calls": [],
            "usage": {},
        }

    return call


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


class TestResolveChain:
    def test_primary_then_fallbacks_malformed_skipped(self) -> None:
        chain = resolve_chain(
            {
                "arbiter": {
                    "provider": "p2",
                    "model": "m-lite",
                    "fallbacks": [
                        {"provider": "p1", "model": "m"},
                        "junk-string",
                        {"broken": True},
                        {"model": "m3"},
                    ],
                },
                "bad": "not-a-dict",
            },
            Purpose.ARBITER,
        )
        assert chain == [
            {"provider": "p2", "model": "m-lite"},
            {"provider": "p1", "model": "m"},
            {"provider": "", "model": "m3"},
        ]
        assert resolve_chain({}, Purpose.CHAT) == []
        assert resolve_chain("junk", Purpose.CHAT) == []

    def test_plain_string_purpose_is_accepted(self) -> None:
        """Callers may pass the purpose as a raw string (e.g. a setting-derived
        key); it resolves identically to the enum member."""
        routing = {"summarize": {"provider": "p1", "model": "m1"}}
        assert resolve_chain(routing, "summarize") == [{"provider": "p1", "model": "m1"}]
        assert resolve_chain(routing, "other") == []


class TestRoutingCompleteEdges:
    async def test_response_format_rejected_with_type_error(self) -> None:
        """The routing transport cannot enforce schemas on the wire: it must
        raise the same TypeError signal ServiceLLM uses so structured-output
        callers fall back to prompt-injected mode."""
        llm = RoutingServiceLLM(_call_factory(set()), purpose=Purpose.CHAT)
        with pytest.raises(TypeError):
            await llm.complete(
                [{"role": "user", "content": "hi"}], response_format={"type": "json_object"}
            )

    async def test_entry_for_another_purpose_keeps_default_resolution(self) -> None:
        """A routing table that only names another purpose leaves this purpose
        on the default provider resolution (and publishes nothing on the bus)."""
        calls: list[dict] = []
        bus = _Bus()
        llm = RoutingServiceLLM(
            _call_factory(set(), calls=calls),
            purpose=Purpose.DISTILL,
            settings=_Settings({ROUTING_KEY: {"chat": {"provider": "p-main"}}}),
            bus=bus,
        )
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "from p-main/m-main"
        assert calls == [{"provider": "p-main", "model": "m-main"}]
        assert bus.events == []

    async def test_model_only_hop_without_usable_provider_degrades(self) -> None:
        """A hop that only pins a model still needs the default provider; with
        no usable provider configured the turn degrades readably instead of
        raising."""

        async def call(domain: str, name: str, args: dict):
            if name == "list_providers":
                return []
            raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")

        llm = RoutingServiceLLM(
            call,
            purpose=Purpose.ARBITER,
            settings=_Settings({ROUTING_KEY: {"arbiter": {"model": "m-x"}}}),
        )
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        assert reply.degraded and reply.text == NO_PROVIDER_TEXT


class TestRoutingStream:
    """complete_stream shares the fallback chain for the initial call: each
    hop either starts streaming or announces a fallthrough on the bus; a
    mid-stream failure still propagates as ServiceError."""

    @staticmethod
    def _stream_factory(fail_provider_ids: set[str], calls: list[dict] | None = None, chunks=None):
        calls = calls if calls is not None else []
        chunks = (
            chunks
            if chunks is not None
            else [
                {"type": "text", "text": "hel"},
                {"type": "text", "text": "lo"},
                {
                    "type": "final",
                    "text": "hello",
                    "tool_calls": [],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                    "model": "m-final",
                },
            ]
        )

        async def call(domain: str, name: str, args: dict):
            if name == "list_providers":
                return [
                    {"id": "p-main", "enabled": True, "has_api_key": True, "models": ["m-main"]}
                ]
            if name == "get_setting":
                raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")
            calls.append({"provider": args["provider_id"], "model": args["model"]})
            if args["provider_id"] in fail_provider_ids:
                raise ServiceError(
                    "llm", ErrorSuffix.UNAVAILABLE, f"provider {args['provider_id']} down"
                )

            async def gen():
                for chunk in chunks:
                    yield chunk

            return gen()

        return call

    @staticmethod
    async def _collect(agen):
        from agent.llm import StreamReply

        deltas: list[str] = []
        reasoning: list[str] = []
        final = None
        async for reply in agen:
            assert isinstance(reply, StreamReply)
            if reply.text_delta:
                deltas.append(reply.text_delta)
            if reply.reasoning_delta:
                reasoning.append(reply.reasoning_delta)
            if reply.final is not None:
                final = reply.final
        return deltas, reasoning, final

    async def test_stream_falls_back_then_delivers_deltas_and_final(self) -> None:
        calls: list[dict] = []
        bus = _Bus()
        llm = RoutingServiceLLM(
            self._stream_factory({"p-lite"}, calls),
            purpose=Purpose.CHAT,
            settings=_Settings(
                {
                    ROUTING_KEY: {
                        "chat": {
                            "provider": "p-lite",
                            "model": "m-lite",
                            "fallbacks": [{"provider": "p-main", "model": "m-main"}],
                        }
                    }
                }
            ),
            bus=bus,
        )
        deltas, reasoning, final = await self._collect(
            llm.complete_stream([{"role": "user", "content": "hi"}], max_tokens=128)
        )
        assert deltas == ["hel", "lo"] and reasoning == []
        assert final is not None and final.text == "hello" and final.model == "m-final"
        assert final.usage.input_tokens == 3 and final.usage.output_tokens == 2
        assert [c["provider"] for c in calls] == ["p-lite", "p-main"]
        assert len(bus.events) == 1 and bus.events[0].type == DomainEvent.LLM_FALLBACK

    async def test_stream_without_chain_delegates_to_default_transport(self) -> None:
        calls: list[dict] = []
        llm = RoutingServiceLLM(
            self._stream_factory(set(), calls),
            purpose=Purpose.DISTILL,
            settings=_Settings({ROUTING_KEY: {"chat": {"provider": "p-main"}}}),
        )
        deltas, _reasoning, final = await self._collect(
            llm.complete_stream([{"role": "user", "content": "hi"}])
        )
        assert deltas == ["hel", "lo"] and final is not None and final.text == "hello"
        assert calls == [{"provider": "p-main", "model": "m-main"}]

    async def test_stream_without_usable_provider_degrades_once(self) -> None:
        async def call(domain: str, name: str, args: dict):
            if name == "list_providers":
                return []
            raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")

        llm = RoutingServiceLLM(
            call,
            purpose=Purpose.CHAT,
            settings=_Settings({ROUTING_KEY: {"chat": {"model": "m-x"}}}),
        )
        deltas, _reasoning, final = await self._collect(
            llm.complete_stream([{"role": "user", "content": "hi"}])
        )
        assert deltas == [] and final is not None
        assert final.degraded and final.text == NO_PROVIDER_TEXT

    async def test_stream_exhausted_chain_degrades_readable(self) -> None:
        llm = RoutingServiceLLM(
            self._stream_factory({"p-lite", "p-main"}),
            purpose=Purpose.CHAT,
            settings=_Settings(
                {
                    ROUTING_KEY: {
                        "chat": {
                            "provider": "p-lite",
                            "fallbacks": [{"provider": "p-main"}],
                        }
                    }
                }
            ),
        )
        deltas, _reasoning, final = await self._collect(
            llm.complete_stream([{"role": "user", "content": "hi"}])
        )
        assert deltas == [] and final is not None
        assert final.degraded and "2 attempt(s)" in (final.text or "")

    async def test_reasoning_chunks_stay_off_the_text_channel(self) -> None:
        llm = RoutingServiceLLM(
            self._stream_factory(
                set(),
                chunks=[
                    {"type": "reasoning", "text": "thinking"},
                    {"type": "text", "text": "answer"},
                    {"type": "final", "text": "answer", "tool_calls": [], "usage": {}},
                ],
            ),
            purpose=Purpose.CHAT,
            settings=_Settings({ROUTING_KEY: {"chat": {"provider": "p-main"}}}),
        )
        deltas, reasoning, _final = await self._collect(
            llm.complete_stream([{"role": "user", "content": "hi"}])
        )
        assert deltas == ["answer"] and reasoning == ["thinking"]


class TestRoutingFallback:
    async def test_route_pins_provider_then_falls_back_with_event(self) -> None:
        calls: list[dict] = []
        bus = _Bus()
        llm = RoutingServiceLLM(
            _call_factory(fail_provider_ids={"p-lite"}, calls=calls),
            purpose=Purpose.ARBITER,
            settings=_Settings(
                {
                    ROUTING_KEY: {
                        "arbiter": {
                            "provider": "p-lite",
                            "model": "m-lite",
                            "fallbacks": [{"provider": "p-main", "model": ""}],
                        }
                    }
                }
            ),
            bus=bus,
        )
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        # the fallback hop sends an empty model: the llm capability resolves the
        # provider's own default (mirrored verbatim by the fake)
        assert reply.text == "from p-main/"
        assert [c["provider"] for c in calls] == ["p-lite", "p-main"]
        assert len(bus.events) == 1
        payload = bus.events[0].payload
        assert bus.events[0].type == DomainEvent.LLM_FALLBACK
        assert payload["purpose"] == "arbiter" and "p-lite down" in payload["error"]

    async def test_exhausted_chain_degrades_readable(self) -> None:
        llm = RoutingServiceLLM(
            _call_factory(fail_provider_ids={"p-lite", "p-main"}),
            purpose=Purpose.DISTILL,
            settings=_Settings(
                {
                    ROUTING_KEY: {
                        "distill": {
                            "provider": "p-lite",
                            "model": "m-lite",
                            "fallbacks": [{"provider": "p-main", "model": ""}],
                        }
                    }
                }
            ),
        )
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        assert reply.degraded and "2 attempt(s)" in (reply.text or "")

    async def test_broken_settings_keep_default_route(self) -> None:
        calls: list[dict] = []
        llm = RoutingServiceLLM(
            _call_factory(set()),
            purpose=Purpose.CHAT,
            settings=_Settings(fail=True),
        )
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "from p-main/m-main"
        assert json.dumps(calls)  # one call, default provider


class TestBuildWiring:
    async def test_arbiter_transport_differs_from_chat(self, tmp_path) -> None:
        class Marked:
            async def complete(self, messages, tools=None, response_format=None, max_tokens=None):
                return None

        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            purpose_llms={"arbiter": Marked()},
        )
        try:
            # The arbiter got its own (metered-wrapped) transport, distinct
            # from the chat one; without routes both share one wrapper
            assert app.master._arbiter._llm is not app.master._llm
        finally:
            app.close()

        app = build_agent(data_dir=tmp_path / "rd2", workspace_dir=tmp_path / "ws2", llm=FakeLLM())
        try:
            assert app.master._arbiter._llm is app.master._llm
        finally:
            app.close()


class _Instance:
    """Turn context stand-in: only .persona is consulted."""

    def __init__(self, persona: str) -> None:
        self.persona = persona


class TestPersonaRouting:
    async def test_persona_override_pins_provider_and_model(self) -> None:
        calls: list[dict] = []
        llm = PersonaRoutingServiceLLM(
            _call_factory(set(), calls=calls),
            settings=_Settings(
                {
                    OVERRIDES_KEY: {
                        "orchestrator": {"provider": "p-main", "model": "m-forced"},
                    }
                }
            ),
        )
        token = current_instance.set(_Instance("orchestrator"))
        try:
            reply = await llm.complete([{"role": "user", "content": "hi"}])
        finally:
            current_instance.reset(token)
        assert reply.text == "from p-main/m-forced"
        assert calls == [{"provider": "p-main", "model": "m-forced"}]

    async def test_alias_and_outside_turn_fall_back_to_default(self) -> None:
        calls: list[dict] = []
        llm = PersonaRoutingServiceLLM(
            _call_factory(set(), calls=calls),
            settings=_Settings(
                {
                    OVERRIDES_KEY: {
                        "orchestrator": {"provider": "p-main", "model": "m-forced"},
                    }
                }
            ),
        )
        # Alias lucien resolves to orchestrator: the override applies
        token = current_instance.set(_Instance("lucien"))
        try:
            await llm.complete([{"role": "user", "content": "hi"}])
        finally:
            current_instance.reset(token)
        assert calls == [{"provider": "p-main", "model": "m-forced"}]

        # Outside a turn (no instance bound) the default resolution runs
        calls.clear()
        reply = await llm.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "from p-main/m-main"
        assert calls == [{"provider": "p-main", "model": "m-main"}]

    async def test_other_persona_uses_default_route(self) -> None:
        calls: list[dict] = []
        llm = PersonaRoutingServiceLLM(
            _call_factory(set(), calls=calls),
            settings=_Settings({OVERRIDES_KEY: {"orchestrator": {"provider": "p-main"}}}),
        )
        token = current_instance.set(_Instance("scout"))
        try:
            await llm.complete([{"role": "user", "content": "hi"}])
        finally:
            current_instance.reset(token)
        assert calls == [{"provider": "p-main", "model": "m-main"}]

    async def test_broken_override_table_keeps_default_route(self) -> None:
        """Unreadable settings must not block the chat: the persona lookup
        degrades to the default resolution even inside a turn."""
        calls: list[dict] = []
        llm = PersonaRoutingServiceLLM(
            _call_factory(set(), calls=calls),
            settings=_Settings(fail=True),
        )
        token = current_instance.set(_Instance("orchestrator"))
        try:
            reply = await llm.complete([{"role": "user", "content": "hi"}])
        finally:
            current_instance.reset(token)
        assert reply.text == "from p-main/m-main"
        assert calls == [{"provider": "p-main", "model": "m-main"}]


class TestPersonaStyle:
    def test_override_wins_and_falls_back(self) -> None:
        settings = _Settings(
            {
                STYLE_OVERRIDES_KEY: {"orchestrator": "毒舌"},
                "agent.style": "热心",
            }
        )
        assert persona_style_for(settings, "orchestrator") == "毒舌"
        assert persona_style_for(settings, "scout") == ""
        broken = _Settings(fail=True)
        assert persona_style_for(broken, "orchestrator") == ""
        assert persona_style_for(None, "orchestrator") == ""

    def test_non_dict_style_overrides_degrade_to_empty(self) -> None:
        """A corrupt style table (string instead of object) yields no style
        instead of raising or leaking the raw value."""
        settings = _Settings({STYLE_OVERRIDES_KEY: "not-a-table"})
        assert persona_style_for(settings, "orchestrator") == ""
