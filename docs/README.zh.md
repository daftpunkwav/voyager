# Voyager 文档

[English](README.md) | 中文

Voyager 是一个本地优先的 agent 伴侣工作台:Python 后端(FastAPI + SQLite,`packages/` + `agent/`)与 React 前端(`apps/web`)组合为单进程。本树按代码现状编写文档。从这里开始,改动组合或接线前先读 [architecture.zh.md](architecture.zh.md),再前往下表所属页面。

## 总览

| 文档 | 内容 |
|---|---|
| [architecture.zh.md](architecture.zh.md) | 源码根、分层、组合(host → gateway)、agent 引擎、事件流、依赖规则 |
| [development.zh.md](development.zh.md) | 工具链(uv / npm)、启动、门禁脚本、仓库布局 |
| [testing.zh.md](testing.zh.md) | 测试布局、门禁、agent eval 基线、依赖图检查 |

## 子系统(`subsystems/`)

索引:[subsystems/README.zh.md](subsystems/README.zh.md)。

| 页面 | 职责 |
|---|---|
| [platform.zh.md](subsystems/platform.zh.md) | 八个 `platform_*` 框架包:contracts、actor、eventbus、capability、settings、secrets、health、webguard |
| [capability-framework.zh.md](subsystems/capability-framework.zh.md) | `Capability`/`Registry`、REST 与 MCP 生成、守卫链、`Wiring`、审计 |
| [eventbus.zh.md](subsystems/eventbus.zh.md) | 事件词表(`DomainEvent`/`RuntimeEvent`)、`EventLog`、`EventBus`、游标、保留策略 |
| [host.zh.md](subsystems/host.zh.md) | 组合根:卡片扫描、规划、共享设施、域工具桥、跨域调用、LLM 路由 |
| [gateway.zh.md](subsystems/gateway.zh.md) | HTTP 载体:认证、错误包络、挂载、chat/SSE/session/workspace/uploads 路由、限流 |
| [llm.zh.md](subsystems/llm.zh.md) | `llm` 域:供应商、wire 格式、用量计量、定价、嵌入 |
| [notes.zh.md](subsystems/notes.zh.md) | `notes` 域:笔记、版本、链接、标签、附件、回收站 |
| [graph.zh.md](subsystems/graph.zh.md) | `graph` 域:知识图谱存储、索引队列、调度器、C/Python 引擎、L0 关系 |
| [sources.zh.md](subsystems/sources.zh.md) | `sources` 域:repo/doc/web 来源、worker、抽取、SSRF 防护的 URL 抓取 |
| [auxiliary-domains.zh.md](subsystems/auxiliary-domains.zh.md) | `settings`、`browser`、`code_exec`、`office` 域 |
| [agent-loop.zh.md](subsystems/agent-loop.zh.md) | agent 引擎:组装(`AgentApp`)、事件循环、turn 驱动、ReAct 轮、终止、仲裁 |
| [agent-tools.zh.md](subsystems/agent-tools.zh.md) | 工具面:`Toolbelt`、权限、调用管线、域工具桥、人机 parity |
| [agent-context.zh.md](subsystems/agent-context.zh.md) | 上下文工程:提示组装、预算、prune/compact 治理、前缀缓存监视 |
| [agent-subagents.zh.md](subsystems/agent-subagents.zh.md) | 子代理:实例、任务书、派生、模式、编排(任务图、goal、主动联络) |
| [agent-memory.zh.md](subsystems/agent-memory.zh.md) | 记忆库、蒸馏、会话、技能、人格 |
| [agent-runtime.zh.md](subsystems/agent-runtime.zh.md) | agent 运行时机构:轨迹、会话索引、队列、调度器、计量、期限、检查点、追踪 |

## 目录(`catalog/`)

| 文档 | 内容 |
|---|---|
| [tool-catalog.zh.md](catalog/tool-catalog.zh.md) | agent 工具面:内置工具、能力聚合工具、MCP 命名、激活 |
| [config-catalog.zh.md](catalog/config-catalog.zh.md) | 按属主分组的注册设置键,含类型与声明模块 |
| [data-layout.zh.md](catalog/data-layout.zh.md) | `data/` 下的运行时数据布局:每个存储、归属模块与保留策略 |

## 前端(`web/`)

| 文档 | 内容 |
|---|---|
| [frontend.zh.md](web/frontend.zh.md) | `apps/web`:技术栈、路由、能力桥、SSE 流、状态 store、i18n、构建 |

## 流程

| 文档 | 内容 |
|---|---|
| [AGENTS.zh.md](AGENTS.zh.md) | 文档规范:放置、双语配对、写作规则 |
| [i18n/README.zh.md](i18n/README.zh.md) | 双语配对契约与一致性记录 |
