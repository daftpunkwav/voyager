# LLM domain

English | [中文](llm.zh.md)

The `llm` domain owns every model interaction in the composed system: provider management, completions and streaming, usage metering, pricing, and embeddings. The agent never imports this package; host wires the agent's chat transport to it through late-bound calls ([host.md](host.md)).

Source: `packages/llm/src/llm/` — port 8070, enabled by default, store `data/runtime/llm/llm.db`.

## Capabilities

`Registry("llm")`, one module per capability under `capabilities/`:

- Provider management: `list_builtin_providers`, `list_providers`, `get_provider_defaults`, `add_provider`, `update_provider`, `remove_provider`, `set_api_key`
- Models: `list_models`, `list_remote_models`, `test_connection`
- Inference: `complete` (cost 10), `complete_stream` (streaming)
- Telemetry: `get_usage_stats`
- Embeddings: `embed`

## Client

`client.py` uses plain httpx (no litellm). One client covers three wire formats selected per provider's `api_format`:

- `chat` — OpenAI `/chat/completions`
- `anthropic` — `/v1/messages`
- `responses` — OpenAI `/v1/responses` (parser in `wire_responses.py`)

Tools travel in a neutral format (`[{"name", "description", "schema"}]`) and are translated per wire format. Upstream errors are classified (rate limit / auth / context overflow / transient) and retried with a bound of 2 attempts and 0.5 s backoff, honoring `Retry-After` capped at 5 s.

## Storage

`store.py` — `ProviderStore` (SQLite `llm.db`): `providers` (base_url, api_format, models, enabled, custom) and `usage` (ts, provider_id, model, caller, input/output/cached/reasoning/cache-write tokens, ok). API keys are never stored here — they go to `SecretStore` (`platform_secrets`). `catalog.py` holds `BUILTIN_PROVIDERS` presets (e.g. `openai`, `openai-responses`, `anthropic`, `deepseek`, `moonshot`).

## Usage and pricing

`complete` meters every call, including failures (`ok=0`). `get_usage_stats` aggregates from the `usage` table. `pricing.py` converts tokens to cost read-side only, from the `llm.pricing` setting (`{"<model or prefix>": {"input", "output"}}` in USD per 1M tokens, longest-prefix match); unpriced models produce no cost. `configured_reasoning_effort()` hot-reads `llm.reasoning_effort` (`low`/`medium`/`high`/empty).

Both inference capabilities return normalized response metadata on top of the answer text: `finish_reason` (per wire format — chat `finish_reason`, anthropic `stop_reason`, responses `status`), `request_id` (from `x-request-id` / `request-id` / `anthropic-request-id` / `cf-ray`), `response_id` (responses format), `service_tier`, `stop_sequence`, and `created`; usage is refined with `reasoning_tokens` and `cache_write_tokens` per format. Provider rejections carry the `request_id` and a dump path of the exact rejected request. On the anthropic wire the streaming parser treats `message_delta.usage` as the authoritative cumulative usage (non-zero fields override the `message_start` snapshot — the current contract also followed by compatible endpoints that report 0 placeholders in `message_start`). `complete`'s `max_tokens` input uses `0` as "auto": the cap then comes from `llm.max_output_tokens`.

## Settings

`llm.default_provider`, `llm.default_model`, `llm.temperature`, `llm.max_output_tokens`, `llm.embedding_model`, `llm.reasoning_effort`, `llm.pricing`.

## Consumers

- Host LLM routing (`host/llm_routing.py`) — agent chat, arbiter, distiller, and context-planner purposes resolve here per `agent.llm.routing` / `agent.llm.overrides`.
- Host embedder adapter (`host/embedder_adapter.py`) — agent memory vector recall via `call_sync("llm", "embed", ...)`.
- Frontend settings pages — provider/model management and the usage dashboard call `llm` capabilities directly over REST.
