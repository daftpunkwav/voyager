"""embeddings.embed transport: the chat-format POST {base}/embeddings twin
of client.complete — vectors back in input order regardless of response
order, usage metering from either usage field, non-chat providers refused up
front, and a short response degraded with a classified ProviderError.

Unit tests: the HTTP layer is stubbed at the module boundary (the _post
helper embeddings shares with client); retry plumbing stays real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from llm import embeddings
from llm.client import ProviderError

_CHAT = {"api_format": "chat", "base_url": "https://api.example.com/v1/"}


@dataclass
class _FakeResponse:
    status_code: int = 200
    _payload: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return self._payload


class TestEmbed:
    async def test_vectors_sorted_by_index_with_usage(self, monkeypatch) -> None:
        seen: dict[str, Any] = {}

        async def fake_post(client, url, *, headers, body):
            seen.update(url=url, headers=headers, body=body)
            return _FakeResponse(
                _payload={
                    "model": "text-embedding-3-small",
                    "data": [
                        {"index": 1, "embedding": [3, 4]},
                        {"index": 0, "embedding": [1, 2]},
                    ],
                    "usage": {"prompt_tokens": 9},
                }
            )

        monkeypatch.setattr(embeddings, "_post", fake_post)
        out = await embeddings.embed(_CHAT, api_key="sk-test", model="m", texts=["a", "b"])
        # response order is arbitrary: vectors must come back in input order
        assert out.vectors == [[1.0, 2.0], [3.0, 4.0]]
        assert out.model == "text-embedding-3-small" and out.input_tokens == 9
        assert seen["url"] == "https://api.example.com/v1/embeddings"  # trailing / trimmed
        assert seen["headers"]["Authorization"] == "Bearer sk-test"
        assert seen["body"] == {"model": "m", "input": ["a", "b"]}

    async def test_usage_falls_back_to_input_tokens(self, monkeypatch) -> None:
        async def fake_post(client, url, *, headers, body):
            return _FakeResponse(
                _payload={
                    "data": [{"index": 0, "embedding": []}],
                    "usage": {"input_tokens": 4},
                }
            )

        monkeypatch.setattr(embeddings, "_post", fake_post)
        out = await embeddings.embed(_CHAT, api_key="k", model="m", texts=["a"])
        assert out.vectors == [[]] and out.input_tokens == 4 and out.model == "m"

    async def test_non_chat_provider_refused_up_front(self, monkeypatch) -> None:
        async def fail_post(client, url, *, headers, body):  # pragma: no cover - must not run
            raise AssertionError("non-chat providers must not reach the wire")

        monkeypatch.setattr(embeddings, "_post", fail_post)
        anthropic = {"api_format": "anthropic", "base_url": "https://x.test/v1"}
        with pytest.raises(ProviderError) as exc:
            await embeddings.embed(anthropic, api_key="k", model="m", texts=["a"])
        assert exc.value.status == 0 and "anthropic" in str(exc.value)
        # a missing api_format is equally refused (no KeyError, no request)
        with pytest.raises(ProviderError):
            await embeddings.embed(
                {"base_url": "https://x.test/v1"}, api_key="k", model="m", texts=["a"]
            )

    async def test_short_response_is_classified_provider_error(self, monkeypatch) -> None:
        async def fake_post(client, url, *, headers, body):
            return _FakeResponse(
                _payload={"data": [{"index": 0, "embedding": [1]}]}, status_code=200
            )

        monkeypatch.setattr(embeddings, "_post", fake_post)
        with pytest.raises(ProviderError) as exc:
            await embeddings.embed(_CHAT, api_key="k", model="m", texts=["a", "b"])
        assert exc.value.status == 200 and "2 inputs" in str(exc.value)

    async def test_missing_data_section_counts_as_zero_vectors(self, monkeypatch) -> None:
        async def fake_post(client, url, *, headers, body):
            return _FakeResponse(_payload={}, status_code=500)

        monkeypatch.setattr(embeddings, "_post", fake_post)
        with pytest.raises(ProviderError) as exc:
            await embeddings.embed(_CHAT, api_key="k", model="m", texts=["a"])
        assert exc.value.status == 500 and "1 inputs" in str(exc.value)
