"""complete_stream capability: streaming completion (in-process only; REST rejects it)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from platform_capability import capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    read_api_key,
    registry,
    require_deps,
    require_provider,
    service_error_for,
)
from llm.client import ProviderError
from llm.stream import complete_stream as llm_stream


@capability(
    registry,
    name="complete_stream",
    cost=10,
    streaming=True,
    description=(
        "LLM streaming completion (AsyncIterator: several text delta chunks + "
        "a final aggregate chunk; in-process consumption only, rejected over "
        "REST). Guard chain and usage recording match complete — usage is "
        "recorded when the stream ends (including failures)"
    ),
)
async def complete_stream(
    provider_id: str,
    messages: list[dict],
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    _actor: ActorRef | None = None,
):
    """Streaming completion: same validation and key lookup as complete;
    returns an async generator.

    Usage is recorded in the generator's finally block (runs on both normal
    exhaustion and mid-stream errors, distinguished by ok). If a consumer
    abandons the generator before exhausting it, GC triggers aclose and the
    finally block still executes.
    """
    deps = require_deps()
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "api key not configured")
    use_model = model or p["default_model"]

    async def _gen() -> AsyncIterator[dict]:
        ok = False
        usage: dict = {}
        used_model = use_model
        try:
            async for chunk in llm_stream(
                p,
                api_key=key,
                model=use_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            ):
                if chunk.get("type") == "final":
                    usage = chunk.get("usage") or {}
                    used_model = str(chunk.get("model") or use_model)
                yield chunk
            ok = True
        except ProviderError as exc:
            raise service_error_for(exc) from exc
        except Exception as exc:
            raise ServiceError(
                DOMAIN, ErrorSuffix.UNAVAILABLE, f"LLM streaming call failed: {exc}"
            ) from exc
        finally:
            deps.store.record_usage(
                provider_id,
                used_model,
                int(usage.get("input_tokens") or 0),
                int(usage.get("output_tokens") or 0),
                cached_tokens=int(usage.get("cached_tokens") or 0),
                caller=_actor.id if _actor else "",
                ok=ok,
            )

    return _gen()
