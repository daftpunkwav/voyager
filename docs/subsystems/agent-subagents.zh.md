# Agent 子代理与编排

[English](agent-subagents.md) | 中文

引擎如何派生、约束与协调子代理运行。

源码:`agent/src/agent/engine/` 加 `orchestrator/` 编排模块。

## 实例与任务书

`instance.py` — `SubagentInstance` 是一次运行的状态机:`task: TaskBook`、工具带、LLM、`state: RunState`、历史、`UsageTracker`、人格、`parent_run_id`(取消级联)、期限、预算、`prefix_watch`。`TaskBook`(frozen dataclass)声明一次运行:`goal`、`constraints`、`done_when`、`mode`、`allowed_tools`(None = 不裁剪,`()` = 无工具)、`readonly`、`limits`、`conversational`、`session`、`depends_on`、`board_task_id`(团队任务板行回链)。状态机(`runtime/state.py:RunStatus`):`pending → running → waiting_input/paused → completed/failed/cancelled`。

## 常驻团队(群聊)

一个会话就是常驻团队的群聊:五个内置人格(`personas/TEAM_KEYS` —— orchestrator/Lucien、recon/Iris、explainer/Elio、organizer/Miyai、graph_guide/Atlas)。成员共享会话时间线;每条 agent 回复都带 `speaker`(人格键,持久化在历史条目与 `agent.message` payload 上;缺省 = 常驻主持 Lucien,旧消息同样如此读回)。

- **成员 turn** — `engine/turn.py:run_turn(inst, text, member=人格键)` 以该人格运行 turn(经 `build_system` 注入其 system 层、工具面 `trimmed(tool_allow)`、其 `default_mode` —— explainer 在会话内跑 cot),共享同一份时间线;请求构建时把其他成员的历史发言渲染为 `【名字】` 前缀,并合并连续 assistant 条目(部分 provider 拒收相邻 assistant 轮次)。成员标签走 `inst._member_label`,step/delta 事件归属到「Elio」而非会话实例的通用名。
- **发言权路由** — `orchestrator/master.py:_parse_mention` 把行首 `@名字`(显示名与别名)直接路由给该成员;`subagent(action=handoff, persona, message)` 经会话 inbox 排队成员 turn(当前 turn 结束后 drain,同一把会话锁——一次只有一人说话)。
- **任务板** — `orchestrator/task_board.py:TaskBoard` 是发布/认领/确认状态机(`open → claimed → assigned → running → done/failed`,内存态,与被派实例同生命周期)。`taskboard` 能力(与同名工具)向人与 agent 同权暴露 `publish/claim/confirm/list`:Lucien 与用户敲定方案后发布,成员带商议留言认领,发布者 confirm 后由能力层转后台派单(`TaskBook.board_task_id` 关联行)。认领会唤醒发布者(`Master.notify_task_claim`)去拍板或回应商议。
- **交付** — 板上运行的完成走 `Master.announce_delivery`:盖章板行、发结构化 `agent.delivery` 事件(完整内容/状态/耗时/`run_id`,前端渲染为交付卡),并经唤醒 turn(`handle_notice`,受 `WakeBudget` 门控——超限降级为静默收据;认领始终唤醒)让主持向用户转述摘要。

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

`modes/registry.py` 在七种模式间分发 `run_mode()`,一模式一文件:`react`、`plan_execute`、`cot`、`tot`、`got`、`reflexion`、`direct`。派单走人格的 `default_mode`;主持的会话 turn 保持 ReAct,而成员 turn(@点名 / handoff / 板上运行)用成员人格的 `default_mode`(explainer 跑 cot)。对子代理的 `wait` 是 `subagent` 能力的 `wait` 动作:0.5 秒轮询,默认超时 120 秒,上限 600 秒。

## 编排(`orchestrator/`)

- **任务图**(`task_graph.py`)— 派发的父子树,深度上限(`agent.subagents.max_depth`,默认 3);`depends_on` 未满足时派发保持为 `DeferredDispatch`;`finish_task` 汇入图。不是通用 DAG 引擎。
- **派发**(`dispatch.py`)— 人格解析(内置 → 用户 registry 回退)、工具面交集、网络收窄(`narrow_network`)、后台运行、完成通知合成(`synthesize.py`)、`on_subagent_start`/`on_subagent_end` 钩子。
- **黑板**(`blackboard.py`)— 任务范围共享笔记;实例之间从不直接对话。
- **摘要**(`digest.py`)— `DigestStore` 保存每个子代理的状态卡;orchestrator 只见摘要,不见原始上下文。
- **仲裁**(`arbiter.py`)— turn 运行中对新用户输入做合并/排队/延后(`agent.arbiter.mode`)。
- **Goal**(`goal.py`、`goal_driver.py`)— 每会话一个持久 goal,存于会话存储 meta;驱动器经持久队列调度带预约门槛的续跑轮;启动时绝不自动复活已暂停的 goal。
- **主动联络**(`proactive.py`、`outreach_budget.py`)— `user.online` 时问候,以及来自持久队列的一条跟进链,受 `agent.outreach.*` 预算封顶。
- **任务通知**(`job_notify.py`)— 调度器完成产生安静通知或受预算门控的唤醒 turn。
