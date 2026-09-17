"""list_remote_models capability: fetch a provider's model catalog live.

One GET request against the configured base_url (OpenAI-compatible endpoints
and Anthropic share the response shape: {"data": [{"id": ...}]}); returns the
model id list so the settings page can offer a picker instead of free-typing
ids. The path mirrors client.complete's URL building: the anthropic format
expects a bare host (its chat URL is {base}/v1/messages), the others expect
the API root to already include the version segment. Read-only, no retries,
and the api key never appears in the result.
"""

from __future__ import annotations

import httpx
from platform_capability import capability
from platform_contracts import ErrorSuffix, ServiceError

from llm.capabilities.common import (
    DOMAIN,
    read_api_key,
    registry,
    require_provider,
)
from llm.client import _TIMEOUT


def _models_headers(api_format: str, api_key: str) -> dict[str, str]:
    if api_format == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    return {"Authorization": f"Bearer {api_key}"}


@capability(
    registry,
    name="list_remote_models",
    description="Fetch a provider's live model catalog from GET /models",
    cost=2,
)
async def list_remote_models(provider_id: str) -> dict:
    p = require_provider(provider_id)
    key = read_api_key(provider_id)
    if not key:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "This provider has no api key configured",
            hint="Fill in the api key in the settings page before listing models",
        )
    base = p["base_url"].rstrip("/")
    # anthropic base_url carries no version segment (client posts {base}/v1/messages)
    url = f"{base}/v1/models" if p["api_format"] == "anthropic" else f"{base}/models"
    headers = _models_headers(p["api_format"], key)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TransportError as exc:
        raise ServiceError(
            DOMAIN, ErrorSuffix.UNAVAILABLE, f"Model catalog request failed: {exc}"
        ) from exc
    if resp.status_code != 200:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.UNAVAILABLE,
            f"Model catalog request failed with HTTP {resp.status_code}",
            hint=resp.text[:200],
        )
    try:
        payload = resp.json()
        ids = [
            str(item["id"])
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
    except Exception as exc:  # malformed catalog body
        raise ServiceError(
            DOMAIN, ErrorSuffix.UNAVAILABLE, f"Model catalog response was malformed: {exc}"
        ) from exc
    return {"provider_id": provider_id, "models": sorted(set(ids))}
