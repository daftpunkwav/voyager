# llm (src) — implementation of the llm domain

This directory holds the llm domain implementation: the provider catalog, direct HTTP clients for three wire formats, usage metering, price-table cost conversion, and the capability layer under `capabilities/`. The package-level contract lives in [packages/llm/README.md](../../../README.md); the subsystem walkthrough lives in [docs/subsystems/llm.md](../../../../docs/subsystems/llm.md). This file only maps what each file here contains.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `catalog.py` | `BUILTIN_PROVIDERS`: pure-data provider presets across three API formats (`chat`, `anthropic`, `responses`); custom providers are not registered here. |
| `client.py` | Direct httpx LLM client: sends the three wire formats, normalizes the neutral tools format and tool calls, classifies upstream errors, and retries retriable ones with bounded backoff. |
| `embeddings.py` | `embed()` against chat-format providers (`POST {base}/embeddings`); providers on any other API format are refused up front with a classified error. |
| `inline_split.py` | Splits inline `<think>` / `<tool_call>` pseudo-XML out of content text (state-machine `InlineTagSplitter` for streams, `split_inline` for one-shot). |
| `mcp_server.py` | Exposes the registry as an MCP server over stdio (`python -m llm.mcp_server`). |
| `pricing.py` | Read-side token-to-USD conversion against the `llm.pricing` table (exact match, then longest prefix); unpriced models report no cost. |
| `rest.py` | REST entry point: `create_app` / `app_factory`; thin HTTP shell around `wiring.wire`. |
| `settings.py` | `SettingDef`s for `llm.*` keys (default provider/model, sampling, embedding model, price table). |
| `store.py` | `ProviderStore`: provider metadata plus directly-written usage rows in SQLite; API keys never live here (they stay in `platform/secrets`). |
| `stream.py` | Streaming client: line-by-line SSE parsing per wire format, delta aggregation into a final chunk shaped like `complete`'s return, same error classification. |
| `wire_responses.py` | The OpenAI Responses wire format: encodes the neutral message/tools history into `instructions` + typed input items and parses typed output/delta events. |
| `wiring.py` | `wire()`: builds the store, injects `Deps`, registers settings; accepts shared `SecretStore` / `SettingsStore` in aggregate runs. |
| `capabilities/` | One capability per file, registered into the shared `Registry("llm")` — see [capabilities/README.md](capabilities/README.md). |

## Entry points

- Standalone HTTP: `uvicorn llm.rest:app_factory --factory --port 8070` (per `rest.py` docstring).
- Assembly: `wire()` in `wiring.py` is the single wiring source used both here and by `packages/host/`.
- MCP: `python -m llm.mcp_server` (requires `mcp>=1.0`).
