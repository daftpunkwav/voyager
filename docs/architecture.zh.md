# Voyager 架构

[English](architecture.md) | 中文

改动组合或接线前先读本文。Voyager 是本地优先的单用户工作台:Python 后端组合为单进程,前端为浏览器应用。本地机器之外没有部署拓扑;全部持久化是 `data/` 下的 SQLite 与文件。

## 源码根

| 根 | 内容 |
|---|---|
| `packages/platform/` | 八个框架包(`platform_contracts`、`platform_actor`、`platform_eventbus`、`platform_capability`、`platform_settings`、`platform_secrets`、`platform_health`、`platform_webguard`),不含业务逻辑 |
| `packages/<domain>/` | 十个业务域包:`browser`、`code_exec`、`gateway`、`graph`、`host`、`llm`、`notes`、`office`、`settings`、`sources` — 每个是 src 布局的 uv workspace 成员,含 `service.json` 卡片、`src/<domain>/`、`tests/` |
| `agent/` | agent 引擎(`src/agent/`):事件驱动 ReAct 循环、工具面、上下文工程、记忆、技能、子代理 |
| `apps/web/` | 前端:React 19 + TypeScript + Vite |
| `plugins/` | 用户插件,纯声明式(`plugin.json` + `skills/` + `hooks/` + `mcp.json`);经用户显式批准后由 agent 加载 |
| `data/` | 全部运行时状态:`data/runtime/`(存储)、`data/workspace/`(工作工作区) |

每个域包遵循同一脚手架(见 `packages/_template/`):`service.json`(模块卡片)、`src/<domain>/capabilities.py`、`wiring.py`、`rest.py`、`mcp_server.py`、`store.py`、`settings.py`。

## 分层与依赖规则

依赖只指向一个方向,由 `import-linter.ini` 强制:

```text
platform_*  ◀── { gateway, agent, 全部域 }  ◀── host
```

- `platform_*` 包从不 import 业务代码。
- 域之间从不互相 import。跨域交互只通过 host 提供的两个通道:晚加绑的能力调用(`host.call.bind_calls` → `call` / `call_sync`)与总线事件(`platform_eventbus`)。
- 只有 `host` import `agent` 和 `gateway`(加上它组装的域 wiring)。`agent` 只 import `platform_*` — 从不 import 域。
- `gateway` 包不 import 任何域(`packages/gateway/README.md` 的"zero domain imports");域以挂载路由的形式进入 gateway。

## 能力即服务单元

每个业务操作是一个 `Capability`(`platform_capability/define.py`):frozen dataclass,绑定名称、描述、Pydantic 输入模型与处理器,注册进各域的 `Registry`。一次注册,框架投影出两个面:

- REST:`build_router` 产出 `GET /capabilities` 与 `POST /capabilities/{name}`;host 将每个 registry 挂载到 `/api/<domain>`(`gateway/mounts.py`),统一调用形态为 `POST /api/<domain>/capabilities/<name>`。
- MCP:`build_server`(`platform_capability/gen_mcp.py`)经 `python -m <domain>.mcp_server` 以 stdio 暴露同一 registry。

执行经过统一守卫链(`platform_capability/guards.py`):actor 认证 → 成本配额 → 参数校验 → 处理器 → 审计。同一链条服务人类 REST 调用与 agent 调用;差别仅在 `ActorRef`(`ActorKind.USER` 与 `ActorKind.AGENT`)。`agent/src/agent/parity.py` 钉住人机面 parity 契约。

## 组合:host

`packages/host/src/host/assemble.py`(`build()`)是组合根。启动流程:

