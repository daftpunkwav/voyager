# 子系统

[English](README.md) | 中文

每个后端子系统或域一页:定义、类型、端点、存储与事件。这些页面与 [architecture.zh.md](../architecture.zh.md) 互补,后者描述跨子系统的分层、组合与事件流。

| 页面 | 职责 |
|---|---|
| [platform.zh.md](platform.zh.md) | 八个 `platform_*` 框架包:contracts、actor、eventbus、capability、settings、secrets、health、webguard |
| [capability-framework.zh.md](capability-framework.zh.md) | `Capability`/`Registry`、`@capability` 装饰器、REST/MCP 生成、守卫链、`Wiring`、审计 |
| [eventbus.zh.md](eventbus.zh.md) | 事件词表(`DomainEvent`/`RuntimeEvent`)、`EventLog`、`EventBus`、游标、保留策略 |
| [host.zh.md](host.zh.md) | 组合根:扫描、规划、共享设施、wiring 注入、域工具桥、跨域调用、LLM 路由、工作区切换 |
| [gateway.zh.md](gateway.zh.md) | HTTP 载体:`create_app`、安全头、actor 认证、错误包络、挂载、chat/SSE/session/activity/workspace/uploads 路由、限流、健康 |
| [llm.zh.md](llm.zh.md) | `llm` 域:供应商管理、wire 格式(`chat`/`anthropic`/`responses`)、用量计量、定价、嵌入 |
| [notes.zh.md](notes.zh.md) | `notes` 域:笔记、版本历史、wiki 链接与反链、标签、附件、保存视图、回收站 |
| [graph.zh.md](graph.zh.md) | `graph` 域:规范图谱存储、索引队列与调度器、C/Python 引擎、code 与 L0 管线 |
| [sources.zh.md](sources.zh.md) | `sources` 域:repo/doc/web 三类来源、后台 worker、文档抽取、SSRF 防护的 URL 抓取 |
| [auxiliary-domains.zh.md](auxiliary-domains.zh.md) | `settings`、`browser`、`code_exec`、`office` 域 |
| [agent-loop.zh.md](agent-loop.zh.md) | agent 引擎:`AgentApp`、事件循环、turn 驱动、ReAct 轮、终止路径、仲裁 |
| [agent-tools.zh.md](agent-tools.zh.md) | agent 工具面:`AgentTool`/`Toolbelt`、权限与策略、调用管线、结果外溢、域工具桥、parity |
| [agent-context.zh.md](agent-context.zh.md) | 上下文工程:提示组装分层、预算、上下文治理器(prune/compact)、前缀缓存监视、页面上下文 |
| [agent-subagents.zh.md](agent-subagents.zh.md) | 子代理:`SubagentInstance`、任务书、`Spawner`、registry、模式、编排(任务图、黑板、goal、主动联络) |
| [agent-memory.zh.md](agent-memory.zh.md) | 记忆:profile/episodic/semantic/working 四库、召回、蒸馏、聊天会话、技能、人格 |
| [agent-runtime.zh.md](agent-runtime.zh.md) | agent 运行时机构:轨迹、会话索引、持久队列、调度器、计量与配额、期限、重试与熔断、检查点、追踪、钩子、插件 |
