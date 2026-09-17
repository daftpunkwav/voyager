"""add_provider capability: provider metadata only; base_url validated, no api_key accepted."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorRef, ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    MODELS_META_ALLOWED,
    find_bad_models_meta_field,
    registry,
    require_deps,
    require_provider,
    valid_models_meta,
    validate_base_url,
    with_key_flag,
)
from llm.catalog import valid_format


@capability(
    registry, name="add_provider", description="Add a provider (metadata; no api_key accepted)"
)
def add_provider(
    display_name: str,
    base_url: str,
    api_format: str,
    models: list[str] | None = None,
    models_meta: dict | None = None,
    preset_id: str = "",
    _actor: ActorRef | None = None,
) -> dict:
    if not valid_format(api_format):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"api_format only supports chat / anthropic / responses: {api_format}",
        )
    if models_meta is not None and not valid_models_meta(models_meta):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"invalid models_meta: {find_bad_models_meta_field(models_meta)}",
            hint=f"allowed fields: {MODELS_META_ALLOWED}",
        )
    base_url = validate_base_url(base_url, _actor)
    deps = require_deps()
    pid = deps.store.upsert(
        {
            "display_name": display_name,
            "preset_id": preset_id,
            "base_url": base_url,
            "api_format": api_format,
            "models": models or [],
            "models_meta": models_meta or {},
            "custom": True,
        }
    )
    return with_key_flag(require_provider(pid), deps.secrets)
