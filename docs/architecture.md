# Voyager Architecture

English | [中文](architecture.zh.md)

Read this before changing composition or wiring. Voyager is a local-first, single-user workbench: a Python backend composed into one process, and a browser frontend. There is no deployment topology beyond the local machine; all persistence is SQLite and files under `data/`.

## Source roots

| Root | Contents |
|---|---|
| `packages/platform/` | Eight framework packages (`platform_contracts`, `platform_actor`, `platform_eventbus`, `platform_capability`, `platform_settings`, `platform_secrets`, `platform_health`, `platform_webguard`) that carry no business logic |
| `packages/<domain>/` | Ten domain packages: `browser`, `code_exec`, `gateway`, `graph`, `host`, `llm`, `notes`, `office`, `settings`, `sources` — each a src-layout uv workspace member with a `service.json` card, `src/<domain>/`, and `tests/` |
| `agent/` | The agent engine (`src/agent/`): event-driven ReAct loop, tool surface, context engineering, memory, skills, subagents |
| `apps/web/` | The frontend: React 19 + TypeScript + Vite |
| `plugins/` | User plugins, declarative only (`plugin.json` + `skills/` + `hooks/` + `mcp.json`); loaded by the agent after explicit user approval |
| `data/` | All runtime state: `data/runtime/` (stores), `data/workspace/` (the working workspace) |

Every domain package follows the same scaffold (see `packages/_template/`): `service.json` (the module card), `src/<domain>/capabilities.py`, `wiring.py`, `rest.py`, `mcp_server.py`, `store.py`, `settings.py`.

## Layering and dependency rules

Dependencies point one way only, enforced by `import-linter.ini`:

```text
platform_*  ◀── { gateway, agent, every domain }  ◀── host
```

- `platform_*` packages never import business code.
- Domains never import each other. Cross-domain interaction happens only through two channels provided by host: late-bound capability calls (`host.call.bind_calls` → `call` / `call_sync`) and bus events (`platform_eventbus`).
- Only `host` imports `agent` and `gateway` (plus the domain wirings it assembles). `agent` imports `platform_*` only — never a domain.
- The `gateway` package imports no domain ("zero domain imports" in `packages/gateway/README.md`); domains reach it as mounted routers.

## Capability as the service unit

Every business operation is a `Capability` (`platform_capability/define.py`): a frozen dataclass binding a name, description, Pydantic input model, and handler, registered in a per-domain `Registry`. From one registration the framework projects two surfaces:

- REST: `build_router` emits `GET /capabilities` and `POST /capabilities/{name}`; host mounts every registry under `/api/<domain>` (`gateway/mounts.py`), so the uniform call shape is `POST /api/<domain>/capabilities/<name>`.
- MCP: `build_server` (`platform_capability/gen_mcp.py`) exposes the same registry over stdio via `python -m <domain>.mcp_server`.

Execution passes one guard chain (`platform_capability/guards.py`): actor auth → cost quota → argument validation → handler → audit. The same chain serves human REST calls and agent-invoked calls; the only difference is the `ActorRef` (`ActorKind.USER` vs `ActorKind.AGENT`). `agent/src/agent/parity.py` pins the human/agent surface-parity contract.

## Composition: host

`packages/host/src/host/assemble.py` (`build()`) is the composition root. Boot:

