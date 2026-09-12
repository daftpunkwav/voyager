# runtime-data — Runtime data ("its brain", §5)

Separated from the workspace ("its home"). Contents are user data, **not committed to the repo**.

| Contents | Purpose |
|---|---|
| events.db | Event log (persistence for the event stream, §7.2) |
| audit.db | Audit (§7.6) |
| memory/ | Agent memory store (four memory kinds, §9.11) |
| checkpoints/ | Task checkpoints (§9.17) |
| logs/ | Structured logs (§7.8) |
| secrets/ | Local machine secrets (machine.token etc.; platform/actor, platform/secrets) |
