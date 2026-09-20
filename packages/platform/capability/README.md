# platform/capability — Capability framework

**Define once, generate both protocols**:

- Definition: name, description (written for the LLM: when to use it, what it returns), input model, metadata (cost / reversible /
  scopes), handler;
- `gen_rest.build_router`: registry → FastAPI router (for the gateway);
- `gen_mcp.build_server`: registry → MCP server (for the agent / external clients);
- The entry point enforces three things (at the framework layer, not in the handler): authentication, rate/quota limits, audit;
- Long-task convention: the handler only enqueues and returns a `JobRef`; when `long_running=True`, not returning a JobRef counts as a defect;
- Adding a capability = one new registry entry, with zero changes across REST / MCP / agent.

fastapi is an optional dependency (extra `rest`); the MCP SDK is installed on demand. The base install has zero third-party dependencies.

---

## Purpose

Capability framework: @capability registration, Registry, execute() guard chain (auth -> quota -> validate -> invoke -> audit), REST/MCP generators, CostQuota, SqliteAuditSink.

## Configuration

None (sinks/quotas injected at the composition root).

## Extension Points

New guard type = one function composed in execute(); generators live in gen_rest/gen_mcp.

## Known Limitations

Quota is a single daily-budget implementation.

## Deferred Work

Per-actor quota dimensions.
