# 平台包

[English](platform.md) | 中文

`packages/platform/` 容纳八个独立、轻依赖的框架包。它们承载全部共享机构 — 类型、认证、事件、能力框架、设置、密钥、健康与 URL 安全 — 不含业务逻辑。导入方向单向:业务代码 import `platform_*`;`platform_*` 从不 import 业务代码(由 `import-linter.ini` 契约 `platform-no-business` 强制)。

## platform_contracts

`packages/platform/contracts/src/platform_contracts/` — 纯共享类型,零依赖。`events.py` 定义事件词表 `DomainEvent`(跨域总线事件,如 `user.message`、`task.completed`、`agent.step`)与 `RuntimeEvent`(agent 运行生命周期)。`models.py` 定义 `ActorRef`/`ActorKind`、`JobRef`/`JobStatus`、`HealthReport`/`HealthStatus`。`errors.py` 定义 `ServiceError`(错误 `code` + 消息 + hint)、`ErrorEnvelope` wire 形状与 `HTTP_STATUS` 映射。版本常量(`PROTOCOL_VERSION`、`ENVELOPE_VERSION`)与 `new_trace_id()` 也在这里。

## platform_actor

`packages/platform/actor/src/platform_actor/` — 每条守卫链背后的 actor 模型。`ActorContext` 携带解析出的 `ActorRef` 与 scopes。`LocalTokenIssuer` 铸发 bearer token(`machine.token`);`resolve_http_actor` 从 `Authorization: Bearer` 或会话 cookie(`COOKIE_NAME`)解析 HTTP 请求的调用方,未认证的回环请求按 `LOCAL_USER` 处理,未认证的非回环请求被拒绝。`is_loopback`/`is_public_path` 支撑该判定。

## platform_eventbus

`packages/platform/eventbus/src/platform_eventbus/` — 只追加日志加进程内扇出。`EventLog` 把每条 `Event` 持久化到 SQLite `events` 表,以自增 `seq` 为键,带 `Retention` 清扫(host 只保留 `agent.delta` 行,24 小时)。`EventBus` 向进程内异步订阅者投递,落后时将其标记为 `lagged`;消费者按 `seq` 从日志重放。`CursorStore` 持久化每个订阅者的游标。完整参考:[eventbus.zh.md](eventbus.zh.md)。

## platform_capability

`packages/platform/capability/src/platform_capability/` — 能力框架:`Capability`/`Registry`/`@capability`、REST 路由生成(`gen_rest.py`)、MCP 服务器生成(`gen_mcp.py`)、守卫链(`guards.py`)、`Wiring`(`wiring.py`)与审计 sink(`audit_db.py`)。完整参考:[capability-framework.zh.md](capability-framework.zh.md)。

## platform_settings

`packages/platform/settings/src/platform_settings/` — 设置框架。`SettingDef` 声明键的类型(`STR`/`INT`/`FLOAT`/`BOOL`/`CHOICE`/`JSON`)、默认值与标志(`secret`、`user_only`)。`validate` 依据定义矫正并校验值。`SettingsStore` 把值持久化到 SQLite `setting_values` 表,拒绝业务层对 `secret` 项的写入,并在每次提交时发布 `settings.changed`。键由属主在接线时注册;已注册键的目录见 [config-catalog.zh.md](../catalog/config-catalog.zh.md)。

## platform_secrets

`packages/platform/secrets/src/platform_secrets/` — 加密密钥存储。`SecretStore` 把值以 Fernet 加密存入 SQLite `secrets` 表;密钥材料来自环境(`load_key_material`),绝不来自数据库。`SecretUnavailableError` 表示密钥缺失或不可解密。供应商的 API key 存放于此,不在供应商元数据里。

## platform_health

`packages/platform/health/src/platform_health/` — `HealthMonitor` 把 `Probe` 结果聚合为 `HealthReport`;gateway 在 `GET /health` 暴露聚合结果。

## platform_webguard

`packages/platform/webguard/src/platform_webguard/` — 共享的出站 URL 安全机构,供 `sources.save_url` 与 agent web 工具使用:`url_policy`(scheme/host 规则)、`dns_pin`(解析、校验、为连接钉住 IP)、`redirects`(逐跳重新校验)与 `body` 尺寸上限(`read_bounded`)。
