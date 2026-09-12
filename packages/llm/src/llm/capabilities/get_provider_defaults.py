"""get_provider_defaults capability: base_url/format/models of a built-in preset."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    registry,
)
from llm.catalog import get_preset


@capability(
    registry,
    name="get_provider_defaults",
    description="Default base_url/format/model list for a built-in preset",
)
def get_provider_defaults(preset_id: str) -> dict:
    preset = get_preset(preset_id)
    if preset is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"Unknown built-in provider: {preset_id}")
    return preset