1. 在 `data/runtime/` 下构造共享设施:`EventLog`(events.db)、`EventBus`、`SecretStore`(secrets.db)、`SettingsStore`(settings.db)、`SqliteAuditSink`(audit.db)、`LocalTokenIssuer`(machine.token)、`CostQuota`。从仓库 `.env` 播种 `os.environ`。
2. 扫描 `packages/*/service.json`(`scan.py`)为 `ServiceCard`;按 `ENABLE_DOMAINS` 环境变量 → `host.domains.enabled` 设置 → 卡片默认值选择启用的域,并按 `depends_on` 拓扑排序(`plan.py`)。
3. 对每张卡片调用 `<module>.wiring.wire()`,从固定集合(`bus`、`secrets`、`settings_store`、`workspace`、`audit`、`quota`、`call`、`call_sync`)注入卡片声明的 `needs`。未知 needs 或 kwargs 使启动失败。新增域 = 放入一个带 `service.json` 的目录;host 无需改动。
4. 构建 agent(`agent.build.build_agent`),把每个已接线的域 registry 桥接为名为 `<domain>__<capability>` 的 agent 工具(`host/bridge.py`),并注入基于晚加绑调用的 LLM/嵌入适配器(`host/llm_routing.py`、`host/embedder_adapter.py`)。
5. 将全部 `MountSpec` 与额外路由(uploads、workspace、switch、jobs)交给 `gateway.rest.create_app`,在单一端口 **8000** 上服务。

`service.json` 中的各域端口(8010–8080)只适用于独立的 `uvicorn <domain>.rest:app_factory --factory` 运行;组合进程中所有域都在 8000 之后。graph 的 C 引擎 sidecar 是唯一外部进程(默认 `http://127.0.0.1:8123`)。

## agent 引擎

`agent/src/agent/` 是事件驱动引擎,不是请求处理器。`build.py:build_agent()` 用 `platform_*` 原语组装 `AgentApp`(loop、master、工具、记忆、存储);`packages/host/src/host/assemble.py` 以组合好的设施调用它。turn 生命周期见 [agent-loop.zh.md](subsystems/agent-loop.zh.md),工具面见 [agent-tools.zh.md](subsystems/agent-tools.zh.md)。

host 集成点:

- 事件接线:agent 的 `EventLoop` 订阅总线模式;`user.message` 触发 `Master.handle_user_message`(`agent/src/agent/runtime/wire.py`)。
- 域工具:`<domain>__<capability>` 工具以 actor `agent.main` 走完整守卫链执行(`host/bridge.py`)。
- LLM 传输:`RoutingServiceLLM` / `PersonaRoutingServiceLLM` 按用途经晚加绑调用在 `llm` 域内解析供应商/模型(`host/llm_routing.py`);agent 从不 import `llm` 包。
- 嵌入召回:`host/embedder_adapter.py` 把 `llm.embed` 适配为 agent 记忆向量检索,降级为 `EmbeddingUnavailable`。

## 事件流

`platform_eventbus.EventLog`(SQLite `events.db`)是只追加的事实源;`EventBus` 进程内扇出;浏览器经 SSE 订阅。

```text
apps/web                    gateway :8000                     host/agent (单进程)
   │  POST /api/chat/messages   │                                     │
   ├───────────────────────────▶│ publish user.message ──────▶ EventBus
   │                            │                        EventLoop → Master.handle_user_message
   │                            │                        _start_turn → SubagentInstance.run_turn
   │                            │                        ReAct 轮:LLM ⇄ 工具
   │                            │                        发出 agent.step / agent.delta / agent.message
   │  GET /api/chat/stream (SSE)│                                     │
   ◀────────────────────────────├◀── 从日志重放 + 实时扇出 ──────────┘
```

每个持久事实经由同一日志到达模型可见历史与 UI;SSE 端点从 `after_seq` 重放缺失行。事件词表:[eventbus.zh.md](subsystems/eventbus.zh.md)。

## 数据

全部状态位于 `data/` 下:共享存储(`events.db`、`settings.db`、`secrets.db`、`audit.db`、`machine.token`)在 `data/runtime/`,各域与 agent 的 SQLite 存储在 `data/runtime/<domain>/` 与 `data/runtime/agent/`,工作树在 `data/workspace/`。完整清单(含归属模块与保留策略)见 [data-layout.zh.md](catalog/data-layout.zh.md)。

## 运行

- 开发:`uv run python -m host.dev` — uvicorn `host.assemble:build` 于 127.0.0.1:8000,加 Vite 开发服务器于 127.0.0.1:5173(`/api` 代理到 8000)。
- 仅后端:`uv run uvicorn host.assemble:build --factory --port 8000`。
- 仅前端:`apps/web` 内 `npm run dev`。
- 门禁:`npm run gate`(Python 与 web 套件,见 [testing.zh.md](testing.zh.md))。
