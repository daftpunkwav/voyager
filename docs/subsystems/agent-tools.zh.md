# Agent 工具面

[English](agent-tools.md) | 中文

工具面:工具如何声明、组合为按代理裁剪的视图、授权与调用。完整工具清单(含类别与动作)见 [tool-catalog.zh.md](../catalog/tool-catalog.zh.md)。

源码:`agent/src/agent/tools/`

## 工具模型

`tools/core/model.py` — `AgentTool`:`name`、`description`、`handler`、`schema`(JSON Schema)、`dimension`(fs/network/app/shell/skill)、`write`、`irreversible`、`concurrent_safe`、`timeout_s`。

`tools/core/registry.py` — `ToolRegistry` 在装配时合并具名 `ToolSource`(后者优先;`origins()` 记录归属)。`tools/core/base.py` — `Toolbelt` 持有名册并派生视图:`specs()`、`roster()`、`describe(name)`、`trimmed(allow)`(支持 `prefix*` 授权)、`trimmed_read_only()`、`with_active(active, extra)`(分级激活)、`with_policy(policy)`,以及 `call()` / `call_detailed()`。

## 权限

每次调用由两层裁决:

1. **`policy/permissions.py` `ToolPermissions`** — agent actor 门,读设置 `agent.permissions`:`{"mode": "full"|"no_dangerous"|"read_only", "deny": [...], "allow": [...]}`。条目可以是工具名(`"bash"`)、工具动作(`"session.delete"`)或 bash argv 前缀(`"bash:git *"`)。`TOOL_CLASS` 把每个工具映射为 `R`(只读)或 `D`(危险);未知工具归为 `D`(fail-closed),另有成文的动作级覆盖(如 `session.delete`、`jobs.cancel`、`memory.forget`、`extension.install`)。旧键 `agent.shell.denied` 的条目合并为 bash 拒绝前缀。
2. **`policy/engine.py` `PolicyEngine`** — 维度门:`decide(Action(dimension, target, write, irreversible))` → `Decision`。各维度(`network.py`、`fs.py`、`app.py`、`shell.py`)热读自己的设置;级别为 `L0` 放行、`L1` 通知、`L2` 确认。`L2` 确认只在 `decision.confirm_scope == "write_roots"` 时生效 — 写入用户配置的 write roots 需走询问确认回调;其余情形直接执行,至多发出 `agent.policy.notify` 事件。

文件系统根:`agent.fs.read_roots` / `agent.fs.write_roots` 在装配时固定牢笼;fs 工具同时拿到热读函数,设置变更无需重启即生效。

## 调用管线

`tools/core/invoke.py` — `invoke_tool` / `invoke_detailed`:

1. 找工具;未命中时给出近似名与未激活域提示。
2. `validate_arguments` — 一层 JSON-schema 校验。
3. `ToolPermissions.check` — 模式/拒绝/允许门。
4. `policy.decide(Action)` — 维度门;结果:拒绝、L2 确认(仅 write_roots)、L1 通知、放行。
5. `pre_tool` 钩子 — 返回 `False` 拦截。
6. 处理器带重试与每工具 `CircuitBreaker`;写入与不可逆调用绝不重试;超时与 `ServiceError` 不重试。
7. 计量记录(`MeterRecord(kind="tool", ...)`)。
8. `post_tool` 钩子;结果归一为 `ToolResult`;情景记录。
9. 结果预算 — 超限结果外溢到 `workspace/spill/`(`agent.context.tool_result_max` / `agent.context.tool_result_max_lines`)。外溢写盘失败退化为纯截断;外溢目录限额是独立的尽力而为清理,绝不截断未超限的结果。

## MCP 工具

`mcp/` 挂载外部 MCP 服务器(`agent.mcp.servers`,须批准):远端工具成为 `mcp__<server>__<tool>` 的 agent 工具(`mcp/mount.py`),`dimension="app"`,仅在批准后注册。`McpSession`(`mcp/session.py`)以 JSON-RPC 2.0 走 stdio 或 HTTP,调用超时 30 秒。只有服务端裁决的 JSON-RPC 错误(`McpRpcError`)以 `[MCP 错误]` 文本返回;超时与传输故障上抛,进入管线的重试与熔断。

## 域工具桥

host 为每个域能力注入一个工具,命名 `<domain>__<capability>`(`packages/host/src/host/bridge.py`),以 actor `agent.main` 走完整守卫链执行。策展子集默认注册(如 `notes`、`graph`、`sources`、`settings__get_theme`),其余按需激活([tool-catalog.zh.md](../catalog/tool-catalog.zh.md))。

## Parity

`agent/src/agent/parity.py` 钉住人机 parity 契约:REST 暴露的能力,agent 可以同名 `domain__capability` 调用;偏差只在模块内枚举,由 host 的 parity 测试(`test_parity_surface`)把关。
