"""set_api_key capability: user-only secret write into platform/secrets."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError
from platform_secrets import SecretUnavailableError

from llm.capabilities.common import (
    DOMAIN,
    key_name,
    registry,
    require_deps,
    require_provider,
)


@capability(
    registry, name="set_api_key", description="Set a provider's api key (secret: user only)"
)
def set_api_key(provider_id: str, api_key: str, _actor: ActorRef | None = None) -> dict:
    """Privacy rule: beyond the framework layer, the service enforces
    "user-only writes" a second time on its own."""
    if _actor is None or _actor.kind is not ActorKind.USER:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "The api key is private data; only the user may fill it in via the settings page",
            hint="Agents may fill in the other fields; the key is left to the user",
        )
    require_provider(provider_id)
    deps = require_deps()
    try:
        deps.secrets.set(key_name(provider_id), api_key)
    except SecretUnavailableError:
        # BYOK: actionable guidance instead of a 500 when key material is missing
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.UNAVAILABLE,
            "Secret store unavailable: no key material configured on this machine",
            hint="Set SECRETS_ENCRYPTION_KEY in the repo-root .env and restart",
        ) from None
    return {"provider_id": provider_id, "has_api_key": True}
