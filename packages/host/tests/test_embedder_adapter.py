"""ServiceEmbedder: the memory vector channel over llm.embed via call_sync;
every failure mode becomes EmbeddingUnavailable (lexical degradation)."""

from __future__ import annotations

import pytest
from agent.memory.vector import EmbeddingUnavailable
from host.embedder_adapter import ServiceEmbedder
from platform_contracts import ErrorSuffix, ServiceError


class _Settings:
    def __init__(self, **values) -> None:
        self.values = values

    def get(self, key: str):
        return self.values.get(key)


def _call_sync_factory(providers, vectors=None, fail: Exception | None = None):
    calls: list[tuple[str, str, dict]] = []

    def call_sync(domain: str, name: str, args: dict):
        calls.append((domain, name, args))
        if name == "list_providers":
            return providers
        if fail is not None:
            raise fail
        return {"vectors": vectors if vectors is not None else [[1.0]] * len(args["texts"])}

    return call_sync, calls


class TestServiceEmbedder:
    def test_unconfigured_model(self) -> None:
        call_sync, _ = _call_sync_factory([])
        with pytest.raises(EmbeddingUnavailable, match="llm.embedding_model"):
            ServiceEmbedder(call_sync, _Settings()).embed(["a"])

    def test_no_usable_provider(self) -> None:
        call_sync, _ = _call_sync_factory([{"id": "p", "enabled": True, "has_api_key": False}])
        with pytest.raises(EmbeddingUnavailable, match="api key"):
            ServiceEmbedder(call_sync, _Settings(**{"llm.embedding_model": "m"})).embed(["a"])

    def test_default_provider_preferred_and_vectors_returned(self) -> None:
        providers = [
            {"id": "a", "enabled": True, "has_api_key": True},
            {"id": "b", "enabled": True, "has_api_key": True},
        ]
        call_sync, calls = _call_sync_factory(providers, vectors=[[0.5, 0.5], [0.1, 0.9]])
        settings = _Settings(**{"llm.embedding_model": "m", "llm.default_provider": "b"})
        out = ServiceEmbedder(call_sync, settings).embed(["x", "y"])
        assert out == [[0.5, 0.5], [0.1, 0.9]]
        _domain, name, args = calls[-1]
        assert name == "embed" and args["provider_id"] == "b" and args["model"] == "m"

    def test_service_error_degrades(self) -> None:
        providers = [{"id": "a", "enabled": True, "has_api_key": True}]
        call_sync, _ = _call_sync_factory(
            providers, fail=ServiceError("llm", ErrorSuffix.UNAVAILABLE, "upstream down")
        )
        with pytest.raises(EmbeddingUnavailable, match="upstream down"):
            ServiceEmbedder(call_sync, _Settings(**{"llm.embedding_model": "m"})).embed(["a"])

    def test_malformed_response_degrades(self) -> None:
        providers = [{"id": "a", "enabled": True, "has_api_key": True}]
        call_sync, _ = _call_sync_factory(providers, vectors=[[1.0]])  # one vector for two texts
        with pytest.raises(EmbeddingUnavailable, match="malformed"):
            ServiceEmbedder(call_sync, _Settings(**{"llm.embedding_model": "m"})).embed(["a", "b"])
