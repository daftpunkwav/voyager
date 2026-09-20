# host (src) — composition root

This directory implements the composition root: it discovers domain packages, wires them, bridges their capabilities to agent tools, and mounts everything behind the gateway in one process. The package-level contract lives in [packages/host/README.md](../../../README.md); the subsystem walkthrough lives in [docs/subsystems/host.md](../../../../docs/subsystems/host.md). This file only maps what each file here contains.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring; declares `host.assemble.build` as the public assembly entry and forbids imports from `agent/` or domain implementations. |
| `agent_rebuild.py` | Restartless agent workspace rebuild: rebinds the agent app (jails, cwd, skills, hooks, MCP cwd) around a new workspace while shared facilities and domain wirings stay up. |
| `assemble.py` | Monolithic composition root: owns shared facilities (event log/bus, secrets, settings, audit, issuer, quota), seeds env from the repo `.env`, wires scanned domains via their `wire()`, builds agent tools from the mount list, and runs the unified lifespan. |
| `bridge.py` | Wraps domain capability registries into agent `AgentTool`s named `<domain>__<capability>`, executing them through the capability-framework guard chain with the agent principal. |
| `call.py` | Late-bound cross-domain calls: `call` / `call_sync` route through `execute()` so they ride the same auth/quota/audit chain; the composition root never imports a neighbor domain. |
| `dev.py` | Dev launcher: backend (uvicorn :8000) plus web (vite :5173) via `python -m host.dev`. |
| `embedder_adapter.py` | `ServiceEmbedder`: adapts the llm domain's `embed` capability (via `call_sync`) to `memory.vector.EmbeddingFn`; every failure surfaces as `EmbeddingUnavailable`. |
| `jobs_router.py` | Maps a projected background job to its source domain's cancel/reorder capability and runs it through the late-bound call. |
| `lifecycle.py` | `start_wirings` / stop / close with rollback: start in wire order, stop and close in reverse; mid-stop failures are logged, not fatal. |
| `llm_adapter.py` | `ServiceLLM`: adapts the llm domain's `complete` / `complete_stream` capabilities to the `agent.llm.LLMClient` protocol. |
| `llm_routing.py` | Purpose-based model routing and fallback chains: routing-table entry, then explicit provider/model, then default resolution; a hop that still has a next entry emits an `llm.fallback` event before the chain moves on. |
| `plan.py` | Assembly planning: select the enabled domain subset, topologically order cards by `depends_on` (Kahn's algorithm), register gateway-role settings. Pure planning — no wiring. |
| `scan.py` | Domain discovery: reads each directory's `service.json` module card into a `ServiceCard`; skips scaffolding, reserved dirs, and broken cards without failing startup. |
| `settings.py` | Composition-root `SettingDef`s (`host.domains.enabled` whitelist). |

## Notes

- Discovery reads cards, never code (`scan.py` imports no domain implementation); the wiring loop lives in `assemble.py`.
- The assembly sequence is scan (`scan.py`) → plan (`plan.py`) → wire and mount (`assemble.py`), with `lifecycle.py` driving ordered start/stop.
