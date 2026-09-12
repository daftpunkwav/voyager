# platform/capability — 能力框架

**一次定义,双协议生成**(§7.3):

- 定义:名称、描述(写给 LLM:何时用、返回什么)、输入模型、元数据(cost / reversible /
  scopes)、handler;
- `gen_rest.build_router`:注册表 → FastAPI router(给 gateway);
- `gen_mcp.build_server`:注册表 → MCP server(给 agent / 外部客户端);
- 入口强制三件事(框架层,不在 handler 里):鉴权(§7.4)、限流配额(§7.5)、审计(§7.6);
- 长任务约定:handler 只入队并返回 `JobRef`;`long_running=True` 时不返回 JobRef 视为缺陷;
- 新增能力 = 注册表新增条目,REST / MCP / agent 三处零改动。

fastapi 为可选依赖(extra `rest`);MCP SDK 按需 `pip install 'mcp>=1.0'`(本仓
`services/mcp` 占用了 mcp 工作区名,故未声明为 extra)。基础安装零第三方依赖。

---

## Purpose

Capability framework: @capability registration, Registry, execute() guard chain (auth -> quota -> validate -> invoke -> audit), REST/MCP generators, CostQuota, SqliteAuditSink.

## Configuration

None (sinks/quotas injected at the composition root).

## Extension Points

New guard type = one function composed in execute(); generators live in gen_rest/gen_mcp.

## Known Limitations

Quota is a single daily-budget implementation.

## Deferred Work

Per-actor quota dimensions.
