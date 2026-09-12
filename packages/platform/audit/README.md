# platform/audit — 审计(骨架)

一切变更类 capability 调用落审计:actor / capability / 输入摘要 / 结果 / ts / trace_id(§7.6)。

capability 框架已定义 `AuditSink` 协议与 `AuditEntry`(含入参脱敏,见
platform/capability/guards.py)。**落库实现暂居 capability 包**:
`platform_capability.audit_db.SqliteAuditSink`(data/runtime/audit.db),
由装配根(host.assemble)接入守卫链;待实现迁移时移入本包。

查询接口 `SqliteAuditSink.recent()`(按能力/trace/成败过滤)已就绪,
**当前生产只写不读**——活动页(§10.8)暂读事件流,审计回查为调试与
后续活动页"操作留痕"视图预留。
