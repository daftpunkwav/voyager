# Host(组合根)

[English](host.md) | 中文

`host` 是唯一 import `agent`、`gateway` 与全部域 wiring 的包。它拥有启动流程、共享设施、跨域通道与 agent↔域的桥。它不是可路由的域;它把所有东西组合为一个 8000 端口上的 gateway 应用。

源码:`packages/host/src/host/`

## 启动管线

1. **扫描**(`scan.py`)— `scan(root, prefix)` 把每个 `packages/*/service.json` 读为 `ServiceCard`(`domain`、`module`、`port`、`capabilities`、`subscribes`、`publishes`、`needs`、`depends_on`、`enabled_by_default`、`role`)。发现只读卡片,不读代码。`_` 前缀目录与 `SKIP_DIR_NAMES = {"platform", "host"}` 被跳过。
2. **规划**(`plan.py`)— `select_enabled` 解析启用集合:`ENABLE_DOMAINS` 环境变量 → `host.domains.enabled` 设置 → 卡片 `enabled_by_default`。`topo_order` 按 `depends_on` 排序(Kahn;成环拒绝启动)。gateway 角色卡片注册其设置。
3. **组装**(`assemble.py`)— `build()`(以 `uvicorn host.assemble:build --factory` 服务)在 `data/runtime/` 下构造共享设施,接线每个启用的域,构建 agent,然后把一切交给 `gateway.rest.create_app`。
4. **开发入口**(`dev.py`)— `python -m host.dev` 在 `apps/web` 拉起 `npm run dev`,并在 `127.0.0.1:8000` 运行 uvicorn;Ctrl+C 同时收掉两者。

## 共享设施

`build()` 每进程构造一次,位于 `data/runtime/`:`EventLog`(`events.db`,`agent.delta` 保留 24 小时)、`EventBus`、`SecretStore`(`secrets.db`)、`SettingsStore`(`settings.db`)、`SqliteAuditSink`(`audit.db`)、`LocalTokenIssuer`(`machine.token`)、`[CostQuota(日预算 50 000)]`。`os.environ` 在 import 时从仓库 `.env` 播种。每个域获得 `data_dir = data/runtime/<domain>/`;agent 获得 `data/runtime/agent/`。

## Wiring 注入

对每张启用的卡片,`_wire_card` import `<module>.wiring.wire()`,并从固定集合 `SHARED_KEYS = {bus, secrets, settings_store, workspace, audit, quota, call, call_sync}` 注入卡片声明的 `needs`。未知 needs 或未知 kwargs 使启动失败。返回的 `Wiring` 贡献一个 `MountSpec(domain, registry, probe, extra_router)`。

## Agent 集成

- **`bridge.py`** — `make_domain_tools(mounts)` 产出名为 `<domain>__<capability>` 的 agent 工具;执行以 actor `ActorRef(kind=AGENT, id="agent.main", scopes=("domain:*",))` 走完整守卫链。
- **`llm_routing.py`** — `ServiceLLM`、`RoutingServiceLLM`、`PersonaRoutingServiceLLM` 按用途、按人格经晚加绑调用在 `llm` 域内解析聊天传输;设置 `agent.llm.overrides` 与 `agent.llm.routing` 引导解析。`embedder_adapter.py` 把 `llm.embed` 适配为 agent 记忆向量召回,降级为 `EmbeddingUnavailable`。
- **`agent_rebuild.py`** — `POST /api/workspace/switch` 背后的免重启工作区切换;`jobs_router.py` 暴露基于 `JobsView`(读事件日志)的任务取消/重排端点。

## 跨域调用

`call.py` — `bind_calls(wirings)` 返回 `call` / `call_sync(domain, name, args)`,这是域之间唯一被认可的通道。调用以 `HOST_ACTOR`(`ActorKind.SYSTEM`,通配 scope)走守卫链执行。使用方:graph L0 → `sources.list_sources`;host LLM 路由 → `llm.*`;embedder → `llm.embed`。

## host 注册的设置

`host/settings.py` 与 `plan.py` 注册 `host.domains.enabled` 与 gateway 键(`gateway.chat.history_page_size`、`gateway.rate_limit.per_minute`、`gateway.sse.max_connections`);`host/plan.py` 还承载 `test_settings_parity.py` 使用的 parity 测试夹具。
