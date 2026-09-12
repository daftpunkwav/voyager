# platform/health — 健康探测与统一错误(§7.10)

目标:**一个服务出问题,其他全部不受影响;出问题的那一个,报错清楚、可行动。**

- `HealthMonitor`:注册各服务探针,周期/按需探测;状态变化发布
  `service.health.changed`(前端服务徽章、agent 都能感知);探针异常 = DOWN;
- `unavailable()` / `queue_full()`:构造统一错误体的助手(`GRAPH.UNAVAILABLE` 503 等);
- 进程监督(崩溃自动拉起)由 desktop/启动器兼任,不在本包;gateway 的周期探测复用
  HealthMonitor,探针 = 打各服务 `/health`。

---

## Purpose

Health monitoring: domain probes aggregated into one /health view; errors vocabulary.

## Configuration

None.

## Extension Points

Probe functions come from each domain's wiring (probe=lambda).

## Known Limitations

Probes are shallow (status only).

## Deferred Work

Deep checks with timeouts per probe.
