# 事件总线

[English](eventbus.md) | 中文

事件总线是集成主干:域之间不互相 import,只发布与订阅。`platform_eventbus` 提供只追加日志、进程内扇出与游标存储。

源码:`packages/platform/eventbus/src/platform_eventbus/`

## 事件词表

`platform_contracts/events.py` 声明两族,由 agent 扩展:

- **`DomainEvent`** — 总线上的跨域事实。固定名称包括:`user.message`、`user.online`、`user.activity`、`task.enqueued`/`task.progress`/`task.completed`/`task.failed`、`agent.message`、`agent.ask`、`agent.step`、`agent.delta`、`agent.observe`、`agent.policy.notify`、`agent.navigate`、`skill.proposed`、`settings.changed`、`service.health.changed`。各域补充自己的事件(`note.created`…`note.purged`、`notes.ui.changed`、`doc.created`、`doc.edited`、`source.added`/`source.removed`/`source.ready`、`graph.engine.fallback`)。
- **`RuntimeEvent`** — agent 运行生命周期(`RunStarted`、`LLMStarted`、`LLMStreaming`、`LLMCompleted`、`ToolStarted`、`ToolCompleted`、`ToolFailed`、`AgentPaused`、`AgentResumed`、`AgentCompleted`、`AgentCancelled`、`RunFailed`、`RunCancelled`);`agent/src/agent/runtime/events.py` 扩展 `ToolProgress` 与 `ThinkingStarted`/`ThinkingDelta`/`ThinkingCompleted`。

每条事件携带 `seq`(日志位置)、`type`、`ts`、`trace_id` 与载荷。

## EventLog

`EventLog` 把每条事件追加到以自增 `seq` 为键的 SQLite `events` 表,并提供分页读取(`before_seq`/`after_seq`)与追赶扫描。这份日志 — 而非内存 — 是事实源:聊天历史、轨迹重建、SSE 重放都从它读取。`Retention` 按类型与年龄清扫旧行;host 只为 `agent.delta` 配置保留(24 小时),其余事件类型持续累积直至手动清理。

## EventBus

`EventBus` 把每条已提交事件按 glob 式模式(支持 `*`)投递给进程内异步订阅者。落后过多的订阅者被标记为 `lagged` 而不是被静默丢弃;它按存储位置从日志重放以恢复。gateway 的 SSE 端点(`GET /api/chat/stream`)是远程消费者:转发实时扇出,并在客户端携带 `after_seq` 重连时从日志重放缺失行。

## CursorStore

`CursorStore` 持久化每个订阅者的位置,让 `EventLoop`(agent 的分发器)从停下的地方继续,而不是启动时重放全量日志。

## 生产者与消费者

| 生产者 | 事件 | 主要消费者 |
|---|---|---|
| gateway `POST /api/chat/messages` | `user.message` | agent `EventLoop` → `Master.handle_user_message`;聊天历史 API |
| gateway `POST /api/activity` | `user.activity` | 活动 feed API |
| agent ReAct 轮循环 | `agent.step`、`agent.delta`、`agent.message` | 轨迹投影、SSE → 前端轨迹与气泡 |
| agent 策略 | `agent.policy.notify` | 前端通知 |
| 域 worker(notes/sources/graph/code_exec) | `task.progress`/`task.completed`/`task.failed` | SSE → 前端任务进度 |
| `SettingsStore` | `settings.changed` | 依赖设置的热读取方 |
| 域 wiring | 生命周期事实(`note.created`、`source.ready` 等) | 前端 feed;钩子(`on_event`) |
