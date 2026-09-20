# runtime-data — Runtime data ("its brain")

> Language: **English** | [简体中文](README.zh.md)

Separated from the workspace ("its home"). Contents are user data, **not committed to the repo**.

| Contents | Purpose |
|---|---|
| events.db | Event log (persistence for the event stream) |
| audit.db | Audit |
| memory/ | Agent memory store (four memory kinds) |
| checkpoints/ | Task checkpoints |
| logs/ | Structured logs |
| secrets/ | Local machine secrets (machine.token etc.; platform/actor, platform/secrets) |
