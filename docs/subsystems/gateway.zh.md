# Gateway

[English](gateway.md) | 中文

`gateway` 域是唯一的 HTTP 载体。它不 import 任何域;域以挂载路由的形式进入。组合进程中,host 构建一个 gateway 应用,把所有域服务在 8000 端口的 `/api/<domain>` 之下;独立运行时,`uvicorn gateway.rest:app_factory --factory --port 8000` 使用自己的默认库(`packages/gateway/data/events.db`)。

源码:`packages/gateway/src/gateway/`

## 应用

`rest.py` — `create_app(mounts, db_path, bus, lifespan, issuer, auth, quota, audit, rate_limit_per_minute=600, sse_max_connections=8, ...)`:

- 安全头中间件:CSP 镜像前端 `index.html` 的 meta CSP(`frame-ancestors 'none'`、`script-src 'self' 'unsafe-eval' blob:`、`worker-src 'self' blob:`)、`X-Content-Type-Options: nosniff`。
- actor 中间件:`platform_actor.resolve_http_actor` 解析 Bearer/cookie 调用方;未认证的回环请求按 `LOCAL_USER` 处理;未认证的非回环请求得到 401。
- `ServiceError` 处理器渲染 `ErrorEnvelope`(`{error: {code, message, hint, trace_id}}`)。

## 挂载的路由

| 路由 | 端点 | 说明 |
|---|---|---|
| `mounts.py` | `GET /api/<domain>/capabilities`、`POST /api/<domain>/capabilities/{name}` | 每个域 registry 一个 `MountSpec`(`build_router`) |
| `chat.py` | `POST /api/chat/messages`、`GET /api/chat/messages`、`GET /api/chat/trajectory`、`GET /api/chat/rawllm`、`GET /api/chat/stream` | 历史分页接受 `before_seq`/`after_seq`/`session`;SSE 支持 `after_seq` 续传、积压重放(`once=true`)、保活注释帧与 `_STREAM_TYPES` 过滤 |
| `session.py` | `GET /api/session/bootstrap` | 仅回环可用的 HttpOnly 会话 cookie,30 天 TTL |
| `activity.py` | `POST /api/activity`、`GET /api/activity/feed` | 类型 `page_view`/`pointer`/`selection`/`manual` → 发布 `user.activity`;feed 支持 `types`(fnmatch)与 `agent`/`session`(按 `payload.session` 归属过滤,agent 回合内产生的事件才携带) |
| `uploads.py` | `POST /api/uploads` | multipart,上限 1 GiB,落在 `workspace/imports/` |
| `workspace.py` | `GET /api/workspace/list`、`GET /api/workspace/read`、`GET /api/workspace/pick` | `read` 预览上限 256 KiB / 400 行;`pick` 只读浏览任意目录 |
| `health.py` | `GET /health` | 聚合各 `HealthProbe` |

host 在其上追加额外路由(`build_upload_router`、`build_workspace_router`、`build_switch_router`、jobs 路由),并把 agent registry 挂载为 `MountSpec(domain="agent", ...)`。

## 限流与 SSE 容量

`ratelimit.py` — 按调用方键控的内存 `RateLimiter`,上限 `gateway.rate_limit.per_minute`(仅单实例)。SSE 容量由 `gateway.sse.max_connections` 封顶。

## 面向 agent 的面 parity

gateway 是 `agent/src/agent/parity.py` 所钉 parity 契约的人类侧:REST 可达的每个能力都可由同名 `<domain>__<capability>` 的 agent 工具调用,host 的 parity 测试保持两侧一致。
