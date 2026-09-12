"""list_providers capability: configured providers with a has_api_key flag (never the key)."""

from __future__ import annotations

from platform_capability import capability

from llm.capabilities.common import (
    registry,
    require_deps,
    with_key_flag,
)


@capability(
    registry,
    name="list_providers",
    description="Configured providers (has_api_key flag; never returns the key)",
)
def list_providers() -> list[dict]:
    deps = require_deps()
    return [with_key_flag(p, deps.secrets) for p in deps.store.list(include_disabled=True)]
