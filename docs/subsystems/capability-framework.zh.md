# 能力框架

[English](capability-framework.md) | 中文

`platform_capability` 把一个注册函数变成三个协同的面:进程内可调用对象、REST 端点、MCP 工具。每个域都基于它构建;agent 自身的能力 registry 也用同一框架。

源码:`packages/platform/capability/src/platform_capability/`

## `Capability` — 服务单元

```python
# define.py
@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    handler: Callable
    input_model: type          # Pydantic/dataclass 输入 schema
    cost: int = 1
    reversible: bool = True
    write: bool = True
    scopes: frozenset = frozenset()
    long_running: bool = False
    streaming: bool = False
    dimension: str = "app"     # app | network | ...
```

`dimension` 驱动策略:agent 调用 `dimension="network"` 的能力要过网络策略门,`dimension="fs"` 过文件系统门。`write`/`reversible` 供 agent 权限的工具分类使用。`long_running=True` 标记入队后台工作并返回 `JobRef` 的能力。

## Registry 与注册

`registry.py` — `Registry(domain)` 持有域的能力,提供 `register`/`get`/`names`/`all`/`merge`;重名抛 `ServiceError(CONFLICT)`。`@capability(registry, name=..., description=..., ...)` 装饰器(`define.py`)注册被装饰函数,并从其 Pydantic 模型或 dataclass 推导输入 schema。

各域通常按关注点模块声明多个 registry 再合并(`sources`:`repo`/`doc`/`web`;`office`:`doc`/`slides`;`notes`:`batch`/`catalog`/`history`/`lifecycle`/`transfer`/`view`)。

## REST 生成

`gen_rest.py` — `build_router(registry, issuer, auth, quota, audit)` 为每个 registry 产出两条路由,由 host 挂载到 `/api/<domain>`:

- `GET /capabilities` — 含输入 schema 的清单。
- `POST /capabilities/{name}` — 调用;返回 `{"result": ...}` 或 `ErrorEnvelope`。

各域的 `rest.py` 把 `build_router` 包进 `create_app()` 供独立运行(`uvicorn <domain>.rest:app_factory --factory --port <port>`)。

## MCP 生成

`gen_mcp.py` — `build_server` 经 MCP stdio 暴露 registry(`python -m <domain>.mcp_server`);`build_tool_specs` 与 `dataclass_to_json_schema` 把能力输入模型转换为 MCP 工具 schema。

## 守卫链

`guards.py` — `execute()` 让每次调用都穿过同一条链,与调用方无关:

1. **认证** — 注入的认证器解析 `ActorContext`(REST:`platform_actor.resolve_http_actor`;进程内调用显式携带 actor)。
2. **配额** — `CostQuota` 执行每日 token 预算(每次调用计 `cost`)。
3. **校验** — 输入模型校验载荷。
4. **处理器** — 能力函数执行。
5. **审计** — `AuditSink` 记录本次调用。

`LocalAuth` 是独立运行时的直通认证器。`CallRequest` 是进程内调用载体(`actor`、`name`、`args`)。

## 审计 sink

`guards.py` + `audit_db.py` — `AuditSink` 是协议;`InMemoryAuditSink` 用于测试,`SqliteAuditSink`(`audit.db`)用于组合运行。host 向每个 registry 注入一个共享 sink。

## Wiring

`wiring.py` — `Wiring(registry, probe, start, stop, close, extra_router)` 是域的 `wire()` 交给 host 的产物:待挂载的 registry、健康 `probe`、生命周期钩子(`start`/`stop`/`close`,用于 worker 与存储)、以及可选的 `extra_router` 承载非能力端点(如 notes 附件、sources 文件预览)。
