# Agent 子代理与编排

[English](agent-subagents.md) | 中文

引擎如何派生、约束与协调子代理运行。

源码:`agent/src/agent/subagent/` 加 `master/` 编排模块。

## 实例与任务书

`instance.py` — `SubagentInstance` 是一次运行的状态机:`task: TaskBook`、工具带、LLM、`state: RunState`、历史、`UsageTracker`、人格、`parent_run_id`(取消级联)、期限、预算、`prefix_watch`。`TaskBook`(frozen dataclass)声明一次运行:`goal`、`constraints`、`done_when`、`mode`、`allowed_tools`(None = 不裁剪,`()` = 无工具)、`readonly`、`limits`、`conversational`、`session`、`depends_on`。状态机(`SubStatus`):`created → running → waiting_input → completed/failed/cancelled`。

## 派生

`spawn.py` — `Spawner`:

- `spawn(task, persona, name, ...)` 构建收窄的工具带:`trimmed(allowed_tools)`,`readonly` 时再加 `trimmed_read_only()`。
- `start(inst, user_text)` 在 `Scheduler` 并发上限(`agent.subagents.max_concurrent`)下运行 turn,并在 `finally` 中持久化 turn 边界检查点。
- `resume_from_checkpoint(run_id)` — 仅任务型 REACT。
- `cancel(id_or_name)` 经 `parent_run_id` 级联到 running 与 pending 后代。
- 终态实例超过 `TERMINAL_INSTANCE_CAP = 32` 后淘汰最旧者。

`registry.py` — `SubagentRegistry`/`SubagentDef`:用户自定义子代理,持久化为 `data/runtime/subagents/*.json`(名称须匹配 `^[a-z][a-z0-9_]*$`;字段覆盖模式、人格、允许工具、限额、网络模式、readonly、enabled)。

`surface.py` — `intersect_surface` 强制分配时收窄:派发永远不会授予比派发者本身更宽的工具面。

`triggered_spawn.py` — 事件模式触发的派生,冷却 `agent.triggers.cooldown_s`。

## 模式

`modes/registry.py` 在七种模式间分发 `run_mode()`,一模式一文件:`react`、`plan_execute`、`cot`、`tot`、`got`、`reflexion`、`direct`。orchestrator 人格被强制 ReAct(`master/dispatch.py`)。对子代理的 `wait` 是 `subagent` 能力的 `wait` 动作:0.5 秒轮询,默认超时 120 秒,上限 600 秒。

## 编排(`master/`)

- **任务图**(`task_graph.py`)— 派发的父子树,深度上限(`agent.subagents.max_depth`,默认 3);`depends_on` 未满足时派发保持为 `DeferredDispatch`;`finish_task` 汇入图。不是通用 DAG 引擎。
- **派发**(`dispatch.py`)— 人格解析(内置 → 用户 registry 回退)、工具面交集、网络收窄(`narrow_network`)、后台运行、完成通知合成(`synthesize.py`)、`on_subagent_start`/`on_subagent_end` 钩子。
- **黑板**(`blackboard.py`)— 任务范围共享笔记;实例之间从不直接对话。
- **摘要**(`digest.py`)— `DigestStore` 保存每个子代理的状态卡;orchestrator 只见摘要,不见原始上下文。
- **仲裁**(`arbiter.py`)— turn 运行中对新用户输入做合并/排队/延后(`agent.arbiter.mode`)。
- **Goal**(`goal.py`、`goal_driver.py`)— 每会话一个持久 goal,存于会话存储 meta;驱动器经持久队列调度带预约门槛的续跑轮;启动时绝不自动复活已暂停的 goal。
- **主动联络**(`proactive.py`、`outreach_budget.py`)— `user.online` 时问候,以及来自持久队列的一条跟进链,受 `agent.outreach.*` 预算封顶。
- **任务通知**(`job_notify.py`)— 调度器完成产生安静通知或受预算门控的唤醒 turn。
