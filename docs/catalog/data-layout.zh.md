# 数据布局

[English](data-layout.md) | 中文

全部运行时状态位于 `data/` 下。以下布局是代码实际创建的;`data/runtime/README.md` 记载了其中一部分。组合进程中一切都在这里;独立域运行默认使用 `packages/<domain>/data/`。

## 共享存储(`packages/host/src/host/assemble.py`)

| 路径 | 归属 | 内容 | 保留 |
|---|---|---|---|
| `data/runtime/events.db` | `platform_eventbus.EventLog` | 只追加事件日志 | `agent.delta` 行 24 小时后清理;其他类型持续累积 |
| `data/runtime/settings.db` | `platform_settings.SettingsStore` | 设置值 | — |
| `data/runtime/secrets.db` | `platform_secrets.SecretStore` | Fernet 加密密钥 | — |
| `data/runtime/audit.db` | `platform_capability.SqliteAuditSink` | 能力调用审计 | — |
| `data/runtime/machine.token` | `platform_actor.LocalTokenIssuer` | 本地 bearer token | — |

## Agent 存储(`agent/src/agent/`,位于 `data/runtime/agent/`)

| 路径 | 归属 | 内容 | 保留 |
|---|---|---|---|
| `sessions.db` | `memory/session_store.py SessionStore` | 聊天会话、活动指针 | — |
| `trajectory.db` | `runtime/trajectory.py TrajectoryStore` | `steps`/`runs` 投影、`raw_rounds` | 原始轮 7 天后清理 |
| `session_index.db` | `runtime/session_index.py SessionIndex` | 聊天消息的 FTS5 索引 | — |
| `queue.db` | `runtime/queue_store.py QueueStore` | 持久队列(cron) | — |
| `meter.db` | `runtime/meter_store.py MeterStore` | LLM/工具用量 | 90 天 |
| `memory/profile.db`、`memory/episodic.db`、`memory/semantic.db` | `memory/` 各库 | 画像、情景轨迹、事实 | `agent.memory.retention_days`(purge 调用) |
| `checkpoints/` | `runtime/state.py CheckpointStore` | 恢复快照 | 启动清扫 |
| `subagents/*.json` | `subagent/registry.py SubagentRegistry` | 用户自定义子代理定义 | — |
| `write_journal/` | 写日志 | 内容寻址的写入备份 | — |

## 域存储(`data/runtime/<domain>/`)

| 路径 | 归属 | 内容 |
|---|---|---|
| `data/runtime/llm/llm.db` | `packages/llm` `ProviderStore` | 供应商、用量 |
| `data/runtime/notes/notes.db` | `packages/notes` `NoteStore` | 笔记、版本、链接、标签、回收站 |
| `data/runtime/notes/assets.db` | `packages/notes` `AssetStore` | 附件元数据(二进制在工作区) |
| `data/runtime/graph/graph.db` | `packages/graph` `GraphStore` | 节点、边 |
| `data/runtime/graph/index.db` | `packages/graph` `IndexQueue` | 索引任务 |
| `data/runtime/graph/engine-python/` | `packages/graph` Python 引擎 | 引擎数据根 |
| `data/runtime/sources/repo.db`、`doc.db`、`web.db` | `packages/sources` | 各类来源记录 |
| `data/runtime/office/office.db` | `packages/office` `DocumentStore` | 文档(`doc`/`slides`) |
| `data/runtime/browser/browser.db` | `packages/browser` `BrowserStore` | 会话元数据 |
| `data/runtime/code_exec/code-exec.db` | `packages/code_exec` `ExecutionStore` | 执行记录 |

## 工作区与引擎缓存

| 路径 | 用途 |
|---|---|
| `data/workspace/` | 工作工作区(可经 `agent.workspace.dir` 切换,必须位于仓库根内);含 `skills/`、`hooks/`、`spill/`、`sandbox/`、`imports/`、`repo/` 克隆 |
| `data/graph-db/` | Python graph 引擎的图谱文件(`engines/python/engine.py`) |
| `data/graph-engine-cache/` | C 引擎 sidecar 缓存(`ENGINE_CACHE_DIR`) |
