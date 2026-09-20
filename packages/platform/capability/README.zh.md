# platform/capability — 能力框架

> 语言：简体中文 | [English](README.md)

**定义一次，双协议生成**：

- 定义：name、description（为 LLM 而写：何时使用、返回什么）、输入模型、元数据（cost / reversible / scopes）、handler；
- `gen_rest.build_router`：registry → FastAPI router（供 gateway 使用）；
- `gen_mcp.build_server`：registry → MCP server（供 agent / 外部客户端使用）；
- 入口处强制三件事（在框架层，而非 handler 内）：认证、限流/配额、审计；
- 长任务约定：handler 只入队并返回 `JobRef`；`long_running=True` 时不返回 JobRef 视为缺陷；
- 新增一个能力 = registry 新增一条，REST / MCP / agent 侧零改动。

fastapi 为可选依赖（extra `rest`）；MCP SDK 按需安装。基础安装零第三方依赖。

---

## 用途

能力框架：@capability 注册、Registry、execute() 守卫链（auth -> quota -> validate -> invoke -> audit）、REST/MCP 生成器、CostQuota、SqliteAuditSink。

## 配置

无（sink/quota 在装配根注入）。

## 扩展点

新守卫类型 = 在 execute() 中组合的一个函数；生成器位于 gen_rest/gen_mcp。

## 已知限制

配额只有单一的日预算实现。

## 暂缓事项

按 actor 的配额维度。
