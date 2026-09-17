"""test_connection capability: one minimal real request, returns latency/error."""

from __future__ import annotations

from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    effective_model,
    read_api_key,
    registry,
    require_provider,
)
from llm.client import test_connection as llm_test


@capability(
    registry,
    name="test_connection",
    description="Send one minimal real request to test connectivity; returns latency/error",
    cost=5,
)
async def test_connection(provider_id: str, model: str = "") -> dict:
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "This provider has no api key configured",
            hint="Fill in the api key in the settings page before testing",
        )
    result = await llm_test(p, api_key=key, model=effective_model(p, model))
    return {
        "ok": result.ok,
        "latency_ms": round(result.latency_ms, 1),
        "model": result.model,
        "error": result.error,
    }
