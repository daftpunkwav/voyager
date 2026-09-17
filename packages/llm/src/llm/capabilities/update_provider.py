"""update_provider capability: metadata update; base_url changes are user-only."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

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
    registry, name="update_provider", description="Update provider metadata (excluding the key)"
)
def update_provider(
    provider_id: str,
    display_name: str | None = None,
    base_url: str | None = None,
    api_format: str | None = None,
    models: list[str] | None = None,
    models_meta: dict | None = None,
    enabled: bool | None = None,
    _actor: ActorRef | None = None,
) -> dict:
    deps = require_deps()
    current = require_provider(provider_id)
    if base_url is not None:
        # Pointing base_url at a new host would send the stored key there on
        # the next call, so only the user may change it.
        if _actor is None or _actor.kind is not ActorKind.USER:
            raise ServiceError(
                DOMAIN,
                ErrorSuffix.FORBIDDEN,
                "base_url can only be changed by the user",
                hint="Agents may update metadata such as name/model list; change "
                "the endpoint URL in the settings page",
            )
        base_url = validate_base_url(base_url, _actor)
    if api_format is not None and not valid_format(api_format):
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
    merged = {
        **current,
        **{
            k: v
            for k, v in {
                "display_name": display_name,
                "base_url": base_url,
                "api_format": api_format,
                "models": models,
                "models_meta": models_meta,
                "enabled": enabled,
            }.items()
            if v is not None
        },
    }
    deps.store.upsert(merged)
    return with_key_flag(require_provider(provider_id), deps.secrets)
