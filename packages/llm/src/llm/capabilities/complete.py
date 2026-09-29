"""complete capability: chat completion with direct usage metering (also on failure)."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    configured_max_output_tokens,
    effective_model,
    http_policy,
    read_api_key,
    registry,
    require_deps,
    require_provider,
    service_error_for,
)
from llm.client import ProviderError
from llm.client import complete as llm_complete

#: Canonical reasoning-effort names with an Anthropic budget mapping; other
#: names a model declares in thinking_variants pass through verbatim on
#: chat/responses formats and stay unset on anthropic (no expressible budget).
_CANONICAL_EFFORTS = ("low", "medium", "high")

#: Sentinel stored in llm.reasoning_effort meaning "explicitly off" — the
#: empty string means the opposite ("follow the model's configured default").
OFF_SENTINEL = "off"


def resolve_reasoning_effort(setting: str, model_meta: dict) -> str:
    """One llm.reasoning_effort value -> the effort actually put on the wire
    for a model with this models_meta entry. The model configuration (the
    settings page's thinking variants/default) is the single source of truth;
    the setting is only a per-session override on top of it:

    - "off" -> "" (explicitly disabled)
    - a configured thinking model: a value inside thinking_variants passes
      through, anything else (unset, stale from a previous model, typo)
      follows thinking_default
    - a model without a variants list (legacy config): canonical names pass
      through unchanged, anything else stays unset — the pre-variants
      typo-safety, kept for backward compatibility
    """
    if setting == OFF_SENTINEL:
        return ""
    variants = model_meta.get("thinking_variants")
    variant_list = [str(v) for v in variants] if isinstance(variants, list) else []
    default = str(model_meta.get("thinking_default") or "")
    if setting:
        if variant_list:
            return setting if setting in variant_list else default
        return setting if setting in _CANONICAL_EFFORTS else ""
    if variant_list or model_meta.get("thinking") is True:
        return default
    return ""


def configured_reasoning_effort(provider: dict, model: str) -> str:
    """Hot-read llm.reasoning_effort and resolve it against the serving
    provider/model's models_meta (see resolve_reasoning_effort); unknown
    shapes degrade to unset, never raise."""
    deps = require_deps()
    if deps.settings is None:
        return ""
    setting = str(deps.settings.get("llm.reasoning_effort") or "")
    meta_raw = provider.get("models_meta")
    meta = meta_raw.get(model) if isinstance(meta_raw, dict) else None
    return resolve_reasoning_effort(setting, meta if isinstance(meta, dict) else {})


def configured_reasoning_variants(provider: dict, model: str) -> tuple[str, ...]:
    """The serving model's declared thinking variants, for the anthropic
    format's budget interpolation of non-canonical effort names."""
    meta_raw = provider.get("models_meta")
    meta = meta_raw.get(model) if isinstance(meta_raw, dict) else None
    if not isinstance(meta, dict):
        return ()
    variants = meta.get("thinking_variants")
    if not isinstance(variants, list):
        return ()
    return tuple(str(v) for v in variants)


@capability(
    registry,
    name="complete",
    description=(
        "LLM chat completion (usage metered directly; agents consume via this). "
        "max_tokens 0 = auto: the llm.max_output_tokens setting supplies the cap"
    ),
    cost=10,
)
async def complete(
    provider_id: str,
    messages: list[dict],
    model: str = "",
    # 0 = caller omitted the cap: fall back to the llm.max_output_tokens
    # setting (users configure it per deployment); a positive value wins.
    max_tokens: int = 0,
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    deps = require_deps()
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "api key not configured")
    use_model = effective_model(p, model)
    wire_max_tokens = max_tokens if max_tokens > 0 else configured_max_output_tokens()
    try:
        result = await llm_complete(
            p,
            api_key=key,
            model=use_model,
            messages=messages,
            max_tokens=wire_max_tokens,
            temperature=temperature,
            tools=tools,
            reasoning_effort=configured_reasoning_effort(p, use_model),
            policy=http_policy(),
            reasoning_variants=configured_reasoning_variants(p, use_model),
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
        reasoning_tokens=result.reasoning_tokens,
        cache_write_tokens=result.cache_write_tokens,
        caller=_actor.id if _actor else "",
    )
    return {
        "text": result.text,
        "model": result.model,
        "tool_calls": [dict(tc) for tc in result.tool_calls],
        "usage": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            # Prompt tokens served from the provider's prefix cache: the agent
            # side's prefix-cache health watch reads this field off the Usage
            # it parses here — omitting it pins cached_tokens at 0 and every
            # round looks permanently cold.
            "cached_tokens": result.cached_tokens,
            "reasoning_tokens": result.reasoning_tokens,
            "cache_write_tokens": result.cache_write_tokens,
        },
        "reasoning": result.reasoning,
        "thinking_blocks": [dict(b) for b in result.thinking_blocks],
        # Provider response metadata (finish_reason / request id / service
        # tier / stop sequence / created); omitted keys were not reported.
        "meta": result.meta.to_dict(),
    }
