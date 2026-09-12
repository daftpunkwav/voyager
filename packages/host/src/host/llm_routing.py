"""Purpose-based model routing and fallback chains (phase 18).

Resolution order for one call: the routing table entry for the purpose
(agent.llm.routing: provider / model / fallbacks) wins; an explicitly
constructed provider_id/model next; the default provider/model resolution
(ServiceLLM) last. Every hop failure falls to the next hop in the chain and
raises an llm.fallback event on the bus so the degradation is visible
(diagnostics + activity feed); exhausting the chain degrades to a readable
reply — a running turn hangs on, it is not lost.

Transport stays in llm_adapter; this file only decides WHERE a call goes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agent.contracts import Purpose
from agent.llm import LLMReply, StreamReply, ToolSpec
from agent.settings import ROUTING_KEY
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event, ServiceError

from .llm_adapter import NO_PROVIDER_TEXT, LateBoundCall, ServiceLLM

SYSTEM_HOST = ActorRef(kind=ActorKind.SYSTEM, id="host.llm")


def resolve_chain(routing: Any, purpose: Purpose | str) -> list[dict[str, str]]:
    """Hops for one purpose: [{"provider": id, "model": name}, ...], primary
    first. Empty provider/model fields mean "use the default resolution".
    Malformed entries are skipped (a broken routing row must not disable the
    primary path)."""
    if not isinstance(routing, dict):
        return []
    entry = routing.get(purpose.value if isinstance(purpose, Purpose) else str(purpose))
    if not isinstance(entry, dict):
        return []
    hops: list[dict[str, str]] = []
    primary = {
        "provider": str(entry.get("provider") or ""),
        "model": str(entry.get("model") or ""),
    }
    if primary["provider"] or primary["model"]:
        hops.append(primary)
    fallbacks = entry.get("fallbacks")
    if isinstance(fallbacks, list):
        for fb in fallbacks:
            if not isinstance(fb, dict):
                continue
            hop = {"provider": str(fb.get("provider") or ""), "model": str(fb.get("model") or "")}
            if hop["provider"] or hop["model"]:
                hops.append(hop)
    return hops


class RoutingServiceLLM(ServiceLLM):
    """ServiceLLM that consults the routing table for its purpose and walks a
    fallback chain on failures (each fallthrough is announced on the bus)."""

    def __init__(
        self,
        call: LateBoundCall,
        *,
        purpose: Purpose,
        settings: Any = None,  # hot routing-table reader (SettingsStore); None = defaults only
        bus: Any = None,  # EventBus | None (duck-typed: tests pass a recorder)
        **kwargs: Any,
    ) -> None:
        super().__init__(call, **kwargs)
        self._purpose = purpose
        self._settings = settings
        self._bus = bus

    def _chain(self) -> list[dict[str, str]]:
        routing = None
        if self._settings is not None:
            try:
                routing = self._settings.get(ROUTING_KEY)
            except Exception:  # noqa: BLE001  # settings trouble must not block the default route
                routing = None
        return resolve_chain(routing, self._purpose)

    def _primary_overrides(self) -> dict[str, str]:
        chain = self._chain()
        if chain:
            return chain[0]
        return {"provider": "", "model": ""}

    async def _resolve_provider(self) -> dict[str, Any] | None:
        pinned = self._primary_overrides()["provider"]
        if pinned:
            return {"id": pinned, "default_model": self._model}
        return await super()._resolve_provider()

    def _model_for(self, provider: dict[str, Any], hop: dict[str, str]) -> str:
        return hop.get("model") or self._model or str(provider.get("default_model") or "")

    async def _announce(self, failed: dict[str, str], next_hop: dict[str, str], error: str) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            Event(
                type=DomainEvent.LLM_FALLBACK,
                actor=SYSTEM_HOST,
                payload={
                    "purpose": self._purpose.value,
                    "from": f"{failed.get('provider', '')}/{failed.get('model', '')}",
                    "to": f"{next_hop.get('provider', '')}/{next_hop.get('model', '')}",
                    "error": error[:300],
                },
            )
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> LLMReply:
        chain = self._chain()
        if not chain:
            return await super().complete(messages, tools)
        last_error = ""
        for index, hop in enumerate(chain):
            provider = (
                {"id": hop["provider"], "default_model": self._model}
                if hop["provider"]
                else await super()._resolve_provider()
            )
            if provider is None:
                return LLMReply(text=NO_PROVIDER_TEXT, degraded=True)
            try:
                return await self._complete_on(
                    provider, self._model_for(provider, hop), messages, tools
                )
            except ServiceError as exc:
                last_error = exc.body.message
                if index + 1 < len(chain):
                    await self._announce(
                        {
                            "provider": str(provider.get("id") or ""),
                            "model": self._model_for(provider, hop),
                        },
                        chain[index + 1],
                        last_error,
                    )
        return LLMReply(
            text=f"(LLM call failed after {len(chain)} attempt(s): {last_error})",
            degraded=True,
        )

    async def _complete_on(
        self,
        provider: dict[str, Any],
        model: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None,
    ) -> LLMReply:
        out = await self._call(
            self._llm_domain,
            "complete",
            {
                "provider_id": provider["id"],
                "model": model,
                "messages": messages,
                "tools": self._tool_payload(tools),
            },
        )
        return self._parse_complete(out)

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamReply]:
        """Streaming shares the chain for the INITIAL call; a mid-stream failure
        still propagates as ServiceError (the agent loop's recovery path owns it)."""
        chain = self._chain()
        if not chain:
            async for reply in super().complete_stream(messages, tools):
                yield reply
            return
        last_error = ""
        for index, hop in enumerate(chain):
            provider = (
                {"id": hop["provider"], "default_model": self._model}
                if hop["provider"]
                else await super()._resolve_provider()
            )
            if provider is None:
                yield StreamReply(final=LLMReply(text=NO_PROVIDER_TEXT, degraded=True))
                return
            try:
                gen = await self._call(
                    self._llm_domain,
                    "complete_stream",
                    {
                        "provider_id": provider["id"],
                        "model": self._model_for(provider, hop),
                        "messages": messages,
                        "tools": self._tool_payload(tools),
                    },
                )
            except ServiceError as exc:
                last_error = exc.body.message
                if index + 1 < len(chain):
                    await self._announce(
                        {
                            "provider": str(provider.get("id") or ""),
                            "model": self._model_for(provider, hop),
                        },
                        chain[index + 1],
                        last_error,
                    )
                continue
            async for chunk in gen:
                if isinstance(chunk, dict) and chunk.get("type") == "final":
                    yield StreamReply(final=self._parse_complete(chunk))
                elif isinstance(chunk, dict):
                    yield StreamReply(text_delta=str(chunk.get("text") or ""))
            return
        yield StreamReply(
            final=LLMReply(
                text=f"(LLM call failed after {len(chain)} attempt(s): {last_error})", degraded=True
            )
        )


__all__ = ["ROUTING_KEY", "RoutingServiceLLM", "resolve_chain"]
