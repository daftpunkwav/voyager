"""list_builtin_providers capability: the built-in provider catalog."""

from __future__ import annotations

from platform_capability import capability

from llm.capabilities.common import (
    registry,
)
from llm.catalog import BUILTIN_PROVIDERS


@capability(
    registry,
    name="list_builtin_providers",
    description="Built-in provider catalog (name/base_url/format/models)",
)
def list_builtin_providers() -> list[dict]:
    return [dict(p) for p in BUILTIN_PROVIDERS]
