# platform/contracts — 契约包

> 语言：简体中文 | [English](README.md)

各模块共享的**纯类型**层：事件信封、capability 输入/输出 DTO、统一错误码、协议版本。

铁律：

- 纯类型，零逻辑，**零第三方依赖**；
- apps / agent / services 三方唯一直接引用的包；
- 前端 TS 类型由本包生成，三方共享同一份理解；
- 协议变更须递增 `version.py` 中的 `PROTOCOL_VERSION`。

导入名为 `platform_contracts`（避免与标准库 `platform` 冲突）。

## 术语表（一词一义；全仓库共享）

| 术语                 | 唯一含义                                                                                                  | 边界                                                                                                                             |
| -------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **capability**       | domain 服务/agent 在 registry 中注册的能力（schema + handler + 元数据）；REST 与 MCP 均由 registry 生成    | 仅存在于 `Registry` 中；其名称即 `service.json` 中注册的名称                                                                      |
| **tool（AgentTool）** | agent 侧可被 LLM 调用的工具，挂载在 Toolbelt 工具面上                                                      | domain 能力经 `host.bridge.make_domain_tools` 桥接为 `<domain>__<capability>`；agent 内置工具（fs/shell/web/spawn…）不来自 registry |
| **skill**            | SKILL.md 知识包；加载后进入系统上下文                                                                     | 不是工具，不可执行；只注入提示词                                                                                                  |
| **MCP server**       | 用户在设置页添加并批准的**外部**服务器，经 McpClientPool 挂载进工具面                                      | 不要用它再接入本仓库自己的 `<domain>/mcp_server`（单体形态下这些能力已桥接进来）                                                   |

同一次调用中，capability 名称 `<name>` 在各处完全一致；不同的只是外壳：
HTTP 为 `POST /api/<domain>/capabilities/<name>`；agent 工具名为 `<domain>__<name>`；
各服务自己的 MCP server 以裸名 `<name>` 暴露该工具（域由服务器本身消歧）。

---

## 用途

各层共享的纯 dataclass/枚举：Event、DomainEvent、RuntimeEvent、ActorRef/Kind、ServiceError/ErrorSuffix、用量类型。零逻辑。

## 配置

无。

## 扩展点

当变更确实跨层时，在此新增契约类型；使用方绝不可自行重复声明结构。

## 已知限制

类型即冻结表面：重命名或改动任何字段结构都是破坏性协议变更（由 version.py 把关）。

## 暂缓事项

更结构化的错误提示。
