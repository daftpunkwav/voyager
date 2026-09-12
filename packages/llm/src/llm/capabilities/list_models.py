"""list_models capability: a provider's model list and default model."""

from __future__ import annotations

from platform_capability import capability

from llm.capabilities.common import (
    registry,
    require_provider,
)


@capability(registry, name="list_models", description="A provider's model list")
def list_models(provider_id: str) -> dict:
    p = require_provider(provider_id)
    return {"provider_id": provider_id, "models": p["models"], "default_model": p["default_model"]}
