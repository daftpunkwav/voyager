"""Embedding requests against chat-format providers (OpenAI-compatible
POST {base}/embeddings); the transport twin of client.complete.

Anthropic-format providers expose no embeddings endpoint and are refused up
front with a classified ProviderError, so the capability layer degrades with
an actionable message instead of a 404. Retry/backoff and error typing reuse
the client module's helpers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from llm.client import (
    HttpPolicy,
    ProviderError,
    _post,
    _send_with_retry,
    _stream_timeout,
    _wire_base,
)
from llm.net_pin import pinned_ip


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    model: str
    input_tokens: int


async def embed(
    provider: dict[str, Any],
    *,
    api_key: str,
    model: str,
    texts: Sequence[str],
    policy: HttpPolicy | None = None,
) -> EmbedResult:
    if provider.get("api_format") != "chat":
        raise ProviderError(
            f"provider format {provider.get('api_format')!r} has no embeddings endpoint",
            status=0,
        )
    base = _wire_base(provider)[1]  # classified lookup: a missing key is not a KeyError
    body = {"model": model, "input": list(texts)}
    chosen_ip = await pinned_ip(provider)  # resolve-and-pin before anything is sent
    async with httpx.AsyncClient(timeout=_stream_timeout(policy)) as client:
        resp = await _send_with_retry(
            lambda: _post(
                client,
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                body=body,
                chosen_ip=chosen_ip,
            ),
            policy,
        )
    data = resp.json()
    items = sorted(data.get("data") or [], key=lambda item: int(item.get("index") or 0))
    vectors = [[float(x) for x in (item.get("embedding") or [])] for item in items]
    if len(vectors) != len(texts):
        raise ProviderError(
            f"embeddings response carried {len(vectors)} vectors for {len(texts)} inputs",
            status=resp.status_code,
        )
    usage = data.get("usage") or {}
    return EmbedResult(
        vectors=vectors,
        model=str(data.get("model") or model),
        input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
    )


__all__ = ["EmbedResult", "embed"]
