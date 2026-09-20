# platform/health — 健康探测与统一错误

> 语言：简体中文 | [English](README.md)

目标：**一个服务挂掉，其余服务不受影响；挂掉的那个所报的错误清晰且可行动。**

- `HealthMonitor`：登记各服务的探针，周期性/按需探测；状态变化发布
  `service.health.changed`（前端服务徽标与 agent 均可感知）；探针失败 = DOWN；
- `unavailable()` / `queue_full()`：构造统一错误体的辅助函数（`GRAPH.UNAVAILABLE` 503 等）；
- 进程守护（崩溃后自动重启）由 desktop/启动器负责，不在本包；gateway 的周期探测复用
  HealthMonitor，探针 = 请求各服务的 `/health`。

---

## 用途

健康监控：各 domain 的探针聚合为一个 /health 视图；错误词汇表。

## 配置

无。

## 扩展点

探针函数来自各 domain 的 wiring（probe=lambda）。

## 已知限制

探针是浅层的（仅状态）。

## 暂缓事项

逐探针带超时的深度检查。
