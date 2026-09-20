# runtime-data — 运行时数据（“它的大脑”）

> 语言：简体中文 | [English](README.md)

与工作区（“它的家”）分离。内容为用户数据，**不提交进仓库**。

| 内容 | 用途 |
|---|---|
| events.db | 事件日志（事件流的持久化） |
| audit.db | 审计 |
| memory/ | agent 记忆存储（四种记忆类型） |
| checkpoints/ | 任务检查点 |
| logs/ | 结构化日志 |
| secrets/ | 本机密钥（machine.token 等；platform/actor、platform/secrets） |
