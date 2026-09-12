# agent.tools — agent 自身工具

## Purpose

不经领域服务的内部工具:agent 的"手脚"(workspace / net)、交互通道(interact)、
自管理(context / memory / skill / session / team / extension / observe)。领域能力经
`host.bridge` 以 `域__能力` 名接入,本包不感知领域实现。

目录纪律(任务书 §4.4):**一工具一文件,文件名 = 工具名**,每文件导出唯一工厂
`<name>_tool(...) -> AgentTool`;机制文件(jail / workdir / todo_store / net_guard /
question_broker)按机制职责命名;组 `__init__.py` 只做零逻辑聚合。形态由
`agent/tests/granularity/test_file_granularity.py` 锁定。

```
core/        机制层:AgentTool/Toolbelt(base)、装配期来源注册表(registry)、执行管线
             (invoke:校验→policy→确认→hook→重试→熔断→结果预算)、结果信封(outcome)、
             分级激活(activate)、agent 自身能力绑定(self_capability:经 execute 守卫链 + 审计)
workspace/   read_file · write_file · edit_file · list_dir · delete_file · grep · glob · run_shell ·
             todo_write · todo_read;机制 jail / workdir / todo_store
net/         web_fetch · web_search;机制 net_guard(DNS/内网解析守卫)
interact/    ask_user · request_context;机制 question_broker
context/     context_status · compact_context(与人侧同名能力共用 context.operations)
memory/      recall_memory · get_memory · clear_memory · set_profile · delete_profile
skill/       load_skill
session/     session_list · session_create · session_fork · rename_session · delete_session · read_history
team/        spawn_subagent · cancel_run · resume_run · register_subagent · list_subagents ·
             list_resumable_checkpoints · abandon_resumable_checkpoint
extension/   list_plugins · install_plugin · uninstall_plugin · list_mcp_servers · preview_mcp_tools ·
             reload_user_hooks · list_user_hooks
observe/     read_events · get_resource_quota · list_tools
```

## Configuration

工具本身无独立设置键;行为受 `agent.fs.*`(附加根)、`agent.network.*`、`agent.app.*`、
`agent.context.tool_result_max`(结果溢写)影响,全部热读。

## Extension Points

- 新增内置工具:在对应组建 `tools/<组>/<名>.py`,导出 `<名>_tool`,在组 `__init__.py` 聚合,
  在 `build.py` 注册;若人侧也应有同名能力,在 `capabilities/<组>/<名>.py` 落实现并让工具经
  `core/self_capability.capability_tool` 绑定同一能力(人机同源、审计对称);
- 治理类工具须声明 `write` / `irreversible`,由 policy 分级(L1 通知 / L2 确认);
- 例外(单侧存在)必须登记到 `agent/parity.py` 并写理由,否则 parity 冻结测试红。

## Model Experience

- 工具名与人侧能力严格同名(`install_plugin`,不是 `plugin_install`);描述为中文、面向可行动;
- 调用失败分型:`[参数错误]`(schema 未过,无副作用)→ `[已拒绝]`(policy / 守卫)→
  `[需确认]` / `[已取消]`(L2)→ `[已拦截]`(熔断)→ `[工具失败]`(handler 异常,含 ServiceError 文案);
- 对话实例首轮只见 CORE 激活集(含 `llm__get_usage_stats`);治理工具按需 `activate_tools(names=[...])`;
- 成本档:只读工具 `concurrent_safe=True` 可并行;写工具零重试。

## Known Limitations

- `rename_session` / `delete_session` 对用户当前会话直接拒绝(交互契约),不提供覆盖开关;
- `read_events` 只读白名单类型(不含 agent.delta / agent.ask);
- `run_shell` 不经 shell 解释(无管道/重定向),Windows 内建命令不可用。

## Deferred Work

- 阶段 21:`run_shell` 路由 code_exec 域(统一执行通道);`net_guard` 迁 `platform_webguard`;
- 阶段 19:`jobs/` 组(list_jobs / cancel_job)、`interact/reach_out`;
- 阶段 20:`team/read_board` / `write_board`。
