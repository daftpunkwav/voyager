"""embed capability: vectors in input order with usage metering; unconfigured
model and non-chat providers degrade with actionable errors."""

from __future__ import annotations

import pytest
from llm.capabilities import Deps, init_deps, registry
from llm.capabilities import embed as embed_mod
from llm.client import ProviderError
from llm.embeddings import EmbedResult
from llm.store import ProviderStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError
from platform_secrets import SecretStore

USER = ActorContext(actor=LOCAL_USER)


class _Settings:
    def __init__(self, model: str = "") -> None:
        self.model = model

    def get(self, key: str):
        return self.model if key == "llm.embedding_model" else None


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "0" * 64)
    store = ProviderStore(tmp_path / "llm.db")
    secrets = SecretStore(tmp_path / "secrets.db")
    settings = _Settings()
    init_deps(Deps(store=store, secrets=secrets, settings=settings))
    pid = store.upsert(
        {
            "display_name": "p",
            "preset_id": "",
            "base_url": "https://api.example.com/v1",
            "api_format": "chat",
            "models": ["m"],
            "default_model": "m",
            "custom": True,
        }
    )
    secrets.set(f"llm.provider.{pid}.api_key", "sk-test")
    yield pid, store, settings
    store.close()
    secrets.close()


class TestEmbed:
    async def test_vectors_and_usage(self, wired, monkeypatch) -> None:
        pid, store, settings = wired
        settings.model = "text-embedding-3-small"
        seen: dict = {}

        async def fake(provider, *, api_key, model, texts):
            seen.update(model=model, texts=list(texts), key=api_key)
            return EmbedResult(vectors=[[0.1, 0.2]] * len(texts), model=model, input_tokens=7)

        monkeypatch.setattr(embed_mod, "llm_embed", fake)
        out = await execute(registry, "embed", USER, {"provider_id": pid, "texts": ["a", "b"]})
        assert (
            out["vectors"] == [[0.1, 0.2], [0.1, 0.2]] and out["model"] == "text-embedding-3-small"
        )
        assert seen["key"] == "sk-test" and seen["texts"] == ["a", "b"]
        assert out["usage"] == {"input_tokens": 7, "output_tokens": 0}
        stats = store.usage_stats(1)
        assert stats["input_tokens"] >= 7

    async def test_unconfigured_model_is_invalid_input(self, wired) -> None:
        pid, _store, _settings = wired
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "embed", USER, {"provider_id": pid, "texts": ["a"]})
        assert exc.value.body.code == "LLM.INVALID_INPUT"
        assert "llm.embedding_model" in (exc.value.body.hint or "")

    async def test_provider_error_is_mapped_and_metered(self, wired, monkeypatch) -> None:
        pid, _store, settings = wired
        settings.model = "m-embed"

        async def boom(provider, *, api_key, model, texts):
            raise ProviderError("no embeddings endpoint", status=0)

        monkeypatch.setattr(embed_mod, "llm_embed", boom)
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "embed", USER, {"provider_id": pid, "texts": ["a"]})
        assert exc.value.body.code == "LLM.UNAVAILABLE"

    async def test_empty_texts_rejected(self, wired) -> None:
        pid, _store, settings = wired
        settings.model = "m-embed"
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "embed", USER, {"provider_id": pid, "texts": []})
        assert exc.value.body.code == "LLM.INVALID_INPUT"
