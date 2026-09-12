"""Adapts the llm domain's complete / complete_stream capabilities to
the agent.llm.LLMClient protocol.

The agent never talks to an LLM provider directly: completions always go
through the late-bound call injected by the composition root, so they ride
the same guard chain as REST consumers. Domain names are constructor
defaults (llm / settings), not imports: the adapter never loads a domain
package.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from agent.llm import LLMReply, StreamReply, ToolCall, ToolSpec, Usage
from platform_contracts import CONTEXT_OVERFLOW_HINT, ServiceError

NO_PROVIDER_TEXT = (
    "(No usable LLM provider is configured yet: add a provider and "
    "fill in its api key, then I can continue.)"
)

LateBoundCall = Callable[[str, str, dict[str, Any]], Awaitable[Any]]


class ServiceLLM:
    """complete capability -> LLMReply.

    Provider resolution: an explicit provider_id wins; otherwise the
    llm.default_provider setting (chosen on the settings page) is used, but only
    when it is enabled and has_api_key; failing that, the first usable provider
    is chosen. Call failures (ServiceError, e.g. network/quota) degrade to a
    readable text reply instead of breaking the agent loop.
    """

    def __init__(
        self,
        call: LateBoundCall,
        *,
        provider_id: str = "",
        model: str = "",
        llm_domain: str = "llm",
        settings_domain: str = "settings",
    ) -> None:
        self._call = call
        self._provider_id = provider_id
        self._model = model
        self._llm_domain = llm_domain
        self._settings_domain = settings_domain

    async def _resolve_provider(self) -> dict[str, Any] | None:
        if self._provider_id:
            return {"id": self._provider_id, "default_model": self._model}
        raw = await self._call(self._llm_domain, "list_providers", {})
        if not isinstance(raw, list):
            return None
        usable = [
            p
            for p in raw
            if isinstance(p, dict) and p.get("enabled", True) and p.get("has_api_key")
        ]
        if not usable:
            return None
        default_id = ""
        try:
            item = await self._call(
                self._settings_domain,
                "get_setting",
                {"key": "llm.default_provider"},
            )
            if isinstance(item, dict):
                default_id = str(item.get("value") or "")
        except ServiceError:
            pass  # settings unavailable must not block chat; treat as unset
        if default_id:
            for p in usable:
                if p.get("id") == default_id:
                    return p
        return usable[0]

    def _tool_payload(self, tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [{"name": t.name, "description": t.description, "schema": t.schema} for t in tools]

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> LLMReply:
        provider = await self._resolve_provider()
        if provider is None:
            return LLMReply(text=NO_PROVIDER_TEXT, degraded=True)
        try:
            out = await self._call(
                self._llm_domain,
                "complete",
                {
                    "provider_id": provider["id"],
                    "model": self._model or provider.get("default_model", ""),
                    "messages": messages,
                    "tools": self._tool_payload(tools),
                },
            )
        except ServiceError as exc:
            return LLMReply(
                text=f"(LLM call failed: {exc.body.message})",
                degraded=True,
                overflow=exc.body.hint == CONTEXT_OVERFLOW_HINT,
            )
        if not isinstance(out, dict):
            return LLMReply(text=NO_PROVIDER_TEXT, degraded=True)
        return self._parse_complete(out)

    def _parse_complete(self, out: dict[str, Any]) -> LLMReply:
        """One complete-capability result dict -> LLMReply (shared by complete
        and the routing fallback path)."""
        usage = out.get("usage") or {}
        return LLMReply(
            text=out.get("text") or None,
            tool_calls=tuple(
                ToolCall(id=tc.get("id", ""), name=tc["name"], arguments=tc.get("arguments") or {})
                for tc in out.get("tool_calls") or ()
                if isinstance(tc, dict) and "name" in tc
            ),
            usage=Usage(
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
            ),
        )

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamReply]:
        """Streaming completion: provider resolution and initial-call degradation
        match complete.

        The service emits {"type": "text"|"final", ...} chunks; this method maps
        them onto the agent's StreamReply. With no usable provider it yields a
        single final degraded reply (no call is made); service errors raised
        during iteration propagate as ServiceError and are handled by the
        caller (the agent loop) along its existing failure path.
        """
        provider = await self._resolve_provider()
        if provider is None:
            yield StreamReply(final=LLMReply(text=NO_PROVIDER_TEXT, degraded=True))
            return
        try:
            gen = await self._call(
                self._llm_domain,
                "complete_stream",
                {
                    "provider_id": provider["id"],
                    "model": self._model or provider.get("default_model", ""),
                    "messages": messages,
                    "tools": self._tool_payload(tools),
                },
            )
        except ServiceError as exc:
            yield StreamReply(
                final=LLMReply(
                    text=f"(LLM call failed: {exc.body.message})",
                    degraded=True,
                    overflow=exc.body.hint == CONTEXT_OVERFLOW_HINT,
                )
            )
            return
        async for chunk in gen:
            if not isinstance(chunk, dict):
                continue
            if chunk.get("type") == "final":
                usage = chunk.get("usage") or {}
                yield StreamReply(
                    final=LLMReply(
                        text=chunk.get("text") or None,
                        tool_calls=tuple(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=tc["name"],
                                arguments=tc.get("arguments") or {},
                            )
                            for tc in chunk.get("tool_calls") or ()
                            if isinstance(tc, dict) and "name" in tc
                        ),
                        usage=Usage(
                            input_tokens=int(usage.get("input_tokens") or 0),
                            output_tokens=int(usage.get("output_tokens") or 0),
                        ),
                    )
                )
            else:
                yield StreamReply(text_delta=str(chunk.get("text") or ""))
