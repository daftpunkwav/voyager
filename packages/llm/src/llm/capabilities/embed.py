"""embed capability: batch text embeddings with direct usage metering.

The model defaults to the llm.embedding_model setting; an empty setting and
no explicit model is an actionable INVALID_INPUT (the caller — memory recall
— stays lexical and says so). Input tokens are metered like completions,
output tokens are always 0.
"""

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
from llm.embeddings import embed as llm_embed

_MAX_TEXTS = 256
_MAX_CHARS = 8000


@capability(
    registry,
    name="embed",
    description="Batch text embeddings (vectors in input order; model defaults to llm.embedding_model)",
    cost=3,
    write=False,
)
async def embed(
    provider_id: str,
    texts: list[str],
    model: str = "",
    _actor: ActorRef | None = None,
) -> dict:
    deps = require_deps()
    if not isinstance(texts, list) or not texts:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "texts must be a non-empty list")
    if len(texts) > _MAX_TEXTS:
        raise ServiceError(
            DOMAIN, ErrorSuffix.INVALID_INPUT, f"too many texts: {len(texts)} > {_MAX_TEXTS}"
        )
    clean = [str(t)[:_MAX_CHARS] for t in texts]
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(DOMAIN, ErrorSuffix.INVALID_INPUT, "api key not configured")
    configured = deps.settings.get("llm.embedding_model") if deps.settings is not None else ""
    use_model = model or str(configured or "")
    if not use_model:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "no embedding model configured",
            hint="Set llm.embedding_model in the settings page (e.g. text-embedding-3-small)",
        )
    try:
        result = await llm_embed(p, api_key=key, model=use_model, texts=clean)
    except ProviderError as exc:
        deps.store.record_usage(
            provider_id, use_model, 0, 0, caller=_actor.id if _actor else "", ok=False
        )
        raise service_error_for(exc) from exc
    except Exception as exc:
        deps.store.record_usage(
            provider_id, use_model, 0, 0, caller=_actor.id if _actor else "", ok=False
        )
        raise ServiceError(
            DOMAIN, ErrorSuffix.UNAVAILABLE, f"embedding call failed: {exc}"
        ) from exc
    deps.store.record_usage(
        provider_id, result.model, result.input_tokens, 0, caller=_actor.id if _actor else ""
    )
    return {
        "vectors": result.vectors,
        "model": result.model,
        "usage": {"input_tokens": result.input_tokens, "output_tokens": 0},
    }