1. Construct shared facilities under `data/runtime/`: `EventLog` (events.db), `EventBus`, `SecretStore` (secrets.db), `SettingsStore` (settings.db), `SqliteAuditSink` (audit.db), `LocalTokenIssuer` (machine.token), `CostQuota`. Seed `os.environ` from repo `.env`.
2. Scan `packages/*/service.json` (`scan.py`) into `ServiceCard`s; select enabled domains (`ENABLE_DOMAINS` env → `host.domains.enabled` setting → card default) and topo-order them by `depends_on` (`plan.py`).
3. For each card, call `<module>.wiring.wire()` and inject the card-declared `needs` from a fixed set (`bus`, `secrets`, `settings_store`, `workspace`, `audit`, `quota`, `call`, `call_sync`). Unknown needs or kwargs fail startup. Adding a domain means dropping a directory with a `service.json`; no host edit.
4. Build the agent (`agent.build.build_agent`), bridging every wired domain registry into agent tools named `<domain>__<capability>` (`host/bridge.py`), and injecting LLM/embedding adapters over late-bound calls (`host/llm_routing.py`, `host/embedder_adapter.py`).
5. Hand all `MountSpec`s plus the extra routers (uploads, workspace, switch, jobs) to `gateway.rest.create_app` and serve the result on one port, **8000**.

The per-domain ports in `service.json` (8010–8080) apply only to standalone `uvicorn <domain>.rest:app_factory --factory` runs; in the composed process every domain lives behind 8000. The graph C-engine sidecar is the one external process (default `http://127.0.0.1:8123`).

## The agent engine

`agent/src/agent/` is an event-driven engine, not a request handler. `build.py:build_agent()` assembles an `AgentApp` (loop, master, tools, memory, stores) from `platform_*` primitives; `packages/host/src/host/assemble.py` calls it with the composed facilities. See [agent-loop.md](subsystems/agent-loop.md) for the turn lifecycle and [agent-tools.md](subsystems/agent-tools.md) for the tool surface.

Host integration points:

- Event wiring: agent's `EventLoop` subscribes to bus patterns; `user.message` triggers `Master.handle_user_message` (`agent/src/agent/runtime/wire.py`).
- Domain tools: `<domain>__<capability>` tools execute through the full guard chain as actor `agent.main` (`host/bridge.py`).
- LLM transport: `RoutingServiceLLM` / `PersonaRoutingServiceLLM` resolve provider/model per purpose via late-bound calls into the `llm` domain (`host/llm_routing.py`); the agent never imports the `llm` package.
- Embedding recall: `host/embedder_adapter.py` adapts `llm.embed` for agent memory vector search, degrading to `EmbeddingUnavailable`.

## Event flow

`platform_eventbus.EventLog` (SQLite `events.db`) is the append-only source of truth; `EventBus` fans out in-process; the browser subscribes over SSE.

```text
apps/web                    gateway :8000                     host/agent (one process)
   │  POST /api/chat/messages   │                                     │
   ├───────────────────────────▶│ publish user.message ──────▶ EventBus
   │                            │                        EventLoop → Master.handle_user_message
   │                            │                        _start_turn → SubagentInstance.run_turn
   │                            │                        ReAct rounds: LLM ⇄ tools
   │                            │                        emit agent.step / agent.delta / agent.message
   │  GET /api/chat/stream (SSE)│                                     │
   ◀────────────────────────────├◀── replay from log + live fan-out ──┘
```

Every durable fact reaches the model-visible history and the UI through the same log; the SSE endpoint replays missed rows from `after_seq`. Event vocabularies: [eventbus.md](subsystems/eventbus.md).

## Data

All state lives under `data/`: shared stores (`events.db`, `settings.db`, `secrets.db`, `audit.db`, `machine.token`) at `data/runtime/`, per-domain and per-agent SQLite stores under `data/runtime/<domain>/` and `data/runtime/agent/`, the working tree at `data/workspace/`. The full inventory, with owning modules and retention, is in [data-layout.md](catalog/data-layout.md).

## Running

- Development: `uv run python -m host.dev` — uvicorn `host.assemble:build` on 127.0.0.1:8000 plus Vite dev server on 127.0.0.1:5173 (proxies `/api` to 8000).
- Backend only: `uv run uvicorn host.assemble:build --factory --port 8000`.
- Frontend only: `npm run dev` in `apps/web`.
- Gates: `npm run gate` (Python and web suites, see [testing.md](testing.md)).
