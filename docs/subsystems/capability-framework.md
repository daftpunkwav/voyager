# Capability framework

English | [中文](capability-framework.zh.md)

`platform_capability` turns a registered function into three coordinated surfaces: an in-process callable, a REST endpoint, and an MCP tool. Every domain builds on it; the agent's own capability registry uses the same framework.

Source: `packages/platform/capability/src/platform_capability/`

## `Capability` — the unit of service

```python
# define.py
@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    handler: Callable
    input_model: type          # Pydantic/dataclass input schema
    cost: int = 1
    reversible: bool = True
    write: bool = True
    scopes: frozenset = frozenset()
    long_running: bool = False
    streaming: bool = False
    dimension: str = "app"     # app | network | ...
```

`dimension` drives policy: agent calls with `dimension="network"` pass the network policy gate, `dimension="fs"` the filesystem gate. `write`/`reversible` feed the tool classification used by agent permissions. `long_running=True` marks capabilities that enqueue background work and return a `JobRef`.

## Registry and registration

`registry.py` — `Registry(domain)` holds the domain's capabilities with `register`/`get`/`names`/`all`/`merge`; duplicate names raise `ServiceError(CONFLICT)`. The `@capability(registry, name=..., description=..., ...)` decorator (`define.py`) registers the decorated function and derives the input schema from its Pydantic model or dataclass.

Domains typically declare one registry per concern module and merge them (`sources`: `repo`/`doc`/`web`; `office`: `doc`/`slides`; `notes`: `batch`/`catalog`/`history`/`lifecycle`/`transfer`/`view`).

## REST generation

`gen_rest.py` — `build_router(registry, issuer, auth, quota, audit)` emits two routes per registry, mounted by host at `/api/<domain>`:

- `GET /capabilities` — the listing with input schemas.
- `POST /capabilities/{name}` — the invocation; returns `{"result": ...}` or the `ErrorEnvelope`.

`rest.py` in each domain wraps `build_router` in `create_app()` for standalone runs (`uvicorn <domain>.rest:app_factory --factory --port <port>`).

## MCP generation

`gen_mcp.py` — `build_server` exposes the registry over MCP stdio (`python -m <domain>.mcp_server`); `build_tool_specs` and `dataclass_to_json_schema` convert capability input models to MCP tool schemas.

## Guard chain

`guards.py` — `execute()` runs every invocation through one chain, regardless of caller:

1. **Auth** — the injected authenticator resolves the `ActorContext` (REST: `platform_actor.resolve_http_actor`; in-process calls carry their actor explicitly).
2. **Quota** — `CostQuota` enforces the daily token budget (`cost` per call).
3. **Validation** — the input model validates the payload.
4. **Handler** — the capability function runs.
5. **Audit** — the `AuditSink` records the call.

`LocalAuth` is the pass-through authenticator for standalone runs. `CallRequest` is the in-process invocation carrier (`actor`, `name`, `args`).

## Audit sinks

`guards.py` + `audit_db.py` — `AuditSink` is the protocol; `InMemoryAuditSink` for tests, `SqliteAuditSink` (`audit.db`) for composed runs. Host injects one shared sink into every registry.

## Wiring

`wiring.py` — `Wiring(registry, probe, start, stop, close, extra_router)` is what a domain's `wire()` returns to host: the registry to mount, the health `probe`, lifecycle hooks (`start`/`stop`/`close` for workers and stores), and an optional `extra_router` for non-capability endpoints (e.g. notes assets, sources file preview).
