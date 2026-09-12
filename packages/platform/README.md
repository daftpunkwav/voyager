# platform — Cross-cutting infrastructure

The only layer that all modules are allowed to depend on: **mechanisms only, no business logic, no domain vocabulary or brand names**
(docs-local/design/architecture.md §7). It defines "how to speak", never "what to say".

| Subpackage    | Responsibility                                                                                   | Status         |
| ------------- | ------------------------------------------------------------------------------------------------ | -------------- |
| contracts     | Events / DTOs / error codes / protocol version (pure types, zero dependencies)                   | ✅ implemented |
| actor         | Local machine tokens, call context (authentication, §7.4)                                        | ✅ implemented |
| eventbus      | Durable event log + pub/sub + cursors (§7.2)                                                     | ✅ implemented |
| capability    | Define once → REST + MCP dual generation, entry guards (§7.3); includes the audit store audit_db | ✅ implemented |
| settings      | Settings framework: schema/secret/change events (§7.9)                                           | ✅ implemented |
| health        | Health probing and unified error construction (§7.10)                                            | ✅ implemented |
| secrets       | Secret keeping: encrypted at rest, on-demand delivery, redaction (§7.7)                          | ✅ implemented |
| limit         | Rate limiting and quotas (§7.5; CostQuota currently built into capability guards)                | skeleton       |
| audit         | Audit query/visualization (storage currently lives in capability/audit_db, see its README)       | skeleton       |
| observability | Structured logging, traces, metrics (§7.8)                                                       | skeleton       |
| config        | Configuration loading convention: defaults < config file < environment variables (§7.7)          | skeleton       |

Import convention: a directory is the boundary of responsibility; the import name is `platform_<dir>` (to avoid clashing with the
standard-library `platform` / `secrets` etc.). The seven implemented subpackages each have their own pyproject and
independent tests; the four subdirectories marked "skeleton" are documentation placeholders with no code yet.
