# Platform packages

English | [中文](platform.zh.md)

`packages/platform/` holds eight independent, dependency-light framework packages. They carry all shared machinery — types, auth, events, the capability framework, settings, secrets, health, and URL safety — and no business logic. Import direction is one-way: business code imports `platform_*`; `platform_*` never imports business code (enforced by `import-linter.ini`, contract `platform-no-business`).

## platform_contracts

`packages/platform/contracts/src/platform_contracts/` — pure shared types, zero dependencies. `events.py` defines the event vocabularies `DomainEvent` (cross-domain bus events, e.g. `user.message`, `task.completed`, `agent.step`) and `RuntimeEvent` (agent run lifecycle). `models.py` defines `ActorRef`/`ActorKind`, `JobRef`/`JobStatus`, `HealthReport`/`HealthStatus`. `errors.py` defines `ServiceError` (error `code` + message + hint), the `ErrorEnvelope` wire shape, and `HTTP_STATUS` mapping. Version constants (`PROTOCOL_VERSION`, `ENVELOPE_VERSION`) and `new_trace_id()` live here.

## platform_actor

`packages/platform/actor/src/platform_actor/` — the actor model behind every guard chain. `ActorContext` carries the resolved `ActorRef` plus scopes. `LocalTokenIssuer` mints bearer tokens (`machine.token`); `resolve_http_actor` resolves the caller of an HTTP request from `Authorization: Bearer` or the session cookie (`COOKIE_NAME`), treating unauthenticated loopback requests as `LOCAL_USER` and rejecting unauthenticated non-loopback requests. `is_loopback`/`is_public_path` support that decision.

## platform_eventbus

`packages/platform/eventbus/src/platform_eventbus/` — the append-only log plus in-process fan-out. `EventLog` persists every `Event` to a SQLite `events` table keyed by autoincrement `seq`, with `Retention` sweeps (the host retains only `agent.delta` rows, for 24 h). `EventBus` delivers to in-process async subscribers and flags them `lagged` when they fall behind; consumers replay from the log by `seq`. `CursorStore` persists per-subscriber cursors. Full reference: [eventbus.md](eventbus.md).

## platform_capability

`packages/platform/capability/src/platform_capability/` — the capability framework: `Capability`/`Registry`/`@capability`, REST router generation (`gen_rest.py`), MCP server generation (`gen_mcp.py`), the guard chain (`guards.py`), `Wiring` (`wiring.py`), and audit sinks (`audit_db.py`). Full reference: [capability-framework.md](capability-framework.md).

## platform_settings

`packages/platform/settings/src/platform_settings/` — the settings framework. `SettingDef` declares a key with a type (`STR`/`INT`/`FLOAT`/`BOOL`/`CHOICE`/`JSON`), default, and flags (`secret`, `user_only`). `validate` coerces and checks values against the definition. `SettingsStore` persists values in a SQLite `setting_values` table, refuses writes to `secret` items through the business layer, and publishes `settings.changed` on every commit. Keys are registered by owners at wire time; the catalog of registered keys is in [config-catalog.md](../catalog/config-catalog.md).

## platform_secrets

`packages/platform/secrets/src/platform_secrets/` — encrypted secret storage. `SecretStore` stores values Fernet-encrypted in a SQLite `secrets` table; key material comes from the environment (`load_key_material`), never from the database. `SecretUnavailableError` signals a missing or undecryptable key. Providers hold API keys here, not in provider metadata.

## platform_health

`packages/platform/health/src/platform_health/` — `HealthMonitor` aggregates `Probe` results into `HealthReport`s; the gateway exposes the aggregate at `GET /health`.

## platform_webguard

`packages/platform/webguard/src/platform_webguard/` — shared outbound-URL safety used by `sources.save_url` and agent web tools: `url_policy` (scheme/host rules), `dns_pin` (resolve, validate, pin the IP for the connection), `redirects` (per-hop re-validation), and `body` size caps (`read_bounded`).
