"""Embedding adapter: memory.vector.EmbeddingFn backed by the llm domain's
embed capability through the late-bound call_sync (the agent never imports
the llm domain).

Provider resolution mirrors ServiceLLM: llm.default_provider when usable,
else the first enabled provider with a key. Every failure — no embedding
model configured, no usable provider, upstream errors — surfaces as
EmbeddingUnavailable so memory recall degrades to the lexical channel and
reports why, instead of breaking the query.

call_sync must run off the event-loop thread; recall is a sync handler that
the tool/capability pipelines already execute in a worker thread.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent.memory.vector import EmbeddingUnavailable
from platform_contracts import ServiceError

_EMBEDDING_MODEL_KEY = "llm.embedding_model"
_DEFAULT_PROVIDER_KEY = "llm.default_provider"


class ServiceEmbedder:
    def __init__(self, call_sync: Any, settings: Any, *, llm_domain: str = "llm") -> None:
        self._call_sync = call_sync
        self._settings = settings
        self._llm_domain = llm_domain

    def _model(self) -> str:
        model = str(self._settings.get(_EMBEDDING_MODEL_KEY) or "")
        if not model:
            raise EmbeddingUnavailable(
                f"no embedding model configured ({_EMBEDDING_MODEL_KEY} is empty)"
            )
        return model

    def _provider_id(self) -> str:
        raw = self._call_sync(self._llm_domain, "list_providers", {})
        usable = [
            p
            for p in (raw if isinstance(raw, list) else [])
            if isinstance(p, dict) and p.get("enabled", True) and p.get("has_api_key")
        ]
        if not usable:
            raise EmbeddingUnavailable("no enabled provider with an api key")
        default_id = str(self._settings.get(_DEFAULT_PROVIDER_KEY) or "")
        for p in usable:
            if p.get("id") == default_id:
                return str(p["id"])
        return str(usable[0]["id"])

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._model()
        try:
            provider_id = self._provider_id()
            out = self._call_sync(
                self._llm_domain,
                "embed",
                {"provider_id": provider_id, "texts": list(texts), "model": model},
            )
        except EmbeddingUnavailable:
            raise
        except ServiceError as exc:
            raise EmbeddingUnavailable(f"embed capability failed: {exc.body.message}") from exc
        except Exception as exc:  # any transport failure degrades to lexical recall
            raise EmbeddingUnavailable(f"embedding call failed: {exc}") from exc
        vectors = out.get("vectors") if isinstance(out, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingUnavailable("embed capability returned a malformed vector list")
        return vectors


__all__ = ["ServiceEmbedder"]
