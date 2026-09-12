# platform — 横切设施

唯一允许被所有模块依赖的层:**只含机制,不含业务,不出现领域词汇与品牌名**
(docs-local/design/architecture.md §7)。它定义"怎么说话",从不定义"说什么"。

| 子包 | 职责 | 状态 |
|---|---|---|
| contracts | 事件/DTO/错误码/协议版本(纯类型零依赖) | ✅ 已实现 |
| actor | 本机令牌、调用上下文(鉴权,§7.4) | ✅ 已实现 |
| eventbus | 持久化事件日志 + 发布/订阅 + 游标(§7.2) | ✅ 已实现 |
| capability | 一次定义 → REST + MCP 双生成,入口守卫(§7.3);含审计落库 audit_db | ✅ 已实现 |
| settings | 设置项框架:schema/secret/变更事件(§7.9) | ✅ 已实现 |
| health | 健康探测与统一错误构造(§7.10) | ✅ 已实现 |
| secrets | 密钥保管:加密落盘、按需分发、脱敏(§7.7) | ✅ 已实现 |
| limit | 限流与配额(§7.5;当前在 capability guards 内置 CostQuota) | 骨架 |
| audit | 审计查询/可视化(落库暂居 capability/audit_db,见其 README) | 骨架 |
| observability | 结构化日志、trace、指标(§7.8) | 骨架 |
| config | 配置加载约定:默认 < 配置文件 < 环境变量(§7.7) | 骨架 |

导入约定:目录是职责边界;import 名为 `platform_<目录>`(避免与标准库
`platform` / `secrets` 等冲突)。已实现的七个子包各有独立 pyproject 与
独立测试;标"骨架"的四个子目录是文档占位,尚无代码。
