# platform/eventbus — Event stream

Shape: **a durable event log (SQLite append-only table) + cursor-based subscription**.

- In-process: direct push over asyncio queues (a subscriber that falls behind is flagged `lagged`, and can catch up via its cursor);
- Cross-process: consumers share the same `events.db`, hold a cursor, and poll `read_after` / `read_missed`;
- The log table is at once the **audit backbone and the replay source**: restarts recover from cursors, and any interval can be replayed.

The event stream's own failure is the only "global" failure surface, so its implementation must be maximally conservative: writes hit disk immediately, and the zero-loss subscription promise is upheld by "cursor catch-up" rather than in-memory queues.

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
