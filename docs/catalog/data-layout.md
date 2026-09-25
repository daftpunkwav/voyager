# Data layout

English | [中文](data-layout.zh.md)

All runtime state lives under `data/`. The layout below is what the code creates; `data/runtime/README.md` documents a subset. In the composed process everything sits here; standalone domain runs default to `packages/<domain>/data/` instead.

## Shared stores (`packages/host/src/host/assemble.py`)

| Path | Owner | Contents | Retention |
|---|---|---|---|
| `data/runtime/events.db` | `platform_eventbus.EventLog` | the append-only event log | `agent.delta` rows purge after 24 h; other types accumulate |
| `data/runtime/settings.db` | `platform_settings.SettingsStore` | setting values | — |
| `data/runtime/secrets.db` | `platform_secrets.SecretStore` | Fernet-encrypted secrets | — |
| `data/runtime/audit.db` | `platform_capability.SqliteAuditSink` | capability call audit | — |
| `data/runtime/machine.token` | `platform_actor.LocalTokenIssuer` | local bearer token | — |

## Agent stores (`agent/src/agent/`, under `data/runtime/agent/`)

| Path | Owner | Contents | Retention |
|---|---|---|---|
| `sessions.db` | `sessions/store.py SessionStore` | chat sessions, active pointer | — |
| `trajectory.db` | `runtime/trajectory.py TrajectoryStore` | `steps`/`runs` projections, `raw_rounds` | raw rounds purge after 7 days |
| `session_index.db` | `runtime/session_index.py SessionIndex` | FTS5 index over chat messages | — |
| `queue.db` | `runtime/queue_store.py QueueStore` | durable queue (cron) | — |
| `meter.db` | `runtime/meter_store.py MeterStore` | LLM/tool usage | 90 days |
| `memory/profile.db`, `memory/episodic.db`, `memory/semantic.db` | `memory/` stores | profile, episodic trail, facts | `agent.memory.retention_days` (purge call) |
| `checkpoints/` | `runtime/state.py CheckpointStore` | resume snapshots | startup sweeps |
| `subagents/*.json` | `subagent/registry.py SubagentRegistry` | user-defined subagent definitions | — |
| `write_journal/` | write journal | content-addressed write backups | — |

## Domain stores (`data/runtime/<domain>/`)

| Path | Owner | Contents |
|---|---|---|
| `data/runtime/llm/llm.db` | `packages/llm` `ProviderStore` | providers, usage |
| `data/runtime/notes/notes.db` | `packages/notes` `NoteStore` | notes, versions, links, tags, trash |
| `data/runtime/notes/assets.db` | `packages/notes` `AssetStore` | attachment metadata (binaries in workspace) |
| `data/runtime/graph/graph.db` | `packages/graph` `GraphStore` | nodes, edges |
| `data/runtime/graph/index.db` | `packages/graph` `IndexQueue` | index jobs |
| `data/runtime/graph/engine-python/` | `packages/graph` Python engine | engine data root |
| `data/runtime/sources/repo.db`, `doc.db`, `web.db` | `packages/sources` | per-kind source records |
| `data/runtime/office/office.db` | `packages/office` `DocumentStore` | documents (`doc`/`slides`) |
| `data/runtime/browser/browser.db` | `packages/browser` `BrowserStore` | session metadata |
| `data/runtime/code_exec/code-exec.db` | `packages/code_exec` `ExecutionStore` | execution records |

## Workspace and engine caches

| Path | Purpose |
|---|---|
| `data/workspace/` | the working workspace (switchable via `agent.workspace.dir`, must stay inside the repo root); contains `skills/`, `hooks/`, `spill/`, `sandbox/`, `imports/`, `repo/` clones |
| `data/graph-db/` | Python graph engine graph files (`engines/python/engine.py`) |
| `data/graph-engine-cache/` | C engine sidecar cache (`ENGINE_CACHE_DIR`) |
