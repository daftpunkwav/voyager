# platform — Cross-cutting infrastructure

The only layer that all modules are allowed to depend on: **mechanisms only, no business logic, no domain vocabulary or brand names**. It defines "how to speak", never "what to say".

| Subpackage    | Responsibility                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------ |
| contracts     | Events / DTOs / error codes / protocol version (pure types, zero dependencies)                   |
| actor         | Local machine tokens, call context (authentication)                                              |
| eventbus      | Durable event log + pub/sub + cursors                                                            |
| capability    | Define once → REST + MCP dual generation, entry guards; includes the audit store audit_db        |
| settings      | Settings framework: schema/secret/change events                                                  |
| health        | Health probing and unified error construction                                                    |
| secrets       | Secret keeping: encrypted at rest, on-demand delivery, redaction                                 |
| limit         | Rate limiting and quotas (CostQuota lives in the capability guards)                              |
| audit         | Audit query/visualization (storage lives in capability/audit_db, see its README)                 |
| observability | Structured logging, traces, metrics                                                              |
| config        | Configuration loading convention: defaults < config file < environment variables                 |

Import convention: a directory is the boundary of responsibility; the import name is `platform_<dir>` (to avoid clashing with the
standard-library `platform` / `secrets` etc.). The subpackages contracts, actor, eventbus, capability, settings, health, and
secrets each have their own pyproject and independent tests; the limit, audit, observability, and config directories are
documentation placeholders with no code yet, and each carries its own README.

Working conventions for this tree: [AGENTS.md](../AGENTS.md).
