# platform/health — Health probing and unified errors (§7.10)

Goal: **when one service breaks, all the others stay unaffected; and the broken one reports errors that are clear and actionable.**

- `HealthMonitor`: registers each service's probes, probing periodically/on demand; state changes publish
  `service.health.changed` (both the frontend service badges and the agent can perceive it); a probe failure = DOWN;
- `unavailable()` / `queue_full()`: helpers that build the unified error body (`GRAPH.UNAVAILABLE` 503 etc.);
- Process supervision (auto-restart on crash) is handled by desktop/the launcher, not this package; the gateway's periodic probing reuses
  HealthMonitor, with probes = hitting each service's `/health`.

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
