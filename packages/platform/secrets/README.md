# platform/secrets — Secret keeping

> Language: **English** | [简体中文](README.zh.md)

Encrypted at rest, delivered on demand, and framework-level redaction of secrets in log and event payloads;
**the only write path for secret settings is the user writing through this package**. BYOK: the user fills in their own
LLM key; with no key the agent degrades.

---

## Purpose

Secret keeping: encrypted-at-rest sqlite (SECRETS_ENCRYPTION_KEY), get/set/has/delete by key; unavailable key material raises SecretUnavailableError.

## Configuration

SECRETS_ENCRYPTION_KEY env (set at the composition root).

## Extension Points

Nothing to extend — keys are namespaced per consumer (e.g. llm.provider.<id>.api_key).

## Known Limitations

Single machine key; no per-secret ACLs.

## Deferred Work

Key rotation tooling.
