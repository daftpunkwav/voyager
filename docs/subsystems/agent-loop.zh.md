# Agent 主循环

[English](agent-loop.md) | 中文

agent 引擎是事件驱动的:它不拥有请求处理器。总线事件启动工作,asyncio 任务驱动 turn,持久存储记录一切。源码根:`agent/src/agent/`(包 `agent`)。

## 组装

`build.py` — `build_agent(*, data_dir="data/runtime", workspace_dir=None, llm=None, ...) -> AgentApp` 是唯一组合根。它构造事件日志与总线、设置、记忆、策略引擎、计量器、工具带、MCP 池、插件管理器、调度器、队列、检查点、轨迹、会话索引、master、goal 管理器/驱动器与事件循环,然后互相绑定。组装件挂在 `AgentApp` 上(`app.py`):`bus`、`log`、`settings`、`memory`、`master`、`loop`、`skills`、`hooks`、`asker`、`spawner`、`registry`、`mcp`、`meter`、`plugins`、`session_store`、`trajectory`、`queue_store`、`scheduler`、`checkpoints`、`write_journal`、`session_index`、`dispatcher`。`app.close()` 释放它们;`drain()` 等待后台 turn。

未注入 LLM 时(未配置的独立运行),`build_agent` 降级为 `FakeLLM` 并告警。

进程入口:`main.py` — `python -m agent.main` 调用 `build_agent()` 后 `await app.loop.run()`。`repl.py` 提供独立的终端客户端。

## 事件接线

`runtime/wire.py` — `bind_event_loop(...)` 把总线模式映射到处理器:`user.message` → `Master.handle_user_message`,`agent.step` → `trajectory.catch_up`,`user.online` → 主动问候,另加子代理触发模式。`runtime/loop.py` — `EventLoop` 先按存储游标排空日志中的待处理行,再订阅分发,每个模式配一个 `CircuitBreaker`;`"*"` 模式被拒绝。

## Turn 驱动

`master/master.py` — `Master.handle_user_message(text, trace_id, session_id)`:

1. 触发 `on_user_message` 钩子;追加到工作记忆;视条件运行 `Distiller.maybe_distill()`。
2. 直聊模式(`agent.direct_chat`):一次补全直接作答。
3. 否则解析或创建聊天会话(`SessionManager`);若实例已在 RUNNING,应用 `Arbiter`(按 `agent.arbiter.mode` 合并 / 排队 / 入队通知;auto 与 guide 模式用一次短 LLM 判断,失败回退排队)。
4. `_start_turn` 在会话锁(`sessions.lock_for`)下把 `Master._turn` 放入 asyncio 任务,随后排空会话收件箱,再 `goal_driver.maybe_schedule(session)`。

行首的 `@名字`(`_parse_mention`)把消息路由给该常驻成员作为成员 turn(`run_turn(member=...)` —— 该人格自己的 system 层、工具面与默认模式,共享同一时间线);turn 运行中时 @消息排入同一收件箱。收件箱条目携带说话人(`_Queued.member`),排空时成员 turn 把发言权交给被点名的成员。团队完成经 `Master.announce_delivery` → 结构化 `agent.delivery` 事件加一个转述汇报的唤醒 turn(受 `WakeBudget` 门控);任务板认领以同样方式唤醒发布者。

`Master._turn` 重新应用设置中的限额,设置实例期限,然后 `Spawner.start(inst, text)` → `SubagentInstance.run_turn`(`subagent/turn.py`)→ `run_mode(Mode.REACT, ...)` → `modes/react.py:run_react`。

## ReAct 轮

`run_react` 的每一轮:

1. `governor.enforce` — 确定性 prune,仍超阈值则 LLM 压缩。
2. `complete_streaming(llm, messages, specs, ...)` — 一次模型请求;记录用量与原始请求/响应(`on_step`、`on_raw`)。
3. 若回复携带最终文本,返回。无工具的非寒暄回答可能触发一轮 `continue_if_idle` 催促。
4. 否则追加 assistant `tool_calls` 条目,把调用划分为可并行的批次与串行单例,经 `Toolbelt.call_detailed` 执行,追加 `role:"tool"` 结果,并记录 `on_step("tool", ...)`。

默认值:`ModeLimits(max_rounds=20, max_tool_calls=40, max_tokens=0)`(`subagent/modes/base.py`)。

## 终止

turn 在以下情况结束:模型返回最终文本;触及 token 上限(`[预算]`);触及工具调用上限(`[中断]`);`LoopDetector` 在一轮 `LoopAdvisory` 催促后触发;触及 ReAct 轮数上限;或期限到期。上下文溢出触发一次激进压缩、`_emergency_truncate` 与重试。

`subagent/turn.py:run_turn` 随后写回压缩历史摘要(`[历史压缩]` 标记),追加 assistant 回复,置终态 — 会话型实例为 `WAITING_INPUT`,任务为 `COMPLETED` — 并发出 `AGENT_COMPLETED`。错误路径置 `FAILED`/`CANCELLED`;`PauseRequested` 置 `PAUSED` 并落轮中检查点。

## 流式

REACT 与直聊轮流式:`subagent/modes/streaming.py` 合并增量(`DELTA_FLUSH_INTERVAL = 0.12` 秒,取消锚 `"\n\n…[已中断]"`)。只有会话型实例发出 `agent.delta` 事件;其余模式保持非流式。
