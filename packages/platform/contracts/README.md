# platform/contracts — 契约包

跨模块共享的**纯类型**层:事件信封、capability 输入输出 DTO、统一错误码、协议版本。

铁律(见 docs-local/design/architecture.md §7.1):

- 纯类型,零逻辑,**零第三方依赖**;
- 唯一直接被 apps / agent / services 三方引用的包;
- 前端 TS 类型由本包生成,三方认知一致;
- 协议变更升 `version.py` 中的 `PROTOCOL_VERSION`。

import 名为 `platform_contracts`(避免与标准库 `platform` 冲突)。

## 术语对照(一词一义,全仓共用)

| 词 | 唯一含义 | 边界 |
|---|---|---|
| **capability** | 领域服务/agent 在注册表登记的能力(schema + handler + 元数据,§7.3),REST 与 MCP 均由注册表生成 | 只存在于 `Registry`,名字即 `service.json` 登记名 |
| **tool(AgentTool)** | agent 侧 LLM 可调用的工具,挂在 Toolbelt 工具面 | 领域能力经 `host.bridge.make_domain_tools` 桥为 `<domain>__<capability>`;agent 内生工具(fs/shell/web/spawn…)不来自注册表 |
| **skill** | SKILL.md 知识包,装载后进 system 上下文(§9.10) | 不是工具、不可执行,只注入提示 |
| **MCP server** | 用户在设置页添加并批准的**外接** server,经 McpClientPool 挂进工具面 | 禁止用它把本仓 `services/*/mcp_server` 再灌一遍(单体下能力已桥入) |

同一次调用的能力名 `<name>` 处处一致,只是包装不同:
HTTP `POST /api/<domain>/capabilities/<name>`;agent 工具名 `<domain>__<name>`;
各服务自带 MCP server 的 tool 名为裸 `<name>`(域由 server 本身区分)。

---

## Purpose

Pure dataclasses/enums shared by every layer: Event, DomainEvent, RuntimeEvent, ActorRef/Kind, ServiceError/ErrorSuffix, usage types. Zero logic.

## Configuration

None.

## Extension Points

Add new contract types here when a change is genuinely cross-layer; consumers must never re-declare shapes.

## Known Limitations

Types are frozen surfaces: renaming or reshaping any field is a breaking protocol change (version.py gates it).

## Deferred Work

More structured error hints.
