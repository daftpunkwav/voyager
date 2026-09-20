# platform/audit — Audit (skeleton)

Every mutation-type capability call lands in the audit trail: actor / capability / input summary / result / ts / trace_id.

The capability framework already defines the `AuditSink` protocol and `AuditEntry` (with input redaction, see
platform/capability/guards.py). **The storage implementation currently lives in the capability package**:
`platform_capability.audit_db.SqliteAuditSink` (data/runtime/audit.db),
wired into the guard chain by the composition root (host.assemble).

The query interface `SqliteAuditSink.recent()` (filter by capability/trace/outcome) is in place,
**but production currently only writes, never reads** — the activity page reads the event stream; audit lookups serve debugging.
