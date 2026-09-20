# platform — 横切基础设施

> 语言：简体中文 | [English](README.md)

唯一允许所有模块依赖的层：**只有机制，没有业务逻辑，没有领域词汇或品牌名**。它定义“怎么说话”，从不定义“说什么”。

| 子包          | 职责                                                       |
| ------------- | ---------------------------------------------------------- |
| contracts     | 事件 / DTO / 错误码 / 协议版本（纯类型，零依赖）           |
| actor         | 本机令牌、调用上下文（认证）                               |
| eventbus      | 持久化事件日志 + 发布/订阅 + 游标                          |
| capability    | 定义一次 → REST + MCP 双生成，入口门禁；含审计存储 audit_db |
| settings      | 设置框架：schema/密钥项/变更事件                           |
| health        | 健康探测与统一错误构造                                     |
| secrets       | 密钥保管：静态加密、按需下发、脱敏                         |
| webguard      | 出站 Web 安全：URL 策略、DNS 钉扎、重定向策略、有界正文读取 |
| limit         | 限流与配额（CostQuota 位于 capability 的守卫链中）         |
| audit         | 审计查询/可视化（存储在 capability/audit_db，见其 README） |
| observability | 结构化日志、追踪、指标                                     |
| config        | 配置加载约定：默认值 < 配置文件 < 环境变量                 |

导入约定：目录即职责边界；导入名为 `platform_<dir>`（避免与标准库 `platform` / `secrets` 等
冲突）。contracts、actor、eventbus、capability、settings、health、secrets、webguard 各子包有自己的
pyproject 与独立测试；limit、audit、observability、config 目录是尚无代码的文档占位，各带一份 README。

本目录树的工作约定：[AGENTS.md](../AGENTS.md)。
