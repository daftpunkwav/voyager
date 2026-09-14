"""complete capability: chat completion with direct usage metering (also on failure)."""

from __future__ import annotations

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
from llm.client import complete as llm_complete

#: Values accepted for llm.reasoning_effort; anything else degrades to unset
#: so a typo never silently rewrites every request.
_REASONING_EFFORTS = ("", "low", "medium", "high")


def configured_reasoning_effort() -> str:
    """Hot-read llm.reasoning_effort; unknown/missing values mean unset."""
    deps = require_deps()
    if deps.settings is None:
        return ""
    value = str(deps.settings.get("llm.reasoning_effort") or "")
    return value if value in _REASONING_EFFORTS else ""


@capability(
    registry,
    name="complete",
    description="LLM chat completion (usage metered directly; agents consume via this)",
    cost=10,
)
async def complete(
    provider_id: str,
    messages: list[dict],
    model: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    deps = require_deps()
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "api key not configured")
    use_model = model or p["default_model"]
    try:
        result = await llm_complete(
            p,
            api_key=key,
            model=use_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            reasoning_effort=configured_reasoning_effort(),
        )
    except ProviderError as exc:  # classified mapping; still metered on failure (ok=0)
        deps.store.record_usage(
            provider_id, use_model, 0, 0, caller=_actor.id if _actor else "", ok=False
        )
        raise service_error_for(exc) from exc
    except Exception as exc:  # meter unexpected errors too (ok=0)
        deps.store.record_usage(
            provider_id, use_model, 0, 0, caller=_actor.id if _actor else "", ok=False
        )
        raise ServiceError(DOMAIN, ErrorSuffix.UNAVAILABLE, f"LLM call failed: {exc}") from exc
    deps.store.record_usage(
        provider_id,
        result.model or use_model,
        result.input_tokens,
        result.output_tokens,
        cached_tokens=result.cached_tokens,
        caller=_actor.id if _actor else "",
    )
    return {
        "text": result.text,
        "model": result.model,
        "tool_calls": [dict(tc) for tc in result.tool_calls],
        "usage": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
    }
