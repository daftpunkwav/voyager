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


def _fallback_model(provider: dict[str, Any]) -> str:
    """First enabled model of the provider's list (models_meta enabled=False
    entries are skipped; absent metadata means enabled)."""
    models = provider.get("models") or []
    meta = provider.get("models_meta") or {}
    for m in models:
        fields = meta.get(m)
        if not isinstance(fields, dict) or fields.get("enabled", True) is not False:
            return str(m)
    return str(models[0]) if models else ""


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
            return {"id": self._provider_id, "model": self._model}
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
        default_model = ""
        try:
            item = await self._call(
                self._settings_domain,
                "get_setting",
                {"key": "llm.default_provider"},
            )
            if isinstance(item, dict):
                default_id = str(item.get("value") or "")
            item = await self._call(
                self._settings_domain,
                "get_setting",
                {"key": "llm.default_model"},
            )
            if isinstance(item, dict):
                default_model = str(item.get("value") or "")
        except ServiceError:
            pass  # settings unavailable must not block chat; treat as unset
        provider = None
        if default_id:
            for p in usable:
                if p.get("id") == default_id:
                    provider = p
                    break
        provider = provider or usable[0]
        # llm.default_model (composer model picker) wins over the provider's
        # first enabled model — but only when the provider actually serves it:
        # a stale or renamed id would 400 on the wire for every call that has
        # no per-conversation override (task subagents).
        models = provider.get("models") or []
        picked = self._model or (default_model if default_model in models else "")
        if not picked:
            picked = _fallback_model(provider)
        return {**provider, "model": picked}

    def _tool_payload(self, tools: list[ToolSpec] | None) -> list[dict] | None:
        if not tools:
            return None
        return [{"name": t.name, "description": t.description, "schema": t.schema} for t in tools]

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> LLMReply:
        """max_tokens: caller-resolved wire cap (the agent passes its
        per-model budget); None = the capability's setting-backed default."""
        if response_format is not None:
            # The service transport cannot enforce a schema on the wire, so it
            # rejects the kwarg with TypeError — the signal complete_structured
            # uses to fall back to prompt-injected structured output.
            raise TypeError("ServiceLLM does not support response_format")
        provider = await self._resolve_provider()
        if provider is None:
            return LLMReply(text=NO_PROVIDER_TEXT, degraded=True)
        try:
            args: dict[str, Any] = {
                "provider_id": provider["id"],
                "model": self._model or provider.get("model", ""),
                "messages": messages,
                "tools": self._tool_payload(tools),
            }
            if max_tokens is not None:
                args["max_tokens"] = max_tokens
            out = await self._call(self._llm_domain, "complete", args)
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
        """One result dict -> LLMReply (shared by complete, the routing
        fallback path, and complete_stream's final chunk: the capability
        returns the same aggregate shape on both paths)."""
        usage = out.get("usage") or {}
        thinking_blocks = out.get("thinking_blocks") or ()
        request_body = out.get("request_body")
        meta_raw = out.get("meta")
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
            model=str(out.get("model") or ""),
            reasoning=str(out.get("reasoning") or ""),
            thinking_blocks=tuple(dict(b) for b in thinking_blocks if isinstance(b, dict)),
            # The exact wire body as built by the llm domain (stream flags and
            # reasoning fields included); None from paths that do not report it.
            request_body=request_body if isinstance(request_body, dict) else None,
            # Provider response metadata (finish_reason / request id / ...);
            # empty dict from paths that do not report it.
            meta=dict(meta_raw) if isinstance(meta_raw, dict) else {},
        )

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int | None = None,
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
            args: dict[str, Any] = {
                "provider_id": provider["id"],
                "model": self._model or provider.get("model", ""),
                "messages": messages,
                "tools": self._tool_payload(tools),
            }
            if max_tokens is not None:
                args["max_tokens"] = max_tokens
            gen = await self._call(self._llm_domain, "complete_stream", args)
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
                # Same dict shape as the complete capability's return: one
                # mapping for both paths so the field parsing cannot drift.
                yield StreamReply(final=self._parse_complete(chunk))
            elif chunk.get("type") == "reasoning":
                # Live thinking stays on its own channel: mapping it to
                # text_delta would spray reasoning into the answer stream.
                yield StreamReply(reasoning_delta=str(chunk.get("text") or ""))
            else:
                yield StreamReply(text_delta=str(chunk.get("text") or ""))
