# 工具目录

[English](tool-catalog.md) | 中文

装配时注册的 agent 工具面。声明位置是权威;本页做摘要并链接。工具机制(权限、调用管线)见 [agent-tools.zh.md](../subsystems/agent-tools.zh.md)。

## 内置工具

| 工具 | 声明位置 | 用途 |
|---|---|---|
| `read` / `write` / `edit` | `agent/src/agent/tools/workspace/` | 工作区牢笼内的文件访问 |
| `glob` / `grep` | `agent/src/agent/tools/workspace/` | 文件检索 |
| `bash` | `agent/src/agent/tools/workspace/` | shell,cwd = 工作区 |
| `todowrite` | `agent/src/agent/tools/workspace/` | 计划/todo 列表维护 |
| `web_fetch` / `web_search` | `agent/src/agent/tools/net/` | 出站 web,`dimension="network"` |
| `ask_user` | `agent/src/agent/tools/interact/` | 经询问回调的人类问答 |
| `request_context` | `agent/src/agent/tools/interact/` | 向前端请求页面/工作区上下文 |
| `skill` | `agent/src/agent/tools/skill/skill.py` | 加载或提议技能(动作含 `load`、`propose`) |
| `plan` | `agent/src/agent/tools/plan/plan_ops.py` | 计划门操作(晚加绑) |
| `scratchpad` | `agent/src/agent/tools/plan/` | 草稿笔记 |
| `context` | `agent/src/agent/tools/context/context.py` | 面向 LLM 的上下文状态与压缩 |
| `activate_tools` | `agent/src/agent/tools/core/activate.py` | 休眠域工具的分级激活 |

## 能力聚合工具

每个包一个 agent-registry 能力(`tools/core/self_capability.py: capability_tool`),以 actor `agent.main` 执行:

| 工具 | 声明位置 | 动作(示例) |
|---|---|---|
| `subagent` | `agent/src/agent/capabilities/team/subagent.py` | `spawn`、`list`、`register`、`unregister`、`wait`、`send` |
| `agent_instance` | `agent/src/agent/capabilities/team/` | 实例查看/取消/放弃 |
| `board` | `agent/src/agent/capabilities/team/` | 黑板笔记 |
| `goal` | `agent/src/agent/capabilities/team/goal.py` | 会话级 goal 生命周期 |
| `memory` | `agent/src/agent/capabilities/memory/memory.py` | `query`、`recall`、`remember`、`forget`、`clear` |
| `extension` | `agent/src/agent/tools/extension/` | 插件批准/安装/卸载/重载 |
| `session` | `agent/src/agent/capabilities/session/` | 会话管理(含 `delete`) |
| `observe` | `agent/src/agent/tools/observe/` | 轨迹/日志检视 |
| `jobs` | `agent/src/agent/tools/jobs/` | 任务列表/取消/重排 |
| `tools` | `agent/src/agent/tools/tools/tools.py` | 工具目录内省(`describe_tool`、`list_tools`) |

## 域工具

host 为已接线域注入 `<domain>__<capability>` 工具(`packages/host/src/host/bridge.py`),如 `notes`、`graph`、`sources`、`settings__get_theme`。策展子集默认注册(`build.py` 的晚加绑注册:`plan_tools`,随后 `team_tools`/`memory_tools`/`extension_tools`/`session_tools`/`observe_tools`/`jobs_tools`/`tools_tools`);页面关联域经 `_PAGE_PREACTIVATE` 预激活(`notes`、`graph`、`sources`);其余经 `activate_tools` 激活。

## MCP 工具

外部 MCP 服务器(`agent.clients.servers`)的工具挂载为 `mcp__<server>__<safe-name>`(`agent/src/agent/mcp/mount.py`),`dimension="app"`,仅在用户批准后注册。

## 恒激活集

`CORE_TOOLS`(`agent/src/agent/tools/core/activate.py`)始终激活:`ask_user`、`subagent`、`skill`、`memory`、`request_context`、`todowrite`、`read`、`write`、`edit`、`bash`、`grep`、`glob`、`settings__get_theme`、`settings__set_theme`、`activate_tools`、`context`、`session`、`llm__get_usage_stats`。

## 分类

`policy/permissions.py` 的 `TOOL_CLASS` 把每个工具映射为 `R`(只读)或 `D`(危险);未知工具为 `D`(fail-closed)。动作级覆盖把只读工具内的特定动作标为 `D`(如 `session.delete`、`jobs.cancel`、`memory.forget`、`extension.install`、`subagent.register`)。该分类驱动 `agent.permissions` 的模式(`full` / `no_dangerous` / `read_only`)。
