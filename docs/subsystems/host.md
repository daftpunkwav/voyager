# Host (composition root)

English | [中文](host.zh.md)

`host` is the only package that imports `agent`, `gateway`, and every domain wiring. It owns boot, the shared facilities, the cross-domain channels, and the agent↔domain bridges. It is not a routable domain; it composes everything into one gateway app on port 8000.

Source: `packages/host/src/host/`

## Boot pipeline

1. **Scan** (`scan.py`) — `scan(root, prefix)` reads each `packages/*/service.json` into a `ServiceCard` (`domain`, `module`, `port`, `capabilities`, `subscribes`, `publishes`, `needs`, `depends_on`, `enabled_by_default`, `role`). Discovery reads the card, never code. `_`-prefixed directories and `SKIP_DIR_NAMES = {"platform", "host"}` are skipped.
2. **Plan** (`plan.py`) — `select_enabled` resolves the enabled set: `ENABLE_DOMAINS` env → `host.domains.enabled` setting → card `enabled_by_default`. `topo_order` orders them by `depends_on` (Kahn; a cycle refuses boot). Gateway-role cards register their settings.
3. **Assemble** (`assemble.py`) — `build()` (served as `uvicorn host.assemble:build --factory`) constructs shared facilities under `data/runtime/`, wires each enabled domain, builds the agent, and hands everything to `gateway.rest.create_app`.
4. **Dev entry** (`dev.py`) — `python -m host.dev` spawns `npm run dev` in `apps/web` and runs uvicorn on `127.0.0.1:8000`; Ctrl+C tears down both.

## Shared facilities

`build()` constructs, once per process, under `data/runtime/`: `EventLog` (`events.db`, retention for `agent.delta` at 24 h), `EventBus`, `SecretStore` (`secrets.db`), `SettingsStore` (`settings.db`), `SqliteAuditSink` (`audit.db`), `LocalTokenIssuer` (`machine.token`), `[CostQuota(daily budget 50 000)]`. `os.environ` is seeded from the repo `.env` at import. Each domain gets `data_dir = data/runtime/<domain>/`; the agent gets `data/runtime/agent/`.

## Wiring injection

For each enabled card, `_wire_card` imports `<module>.wiring.wire()` and injects the card-declared `needs` from the fixed set `SHARED_KEYS = {bus, secrets, settings_store, workspace, audit, quota, call, call_sync}`. Unknown needs or unknown kwargs fail startup. The returned `Wiring` contributes a `MountSpec(domain, registry, probe, extra_router)`.

## Agent integration

- **`bridge.py`** — `make_domain_tools(mounts)` produces agent tools named `<domain>__<capability>`; execution goes through the full guard chain as actor `ActorRef(kind=AGENT, id="agent.main", scopes=("domain:*",))`.
- **`llm_routing.py`** — `ServiceLLM`, `RoutingServiceLLM`, `PersonaRoutingServiceLLM` resolve the chat transport per purpose and per persona via late-bound calls into the `llm` domain; settings `agent.llm.overrides` and `agent.llm.routing` steer the resolution. `embedder_adapter.py` adapts `llm.embed` for agent memory vector recall, degrading to `EmbeddingUnavailable`.
- **`agent_rebuild.py`** — restartless workspace switch behind `POST /api/workspace/switch`; `jobs_router.py` exposes job cancel/reorder endpoints backed by `JobsView` over the event log.

## Cross-domain calls

`call.py` — `bind_calls(wirings)` returns `call` / `call_sync(domain, name, args)`, the only sanctioned channel between domains. Calls execute through the guard chain as the `HOST_ACTOR` (`ActorKind.SYSTEM`, wildcard scope). Users: graph L0 → `sources.list_sources`; host LLM routing → `llm.*`; embedder → `llm.embed`.

## Settings registered by host

`host/settings.py` and `plan.py` register `host.domains.enabled` and the gateway keys (`gateway.chat.history_page_size`, `gateway.rate_limit.per_minute`, `gateway.sse.max_connections`); `host/plan.py` also carries the parity test fixture used by `test_settings_parity.py`.
