# llm

> Language: **English** | [简体中文](README.zh.md)

## Purpose

LLM domain: provider catalog, chat/stream/embedding calls, usage metering, price-table cost conversion.

## Configuration

llm.* settings: default provider/model, sampling, embedding model, price table (llm.pricing).

## Extension Points

New provider = catalog preset; new call type = one client module + one capability file under capabilities/.

## Model Experience

Tools: llm__complete / complete_stream / embed / get_usage_stats. Agents rarely call these directly — the harness transport does. complete fails soft with classified errors (rate limit / auth / overflow).

## Known Limitations

Embeddings only on chat-format providers (OpenAI-compatible).

## Deferred Work

Per-purpose provider health tracking.
