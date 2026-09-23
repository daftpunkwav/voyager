"""Tests for the output-cap wrapper: the configured per-model wire max_tokens
is injected into every LLM call; caller-passed values win; inner clients
without streaming keep the probe chain intact."""

from typing import Any

import pytest
from agent.llm import FakeLLM, LLMReply, StreamReply
from agent.runtime.llm_output_cap import output_capped_llm


class _Settings:
    """Duck-typed settings reader; unregistered keys raise like the store."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def get(self, key: str) -> Any:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


def _chat_settings(**overrides: Any) -> _Settings:
    values: dict[str, Any] = {
        "agent.context.window_tokens": 200_000,
        "agent.context.max_output_tokens": 64_000,
        "agent.context.model_profiles": {},
        "agent.llm.model": "",
        "llm.default_model": "",
    }
    values.update(overrides)
    return _Settings(values)


class _RecordingLLM:
    """Minimal inner client recording the max_tokens it received on both the
    complete and the complete_stream path."""

    def __init__(self, *, model: str = "") -> None:
        self.model = model
        self.seen: list[int | None] = []
        self.stream_seen: list[int | None] = []

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: Any = None,
        response_format: Any = None,
        max_tokens: int | None = None,
    ) -> LLMReply:
        self.seen.append(max_tokens)
        return LLMReply(text="ok")

    def complete_stream(
        self, messages: list[dict[str, Any]], tools: Any = None, max_tokens: int | None = None
    ) -> Any:
        self.stream_seen.append(max_tokens)

        async def _gen() -> Any:
            yield StreamReply(text_delta="ok")
            yield StreamReply(final=LLMReply(text="ok"))

        return _gen()


@pytest.mark.asyncio
async def test_profile_cap_injected() -> None:
    """The model's profile max_output rides the call; settings resolve per
    call so hot changes apply from the next one."""
    inner = _RecordingLLM(model="glm-5.3-flash")
    settings = _chat_settings(
        **{
            "agent.context.model_profiles": {
                "glm-5.3-flash": {"window_tokens": 1_000_000, "max_output_tokens": 128_000}
            }
        }
    )
    llm = output_capped_llm(inner, settings)  # type: ignore[arg-type]
    await llm.complete([{"role": "user", "content": "hi"}])
    assert inner.seen == [128_000]


@pytest.mark.asyncio
async def test_global_default_when_no_profile() -> None:
    inner = _RecordingLLM()
    llm = output_capped_llm(inner, _chat_settings())  # type: ignore[arg-type]
    await llm.complete([{"role": "user", "content": "hi"}])
    assert inner.seen == [64_000]


@pytest.mark.asyncio
async def test_explicit_max_tokens_wins() -> None:
    inner = _RecordingLLM()
    llm = output_capped_llm(inner, _chat_settings())  # type: ignore[arg-type]
    await llm.complete([{"role": "user", "content": "hi"}], max_tokens=555)
    assert inner.seen == [555]


@pytest.mark.asyncio
async def test_stream_cap_injected_and_explicit_wins() -> None:
    """complete_stream carries the same resolution: the configured cap rides
    the streaming call (the chat page's default path), an explicit caller
    value wins, and the wrapper still yields the inner stream's events."""
    inner = _RecordingLLM()
    llm = output_capped_llm(inner, _chat_settings())  # type: ignore[arg-type]
    # LLMClient's static type omits the streaming tier on purpose: probe the
    # attribute like production callers do (a missing attribute fails the
    # test, which is exactly the exposure contract under test).
    stream_call = getattr(llm, "complete_stream")
    chunks = [ev async for ev in stream_call([{"role": "user", "content": "hi"}])]
    assert inner.stream_seen == [64_000]
    assert [c.text_delta or (c.final.text if c.final else "") for c in chunks] == ["ok", "ok"]

    inner2 = _RecordingLLM()
    llm2 = output_capped_llm(inner2, _chat_settings())  # type: ignore[arg-type]
    stream_call2 = getattr(llm2, "complete_stream")
    _ = [ev async for ev in stream_call2([{"role": "user", "content": "hi"}], max_tokens=42)]
    assert inner2.stream_seen == [42]


@pytest.mark.asyncio
async def test_resolution_failure_degrades_to_no_injection() -> None:
    """A broken settings reader must not block the call: no cap is injected
    and the llm domain's setting-backed default applies instead."""

    class _Broken:
        def get(self, key: str) -> Any:
            raise KeyError(key)

    inner = _RecordingLLM()
    llm = output_capped_llm(inner, _Broken())  # type: ignore[arg-type]
    reply = await llm.complete([{"role": "user", "content": "hi"}])
    assert reply.text == "ok"
    assert inner.seen == [None]


@pytest.mark.asyncio
async def test_chat_model_fallback_for_attrless_clients() -> None:
    """ServiceLLM exposes no .model attr: the composer chat model setting
    drives the profile lookup (the host-served path)."""

    class _Attrless:
        """No model attribute at all (getattr falls through to settings)."""

        def __init__(self) -> None:
            self.seen: list[int | None] = []

        async def complete(
            self,
            messages: list[dict[str, Any]],
            tools: Any = None,
            response_format: Any = None,
            max_tokens: int | None = None,
        ) -> LLMReply:
            self.seen.append(max_tokens)
            return LLMReply(text="ok")

    inner = _Attrless()
    settings = _chat_settings(
        **{
            "llm.default_model": "glm-5.3-flash",
            "agent.context.model_profiles": {
                "glm-5.3-flash": {"window_tokens": 1_000_000, "max_output_tokens": 128_000}
            },
        }
    )
    llm = output_capped_llm(inner, settings)  # type: ignore[arg-type]
    await llm.complete([{"role": "user", "content": "hi"}])
    assert inner.seen == [128_000]


@pytest.mark.asyncio
async def test_streaming_exposure_follows_inner() -> None:
    """complete_stream exists only when the inner client has it: the upstream
    streaming probe relies on absence, not on an error."""

    class _NoStream:
        async def complete(
            self,
            messages: list[dict[str, Any]],
            tools: Any = None,
            response_format: Any = None,
            max_tokens: int | None = None,
        ) -> LLMReply:
            return LLMReply(text="ok")

    wrapped = output_capped_llm(_NoStream(), _chat_settings())  # type: ignore[arg-type]
    assert callable(getattr(wrapped, "complete_stream", None)) is False

    inner = FakeLLM()
    wrapped_fake = output_capped_llm(inner, _chat_settings())
    assert callable(getattr(wrapped_fake, "complete_stream", None)) is False
