# llm.capabilities — the llm domain's registered capabilities

This directory implements the capabilities of the llm domain, one file per capability, each registered into the shared `Registry("llm")` on import (`__init__.py` imports every module for its registration side effect and exposes `Deps` / `init_deps` / `registry`). The package-level contract lives in [packages/llm/README.md](../../../README.md); the subsystem walkthrough lives in [docs/subsystems/llm.md](../../../../../docs/subsystems/llm.md). This file only maps what each file here contains.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Imports all capability modules to trigger registration; public entry points `Deps` / `init_deps` / `registry`. |
| `add_provider.py` | `add_provider`: stores provider metadata (validated `base_url`); accepts no api key. |
| `common.py` | Shared mechanisms: the domain registry, the `Deps` container, provider/key lookups, `base_url` validation, and `ProviderError` → `ServiceError` mapping. |
| `complete.py` | `complete`: chat completion with direct usage metering (also on failure); unknown `reasoning_effort` values degrade to unset. |
| `complete_stream.py` | `complete_stream`: streaming completion, in-process only — REST rejects it. |
| `embed.py` | `embed`: batch text embeddings with input-token metering; model defaults to the `llm.embedding_model` setting. |
| `get_provider_defaults.py` | `get_provider_defaults`: base_url/format/models of a built-in preset. |
| `get_usage_stats.py` | `get_usage_stats`: day-grouped usage stats by model, with read-side cost conversion when the `llm.pricing` table covers a model. |
| `list_builtin_providers.py` | `list_builtin_providers`: the built-in provider catalog from `llm.catalog`. |
| `list_models.py` | `list_models`: a provider's model list plus its `models_meta`. |
| `list_providers.py` | `list_providers`: configured providers with a `has_api_key` flag, never the key itself. |
| `list_remote_models.py` | `list_remote_models`: one live GET against the provider's `base_url` to fetch its model id catalog (read-only, no retries). |
| `remove_provider.py` | `remove_provider`: deletes a provider and clears its key from `platform/secrets`. |
| `set_api_key.py` | `set_api_key`: user-only secret write into `platform/secrets` under `key_name(provider_id)`. |
| `test_connection.py` | `test_connection`: one minimal real request; returns latency or the classified error. |
| `update_provider.py` | `update_provider`: metadata update; `base_url` changes are restricted to the user actor. |

## Notes

- Secret boundary (per `common.py` / `set_api_key.py`): keys live only in `platform/secrets`; provider dicts carry a `has_api_key` flag.
- Provider CRUD capabilities delegate persistence to `llm.store.ProviderStore`; call capabilities delegate transport to `llm.client` / `llm.stream` / `llm.embeddings`.
