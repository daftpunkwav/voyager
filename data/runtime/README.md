# runtime-data — 运行期数据("它的脑",§5)

与 workspace("它的家")分离。内容为用户数据,**不入库**。

| 内容 | 用途 |
|---|---|
| events.db | 事件日志(事件流的持久化,§7.2) |
| audit.db | 审计(§7.6) |
| memory/ | agent 记忆库(四类记忆,§9.11) |
| checkpoints/ | 任务断点(§9.17) |
| logs/ | 结构化日志(§7.8) |
| secrets/ | 本机密钥(machine.token 等,platform/actor、platform/secrets) |
