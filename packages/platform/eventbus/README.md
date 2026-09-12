# platform/eventbus — 事件流

形态:**持久化事件日志(SQLite 追加表)+ 游标订阅**(§7.2)。

- 进程内:asyncio 队列直推(订阅者掉队标记 `lagged`,可经游标补读);
- 跨进程:共享同一 `events.db`,消费方持游标轮询 `read_after` / `read_missed`;
- 日志表同时是**审计主线与重放源**:重启从游标恢复,可重放任意区间。

事件流自身故障是唯一"全局性"故障面,实现必须最保守:写入即落盘,订阅零丢失承诺
由"游标补读"而非内存队列保证。

---

## Purpose

Durable event bus: append-only EventLog (sqlite), pub/sub Subscription queues, cursor storage for catch-up replays.

## Configuration

None (paths injected by the composition root).

## Extension Points

New read pattern = a method on EventLog (bounded, locked); never read the DB directly.

## Known Limitations

Model-agnostic infrastructure; single sqlite file, retention/pruning is manual.

## Deferred Work

Segmented log files for cheaper retention.
