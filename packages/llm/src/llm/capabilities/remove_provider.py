"""remove_provider capability: delete a provider and clear its key."""

from __future__ import annotations

from platform_capability import capability

from llm.capabilities.common import (
    key_name,
    registry,
    require_deps,
    require_provider,
)


@capability(registry, name="remove_provider", description="Delete a provider and clear its key")
def remove_provider(provider_id: str) -> dict:
    deps = require_deps()
    require_provider(provider_id)
    deps.store.delete(provider_id)
    deps.secrets.delete(key_name(provider_id))
    return {"removed": provider_id}
