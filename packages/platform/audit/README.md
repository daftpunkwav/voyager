# platform/audit — Audit (skeleton)

Every mutation-type capability call lands in the audit trail: actor / capability / input summary / result / ts / trace_id (§7.6).

The capability framework already defines the `AuditSink` protocol and `AuditEntry` (with input redaction, see
platform/capability/guards.py). **The storage implementation currently lives in the capability package**:
`platform_capability.audit_db.SqliteAuditSink` (data/runtime/audit.db),
wired into the guard chain by the composition root (host.assemble); it will move into this package when that migration is implemented.

The query interface `SqliteAuditSink.recent()` (filter by capability/trace/outcome) is in place,
**but production currently only writes, never reads** — the activity page (§10.8) reads the event stream for now; audit lookups are reserved for debugging and for a future "operation trail" view on the activity page.
