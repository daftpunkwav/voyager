"""Output-cap wrapper: inject the configured per-model max-output budget
into every LLM call so the wire request honors user settings instead of the
transport's built-in default.

The cap comes from agent.context resolution (agent.context.max_output_tokens
with the agent.context.model_profiles per-model override), resolved against
the inner client's model on each call — hot-read, so settings changes apply
from the next call. A caller-passed max_tokens always wins; resolution
trouble degrades to no injection (the llm domain's setting-backed default
applies) rather than blocking the call.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from platform_contracts import ServiceError

from agent.context.usage import resolve_window
from agent.llm import LLMClient, LLMReply

log = logging.getLogger("agent.context")


def _settings_str(settings: Any, key: str) -> str:
    try:
        return str(settings.get(key) or "")
    except (KeyError, ServiceError):  # unregistered keys raise; degrade to empty
        return ""


def _resolve_cap(settings: Any, llm: Any) -> int:
    """Resolved max-output for the inner client's model; 0 = do not inject.

    ServiceLLM exposes no .model attribute (the effective chat model resolves
    per call from llm.default_model), so the same fallback chain as the
    budget resolver applies: client attr -> standalone-run setting ->
    composer chat model. Routed purposes whose chain picks a different model
    resolve to the chat default's cap — a documented approximation.
    """
    try:
        model_name = (
            str(getattr(llm, "model", "") or "")
            or _settings_str(settings, "agent.llm.model")
            or _settings_str(settings, "llm.default_model")
        )
        return resolve_window(settings, model_name).max_output_tokens
    except (KeyError, ServiceError):  # settings trouble must not block the call
        log.debug("output cap resolution failed; falling back to the llm default", exc_info=True)
        return 0


def output_capped_llm(llm: LLMClient, settings: Any) -> LLMClient:
    """Wrap an LLM client so each complete/complete_stream carries the
    configured wire max_tokens (agent.context resolution for the inner
    client's model). Callers passing max_tokens explicitly bypass the
    resolution. complete_stream is exposed only when the inner client has it,
    mirroring the quota wrapper — the streaming probe upstream relies on the
    attribute being absent, not erroring."""

    class _CappedBase:
        async def complete(
            self,
            messages: list[dict[str, Any]],
            tools: Any = None,
            response_format: Any = None,
            max_tokens: int | None = None,
        ) -> LLMReply:
            cap = max_tokens if max_tokens is not None else _resolve_cap(settings, llm) or None
            try:
                return await llm.complete(
                    messages, tools, response_format=response_format, max_tokens=cap
                )
            except TypeError:
                return await llm.complete(messages, tools)

    class _CappedStreaming(_CappedBase):
        def complete_stream(
            self,
            messages: list[dict[str, Any]],
            tools: Any = None,
            max_tokens: int | None = None,
        ) -> AsyncIterator[Any]:
            return self._stream(messages, tools, max_tokens=max_tokens)

        async def _stream(
            self,
            messages: list[dict[str, Any]],
            tools: Any = None,
            max_tokens: int | None = None,
        ) -> AsyncIterator[Any]:
            cap = max_tokens if max_tokens is not None else _resolve_cap(settings, llm) or None
            # Selected only when the inner client has complete_stream; the
            # ignore is load-bearing: LLMClient types it as optional.
            stream_call = llm.complete_stream  # type: ignore[attr-defined]
            try:
                stream = stream_call(messages, tools, max_tokens=cap)
            except TypeError:
                stream = stream_call(messages, tools)
            async for ev in stream:
                yield ev

    has_stream = callable(getattr(llm, "complete_stream", None))
    instance: LLMClient = _CappedStreaming() if has_stream else _CappedBase()
    return instance


__all__ = ["output_capped_llm"]
