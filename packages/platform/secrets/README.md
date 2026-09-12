# platform/secrets — 密钥保管(骨架)

加密落盘、按需分发、日志与事件 payload 框架层脱敏(§7.7);
**secret 设置项的唯一写入口是用户本人经本包写入**(§8.8)。BYOK:用户填自己的
LLM key;无 key 时 agent 降级(§9.18)。

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
