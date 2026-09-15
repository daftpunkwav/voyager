"""ServiceLLM streaming adapter tests: chunk mapping, degradation, error
propagation.

The call stub returns an async generator (the real shape produced via the
capability framework's execute) without touching the network.
"""

from collections.abc import AsyncIterator

import pytest
from agent.llm import ToolSpec
from host.llm_adapter import ServiceLLM
from platform_contracts import ServiceError


def _stream_llm(chunks: list[dict]) -> ServiceLLM:
    """An explicit provider_id short-circuits provider resolution; the call stub
    only answers complete_stream."""

    async def call(domain: str, name: str, args: dict) -> object:
        assert domain == "llm" and name == "complete_stream"

        async def _gen() -> AsyncIterator[dict]:
            for c in chunks:
                yield c

        return _gen()

    return ServiceLLM(call, provider_id="p1", model="m")


async def _drain(llm, *args, **kw) -> list:
    return [ev async for ev in llm.complete_stream(*args, **kw)]


class TestServiceLLMStream:
    async def test_chunks_mapped_to_stream_reply(self) -> None:
        llm = _stream_llm(
            [
                {"type": "text", "text": "hel"},
                {"type": "text", "text": "lo"},
                {
                    "type": "final",
                    "text": "hello",
                    "tool_calls": [],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                    "model": "m",
                },
            ]
        )
        events = await _drain(llm, [{"role": "user", "content": "hi"}])
        assert [(e.text_delta, e.final) for e in events] == [
            ("hel", None),
            ("lo", None),
            ("", events[-1].final),
        ]
        final = events[-1].final
        assert final.text == "hello"
        assert final.usage.input_tokens == 3 and final.usage.output_tokens == 2

    async def test_tool_calls_in_final(self) -> None:
        llm = _stream_llm(
            [
                {
                    "type": "final",
                    "text": "",
                    "tool_calls": [{"id": "c1", "name": "t", "arguments": {"x": 1}}],
                    "usage": {},
                    "model": "m",
                },
            ]
        )
        events = await _drain(llm, [], tools=[ToolSpec(name="t", description="d")])
        final = events[-1].final
        assert not events[0].text_delta
        assert final.tool_calls[0].name == "t"
        assert final.tool_calls[0].arguments == {"x": 1}

    async def test_reasoning_in_final(self) -> None:
        llm = _stream_llm(
            [
                {"type": "reasoning", "text": "weigh"},
                {
                    "type": "final",
                    "text": "hello",
                    "reasoning": "weigh",
                    "thinking_blocks": [
                        {"type": "thinking", "thinking": "weigh", "signature": "s"}
                    ],
                    "tool_calls": [],
                    "usage": {},
                    "model": "m",
                },
            ]
        )
        events = await _drain(llm, [{"role": "user", "content": "hi"}])
        # Live reasoning chunks do not leak into the answer text stream.
        assert [e.text_delta for e in events] == ["", ""]
        assert events[0].reasoning_delta == "weigh"
        final = events[-1].final
        assert final.text == "hello"
        assert final.reasoning == "weigh"
        assert final.thinking_blocks == (
            {"type": "thinking", "thinking": "weigh", "signature": "s"},
        )

    async def test_call_error_degrades_to_final_text(self) -> None:
        """Call-time errors (guard rejection/unconfigured): degrade to a final
        readable reply, same semantics as complete."""
        from platform_contracts import ErrorSuffix

        async def call(domain: str, name: str, args: dict) -> object:
            raise ServiceError("llm", ErrorSuffix.INVALID_INPUT, "api key not configured")

        llm = ServiceLLM(call, provider_id="p1", model="m")
        events = await _drain(llm, [{"role": "user", "content": "hi"}])
        assert len(events) == 1
        assert "api key not configured" in events[0].final.text

    async def test_consumption_error_propagates(self) -> None:
        """Consumption-time errors (deltas already produced): propagate as-is,
        no degradation."""

        async def call(domain: str, name: str, args: dict) -> object:
            async def _gen() -> AsyncIterator[dict]:
                yield {"type": "text", "text": "partial"}
                raise RuntimeError("stream broken")

            return _gen()

        llm = ServiceLLM(call, provider_id="p1", model="m")
        with pytest.raises(RuntimeError):
            await _drain(llm, [{"role": "user", "content": "hi"}])

    async def test_tools_serialized_to_service_shape(self) -> None:
        seen: dict = {}

        async def call(domain: str, name: str, args: dict) -> object:
            seen["args"] = args

            async def _gen() -> AsyncIterator[dict]:
                yield {"type": "final", "text": "ok", "tool_calls": [], "usage": {}}

            return _gen()

        llm = ServiceLLM(call, provider_id="p1", model="m")
        await _drain(
            llm,
            [{"role": "user", "content": "hi"}],
            tools=[ToolSpec(name="t", description="d", schema={"type": "object"})],
        )
        assert seen["args"]["tools"] == [
            {"name": "t", "description": "d", "schema": {"type": "object"}}
        ]
