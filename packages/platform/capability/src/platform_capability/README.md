# platform_capability — capability framework implementation

Implementation of the capability framework: define a capability once (`@capability` + `Registry`), generate both protocols (FastAPI router and MCP server), and enforce the entry-point guard chain (auth → quota → audit) in one place. Package-level contract lives in [packages/platform/capability/README.md](../../README.md); the framework is detailed in [docs/subsystems/capability-framework.md](../../../../../docs/subsystems/capability-framework.md). This README is only a map of the files in this directory.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Public exports (`Capability`, `capability`, `Registry`, `execute`, `build_router`, `build_server`, `SqliteAuditSink`, `Wiring`, ...). |
| `define.py` | `@capability` decorator and the frozen `Capability` metadata record (name, LLM-facing description, input model, cost / reversible / write / scopes / long_running / streaming / dimension) plus `coerce_input` for shallow dataclass input validation. |
| `registry.py` | `Registry`: per-service (or sub-module) capability table; `merge()` folds sub-module registries into an aggregate one, and name conflicts raise immediately instead of overwriting; the domain doubles as the error-code prefix. |
| `guards.py` | `execute()`: the guard chain run for every invocation (auth → quota → handler → audit); `LocalAuth` scope rejection, `CostQuota` per-actor daily budget (429 on excess), `AuditSink` protocol with `InMemoryAuditSink`, `SENSITIVE_KEYS` redaction in audit summaries. Enforced at the framework layer; handlers never implement these. |
| `audit_db.py` | `SqliteAuditSink`: SQLite-backed audit persistence with indexes on ts / trace_id / capability, wired at the composition root so audits survive restarts. |
| `gen_rest.py` | `build_router`: registry → FastAPI router (GET `{prefix}` lists capabilities, POST `{prefix}/{name}` invokes one; `JobRef` maps to 202 Accepted, `ServiceError` to the unified error body). fastapi is an optional dependency. |
| `gen_mcp.py` | `build_server`: registry → MCP server over stdio (SDK imported only here); `build_tool_specs` / `dataclass_to_json_schema` / `capability_input_schema` are pure functions, reused by REST capability listing. |
| `wiring.py` | `Wiring`: the dataclass protocol for a service's assembled artifacts (registry, probe, start / stop, close, extra_router) — the shape every domain `wire()` returns so standalone and composition-root mounting share one assembly point. |

## Notes

- Long-task convention is validated here, not in handlers: `define.py` declares the `long_running` / `streaming` flags, `guards.py` enforces at invoke time that a `long_running=True` handler returns a `JobRef` (enqueue only), and `gen_rest.py` maps the `JobRef` to 202 and rejects `streaming` capabilities (which return `AsyncIterator[dict]`) on the REST channel.
- fastapi and the MCP SDK are optional dependencies, imported only inside `gen_rest.py` / `gen_mcp.py` when their build functions are called; the pure helpers in `gen_mcp.py` work without either.
