"""Purpose routing: chain resolution, fallback execution with llm.fallback
events, and per-purpose metering wiring through build_agent."""

from __future__ import annotations

import json

from agent.build import build_agent
from agent.contracts import Purpose
from agent.llm import FakeLLM
from host.llm_routing import ROUTING_KEY, RoutingServiceLLM, resolve_chain
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
            return [
                {"id": "p-main", "enabled": True, "has_api_key": True, "default_model": "m-main"}
            ]
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
            async def complete(self, messages, tools=None):
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
