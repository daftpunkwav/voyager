# Agent 运行时机构

[English](agent-runtime.md) | 中文

`agent/src/agent/runtime/` 下的常驻机构,外加钩子与插件。

## 轨迹

`trajectory.py` — `TrajectoryStore`(`data/runtime/agent/trajectory.db`)是事件日志之上的可重建查询投影。`catch_up()`(单写者,按 `seq` 幂等 `INSERT OR IGNORE`)把 `agent.step` 与运行生命周期事件折叠进 `steps` 与 `runs` 表,游标存于 `meta`。`raw_rounds` 表(`PRIMARY KEY (run_id, round)`)按轮存完整请求/响应 JSON,另有 `wire_request`(出站 wire 请求体原文)与 `seq_round`(会话级连续显示轮号,按 `ts` 排序在单事务内回填;读取按它排序),仅会话型实例经 `master.sessions.set_raw_fn` 写入。原始行按 `RAW_LOG_RETENTION_DAYS = 7` 天清理。每条 `agent.step` 事件在循环线程内联催促 `catch_up()`(`runtime/wire.py`)。gateway 的 `GET /api/chat/trajectory` 与 `GET /api/chat/rawllm` 读取该存储。

## 会话索引

`session_index.py` — `SessionIndex`(`data/runtime/agent/session_index.db`):对 `user.message`/`agent.message` 的 SQLite FTS5 检索投影,带 CJK 分词。

## 持久队列与调度器

`queue_store.py` — `QueueStore`(`data/runtime/agent/queue.db`):支持 cron 的持久队列,至少一次投递,启动时崩溃恢复(`recover()`)。`scheduler.py` — `Scheduler`:子代理运行的并发上限、定时器与持久任务轮询循环(`app.start_queue_loop`)。`orchestrator/wake_budget.py` 约束排队工作唤醒 agent 的频率。

## 计量与配额

`meter.py` / `meter_store.py` / `pricing.py` — `Meter` 背靠 `MeterStore`(`meter.db`),90 天清理;每次 LLM 调用与工具调用都记录用量。`runtime/llm_quota.py` — `metered_llm(client, meter, quota_fn)` 包住每个真实 LLM 客户端,热读每日 token 预算 `agent.resource.daily_tokens`。`agent.pricing.overrides` 供成本换算。

## 期限、重试、熔断

`deadline.py` — `Deadline.from_settings` 应用墙钟上限 `agent.execution.tool_deadline_s` / `round_deadline_s`。`recovery.py` — `with_retry` 与 `CircuitBreaker`(每工具、每事件模式各一)。

## 检查点与恢复

`state.py` — `RunState`、`Step`、`ResumeSnapshot` 与 `CheckpointStore`(`data/runtime/agent/checkpoints/`),原子保存加启动清扫;`build.py` 在启动时清理临时文件并准备可恢复检查点。`Spawner.resume_from_checkpoint` 重放任务型 REACT 运行;暂停会在轮中持久化 `pending_messages`。

## 追踪与可观测

`trace.py` — trace `ContextVar` 加有界 span 缓冲(`start_span`)。`exporters.py` — `TraceDispatcher` 按 `agent.observability.exporter` 选择 OTLP 和/或 Langfuse 导出器。`orchestrator/evaluation.py` — `TaskEvaluator` 以启发式或评判模型为 turn 打分(`agent.evaluation.*`)。`jobs_view.py` — `JobsView`,支撑 jobs API 的只读 `task.*` 投影。`current.py` — `current_instance` 上下文变量。

## 写日志

`build.py` 接线 `WriteJournal`(`data/runtime/agent/write_journal/`):内容寻址的文件写入备份,支撑撤销。

## 钩子

`hooks/triggers.py` — `HookRegistry` 固定挂点:`on_event`、`pre_tool`(返回 `False` 拦截)、`post_tool`、`on_subagent_start`、`on_subagent_end`、`on_user_message`。`hooks/loader.py` — `HookLoader.load_dir` 加载 `workspace/hooks`;`hooks/reload.py` — `UserHookReloader` 热加载/卸载钩子文件,并把声明式 `on_event` 模式同步进 `EventLoop`。

## 插件

`agent/src/agent/plugins/manager.py` — `PluginManager` 发现 `<plugins_root>/<name>/plugin.json` 清单。加载仅限持久化的批准列表(`agent.plugins.approved`、`agent.plugins.approvals`);管理器以声明方式套用插件的 skills、hooks 与 MCP 条目,从不 import 或执行插件代码。`agent/src/agent/plugins/install.py` — zip/目录安装,经清单、路径牢笼、zip-slip、符号链接与尺寸校验;安装后的插件绝不预批准;卸载只移除未批准插件。
