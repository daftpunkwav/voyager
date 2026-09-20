# Voyager documentation

English | [中文](README.zh.md)

Voyager is a local-first agent companion workbench: a Python backend (FastAPI + SQLite, `packages/` + `agent/`) and a React frontend (`apps/web`), composed into one process. This tree documents the code as it is. Start here, read [architecture.md](architecture.md) before changing composition or wiring, then go to the owning page listed below.

## Overview

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Source roots, layering, composition (host → gateway), the agent engine, event flow, dependency rules |
| [development.md](development.md) | Toolchain (uv / npm), startup, gate scripts, repository layout |
| [testing.md](testing.md) | Test layout, gates, the agent eval harness, dependency-graph check |

## Subsystems (`subsystems/`)

Index: [subsystems/README.md](subsystems/README.md).

| Page | Owns |
|---|---|
| [platform.md](subsystems/platform.md) | The eight `platform_*` framework packages: contracts, actor, eventbus, capability, settings, secrets, health, webguard |
| [capability-framework.md](subsystems/capability-framework.md) | `Capability`/`Registry`, REST and MCP generation, the guard chain, `Wiring`, audit sinks |
| [eventbus.md](subsystems/eventbus.md) | Event vocabulary (`DomainEvent`/`RuntimeEvent`), `EventLog`, `EventBus`, cursors, retention |
| [host.md](subsystems/host.md) | The composition root: card scanning, planning, shared facilities, domain tools bridge, cross-domain calls, LLM routing |
| [gateway.md](subsystems/gateway.md) | The HTTP carrier: auth, error envelope, mounts, chat/SSE/session/workspace/uploads routers, rate limiting |
| [llm.md](subsystems/llm.md) | The `llm` domain: providers, wire formats, usage metering, pricing, embeddings |
| [notes.md](subsystems/notes.md) | The `notes` domain: notes, versions, links, tags, assets, trash |
| [graph.md](subsystems/graph.md) | The `graph` domain: knowledge graph store, index queue, scheduler, C/Python engines, L0 relations |
| [sources.md](subsystems/sources.md) | The `sources` domain: repo/doc/web sources, workers, extraction, SSRF-guarded URL capture |
| [auxiliary-domains.md](subsystems/auxiliary-domains.md) | The `settings`, `browser`, `code_exec`, `office` domains |
| [agent-loop.md](subsystems/agent-loop.md) | The agent engine: assembly (`AgentApp`), event loop, turn driving, the ReAct round, termination, arbitration |
| [agent-tools.md](subsystems/agent-tools.md) | The tool surface: `Toolbelt`, permissions, the invocation pipeline, domain tool bridge, parity |
| [agent-context.md](subsystems/agent-context.md) | Context engineering: prompt assembly, budgets, prune/compact governance, prefix-cache watch |
| [agent-subagents.md](subsystems/agent-subagents.md) | Subagents: instances, task books, spawning, modes, orchestration (task graph, goals, proactive) |
| [agent-memory.md](subsystems/agent-memory.md) | Memory stores, distillation, sessions, skills, personas |
| [agent-runtime.md](subsystems/agent-runtime.md) | Agent runtime machinery: trajectory, session index, queue, scheduler, metering, deadlines, checkpoints, tracing |

## Catalogs (`catalog/`)

| Document | Contents |
|---|---|
| [tool-catalog.md](catalog/tool-catalog.md) | The agent tool surface: builtin tools, aggregated capability-backed tools, MCP naming, activation |
| [config-catalog.md](catalog/config-catalog.md) | Registered settings keys by owner, with types and declaring modules |
| [data-layout.md](catalog/data-layout.md) | Runtime data layout under `data/`: every store, its owning module, and retention |

## Frontend (`web/`)

| Document | Contents |
|---|---|
| [frontend.md](web/frontend.md) | `apps/web`: stack, routing, capability bridge, SSE stream, state stores, i18n, build |

## Process

| Document | Contents |
|---|---|
| [AGENTS.md](AGENTS.md) | The documentation standard: placement, bilingual pairing, writing rules |
| [i18n/README.md](i18n/README.md) | The bilingual pairing contract and consistency records |
