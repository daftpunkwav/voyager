# Subsystems

English | [中文](README.zh.md)

One page per backend subsystem or domain: what it is, its types, endpoints, storage, and events. These pages complement [architecture.md](../architecture.md), which describes the layering, composition, and event flow across subsystems.

| Page | Owns |
|---|---|
| [platform.md](platform.md) | the eight `platform_*` framework packages: contracts, actor, eventbus, capability, settings, secrets, health, webguard |
| [capability-framework.md](capability-framework.md) | `Capability`/`Registry`, the `@capability` decorator, REST/MCP generation, the guard chain, `Wiring`, audit sinks |
| [eventbus.md](eventbus.md) | the event vocabulary (`DomainEvent`/`RuntimeEvent`), `EventLog`, `EventBus`, cursors, retention |
| [host.md](host.md) | the composition root: scanning, planning, shared facilities, wiring injection, the domain-tools bridge, cross-domain calls, LLM routing, workspace switch |
| [gateway.md](gateway.md) | the HTTP carrier: `create_app`, security headers, actor auth, error envelope, mounts, chat/SSE/session/activity/workspace/uploads routers, rate limiting, health |
| [llm.md](llm.md) | the `llm` domain: provider management, wire formats (`chat`/`anthropic`/`responses`), usage metering, pricing, embeddings |
| [notes.md](notes.md) | the `notes` domain: notes, version history, wiki links and backlinks, tags, assets, saved views, trash |
| [graph.md](graph.md) | the `graph` domain: the canonical graph store, index queue and scheduler, C/Python engines, code and L0 pipelines |
| [sources.md](sources.md) | the `sources` domain: repo/doc/web source kinds, background workers, document extraction, SSRF-guarded URL capture |
| [auxiliary-domains.md](auxiliary-domains.md) | the `settings`, `browser`, `code_exec`, `office` domains |
| [agent-loop.md](agent-loop.md) | the agent engine: `AgentApp`, the event loop, turn driving, the ReAct round, termination paths, arbitration |
| [agent-tools.md](agent-tools.md) | the agent tool surface: `AgentTool`/`Toolbelt`, permissions and policy, the invocation pipeline, result spill, domain tool bridge, parity |
| [agent-context.md](agent-context.md) | context engineering: prompt assembly layers, budgets, the context governor (prune/compact), prefix-cache watch, page context |
| [agent-subagents.md](agent-subagents.md) | subagents: `SubagentInstance`, task books, `Spawner`, the registry, modes, orchestration (task graph, blackboard, goals, proactive) |
| [agent-memory.md](agent-memory.md) | memory: profile/episodic/semantic/working stores, recall, distillation, chat sessions, skills, personas |
| [agent-runtime.md](agent-runtime.md) | agent runtime machinery: trajectory, session index, durable queue, scheduler, metering and quota, deadlines, retries and breakers, checkpoints, tracing, hooks, plugins |
