"""ServiceLLM tests: complete capability result -> LLMReply mapping and the
degradation paths.
"""

from typing import Any

from agent.llm import ToolSpec
from host.llm_adapter import ServiceLLM
from platform_contracts import CONTEXT_OVERFLOW_HINT, ErrorSuffix, ServiceError

MSGS = [{"role": "user", "content": "hi"}]
TOOLS = [ToolSpec(name="t", description="d", schema={"type": "object"})]


def _call_with_provider(reply: dict, calls: list):
    async def call(domain: str, name: str, args: dict) -> Any:
        calls.append((domain, name, args))
        if name == "list_providers":
            return [{"id": "p1", "enabled": True, "has_api_key": True, "models": ["m9"]}]
        return reply

    return call


class TestMapping:
    async def test_reply_with_tool_calls(self) -> None:
        calls: list = []
        llm = ServiceLLM(
            _call_with_provider(
                {
                    "text": "",
                    "model": "m9",
                    "tool_calls": [{"id": "c1", "name": "t", "arguments": {"a": 1}}],
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                },
                calls,
            )
        )
        reply = await llm.complete(MSGS, tools=TOOLS)
        assert reply.final is False
        assert reply.tool_calls[0].id == "c1"
        assert reply.tool_calls[0].arguments == {"a": 1}
        assert (reply.usage.input_tokens, reply.usage.output_tokens) == (2, 3)
        # complete call arguments: first usable provider auto-selected, tools
        # converted to dict form
        domain, name, args = calls[-1]
        assert (domain, name) == ("llm", "complete")
        assert args["provider_id"] == "p1" and args["model"] == "m9"
        assert args["tools"] == [{"name": "t", "description": "d", "schema": {"type": "object"}}]

    async def test_reply_text_only(self) -> None:
        llm = ServiceLLM(
            _call_with_provider(
                {
                    "text": "ok.",
                    "tool_calls": [],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
                [],
            )
        )
        reply = await llm.complete(MSGS)
        assert reply.final is True and reply.text == "ok."

    async def test_reasoning_and_thinking_blocks_mapped(self) -> None:
        llm = ServiceLLM(
            _call_with_provider(
                {
                    "text": "ok.",
                    "tool_calls": [],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "reasoning": "why this works",
                    "thinking_blocks": [
                        {"type": "thinking", "thinking": "why this works", "signature": "s"},
                        "junk",
                    ],
                },
                [],
            )
        )
        reply = await llm.complete(MSGS)
        assert reply.reasoning == "why this works"
        assert reply.thinking_blocks == (
            {"type": "thinking", "thinking": "why this works", "signature": "s"},
        )


class TestDegraded:
    async def test_no_provider_readable_reply(self) -> None:
        async def call(domain: str, name: str, args: dict) -> list:
            return []  # no configured providers at all

        llm = ServiceLLM(call)
        reply = await llm.complete(MSGS)
        assert reply.final is True
        assert reply.degraded is True
        assert "LLM" in (reply.text or "")

    async def test_provider_error_degrades_to_text(self) -> None:
        async def call(domain: str, name: str, args: dict) -> Any:
            if name == "list_providers":
                return [{"id": "p1", "enabled": True, "has_api_key": True, "models": ["m9"]}]
            raise ServiceError("llm", ErrorSuffix.UNAVAILABLE, "connection timed out")

        llm = ServiceLLM(call)
        reply = await llm.complete(MSGS)
        assert reply.final is True
        assert "LLM call failed" in (reply.text or "")

    async def test_overflow_hint_marks_reply(self) -> None:
        """The llm domain's CONTEXT_OVERFLOW_HINT on the ServiceError maps to
        LLMReply.overflow, driving the ReAct loop's compact-and-retry."""

        async def call(domain: str, name: str, args: dict) -> Any:
            if name == "list_providers":
                return [{"id": "p1", "enabled": True, "has_api_key": True, "models": ["m9"]}]
            raise ServiceError(
                "llm",
                ErrorSuffix.INVALID_INPUT,
                "LLM call failed: too long",
                hint=CONTEXT_OVERFLOW_HINT,
            )

        llm = ServiceLLM(call)
        reply = await llm.complete(MSGS)
        assert reply.degraded is True and reply.overflow is True

        async def plain_call(domain: str, name: str, args: dict) -> Any:
            if name == "list_providers":
                return [{"id": "p1", "enabled": True, "has_api_key": True, "models": ["m9"]}]
            raise ServiceError("llm", ErrorSuffix.INVALID_INPUT, "bad input")

        plain = ServiceLLM(plain_call)
        reply = await plain.complete(MSGS)
        assert reply.degraded is True and reply.overflow is False


class TestDefaultProvider:
    """The llm.default_provider setting wins (when usable); otherwise fall back
    to the first usable provider."""

    @staticmethod
    def _call_with_default(providers: list[dict], default_id: str, calls: list):
        async def call(domain: str, name: str, args: dict) -> Any:
            calls.append((domain, name, args))
            if name == "get_setting":
                return {"key": "llm.default_provider", "value": default_id}
            if name == "complete":
                return {"text": "ok", "tool_calls": [], "usage": {}}
            return providers  # list_providers

        return call

    async def test_setting_default_provider_wins(self) -> None:
        calls: list = []
        providers = [
            {"id": "p1", "enabled": True, "has_api_key": True, "models": ["m1"]},
            {"id": "p2", "enabled": True, "has_api_key": True, "models": ["m2"]},
        ]
        llm = ServiceLLM(self._call_with_default(providers, "p2", calls))
        reply = await llm.complete(MSGS)
        assert reply.text == "ok"
        domain, name, args = calls[-1]
        assert (domain, name) == ("llm", "complete")
        assert args["provider_id"] == "p2"  # with a default set, use it, not the first

    async def test_fallback_when_default_unusable(self) -> None:
        """When the default points at a disabled/keyless provider, fall back to
        the first usable one without raising or emitting the degraded sentence."""
        calls: list = []
        providers = [
            {"id": "p1", "enabled": True, "has_api_key": True, "models": ["m1"]},
            {"id": "p2", "enabled": False, "has_api_key": True, "models": ["m2"]},
        ]
        llm = ServiceLLM(self._call_with_default(providers, "p2", calls))
        await llm.complete(MSGS)
        assert calls[-1][2]["provider_id"] == "p1"

    async def test_fallback_when_setting_read_fails(self) -> None:
        async def call(domain: str, name: str, args: dict) -> Any:
            if name == "get_setting":
                raise ServiceError("settings", ErrorSuffix.NOT_FOUND, "unknown setting")
            if name == "complete":
                return {"text": "ok", "tool_calls": [], "usage": {}}
            return [
                {"id": "p1", "enabled": True, "has_api_key": True, "models": ["m1"]}
            ]  # list_providers

        calls: list = []

        async def wrapped(domain: str, name: str, args: dict) -> dict:
            calls.append((domain, name, args))
            return await call(domain, name, args)

        llm = ServiceLLM(wrapped)
        await llm.complete(MSGS)
        assert calls[-1][2]["provider_id"] == "p1"  # failure is readable, agent loop keeps going
