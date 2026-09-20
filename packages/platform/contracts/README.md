# platform/contracts — Contracts package

The **pure-type** layer shared across modules: event envelopes, capability input/output DTOs, unified error codes, protocol version.

Iron rules:

- Pure types, zero logic, **zero third-party dependencies**;
- The only package referenced directly by all three of apps / agent / services;
- Frontend TS types are generated from this package so all three sides share one understanding;
- Protocol changes bump `PROTOCOL_VERSION` in `version.py`.

The import name is `platform_contracts` (to avoid clashing with the standard-library `platform`).

## Glossary (one term, one meaning; shared repo-wide)

| Term                 | Sole meaning                                                                                                                                         | Boundary                                                                                                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **capability**       | A capability a domain service/agent registers in the registry (schema + handler + metadata); REST and MCP are both generated from the registry | Exists only in the `Registry`; its name is the name registered in `service.json`                                                                                                  |
| **tool (AgentTool)** | An LLM-callable tool on the agent side, mounted on the Toolbelt tool surface                                                                         | Domain capabilities are bridged via `host.bridge.make_domain_tools` into `<domain>__<capability>`; the agent's built-in tools (fs/shell/web/spawn…) do not come from the registry |
| **skill**            | A SKILL.md knowledge pack; once loaded it enters the system context                                                                                  | Not a tool, not executable; it only injects prompts                                                                                                                               |
| **MCP server**       | An **external** server the user adds and approves on the settings page, mounted into the tool surface via McpClientPool                              | Never use it to re-feed this repo's own `<domain>/mcp_server` (in the monolith those capabilities are already bridged in)                                                          |

Within one call the capability name `<name>` is identical everywhere; only the wrapper differs:
HTTP `POST /api/<domain>/capabilities/<name>`; agent tool name `<domain>__<name>`;
each service's own MCP server exposes the tool under the bare `<name>` (the domain is disambiguated by the server itself).

---

## Purpose

Pure dataclasses/enums shared by every layer: Event, DomainEvent, RuntimeEvent, ActorRef/Kind, ServiceError/ErrorSuffix, usage types. Zero logic.

## Configuration

None.

## Extension Points

Add new contract types here when a change is genuinely cross-layer; consumers must never re-declare shapes.

## Known Limitations

Types are frozen surfaces: renaming or reshaping any field is a breaking protocol change (version.py gates it).

## Deferred Work

More structured error hints.
