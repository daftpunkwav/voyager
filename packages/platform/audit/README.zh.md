# platform/audit — 审计（骨架）

> 语言：简体中文 | [English](README.md)

每次变更类能力调用都会落入审计轨迹：actor / capability / 输入摘要 / result / ts / trace_id。

capability 框架已定义 `AuditSink` 协议与 `AuditEntry`（含输入脱敏，见
platform/capability/guards.py）。**存储实现目前位于 capability 包内**：
`platform_capability.audit_db.SqliteAuditSink`（data/runtime/audit.db），
由装配根（host.assemble）接入守卫链。

查询接口 `SqliteAuditSink.recent()`（按 capability/trace/outcome 过滤）已就位，
**但目前生产路径只写不读**——活动页读取事件流；审计查询仅服务于调试。
