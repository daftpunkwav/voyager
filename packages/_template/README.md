# packages/_template — New domain service scaffold

Copy this directory and you have a new service (acceptance criterion: no other directory is touched):

1. `cp -r packages/_template packages/<domain>`, rename `src/_template/` to
   `src/<domain>/`, and globally replace `_template` / `template` with `<domain>`
   (`name` and `packages = ["src/<domain>"]` in pyproject, `name` in
   `service.json`, imports in tests);
2. Add `packages/<domain>` to `tool.uv.workspace.members` in the root `pyproject.toml`,
   register it in `dependencies` and `tool.uv.sources` too, then run `uv sync`;
3. Register this domain's capabilities in `src/<domain>/capabilities.py` (minimal initial set; the full list goes into
   this package's README);
4. Long tasks: the handler only enqueues and returns a `JobRef`; progress goes through the event stream — see the `worker.py` example;
5. The port is declared in `service.json` and registered with the gateway (port table in packages/README.md).

Layout (src layout):

```
packages/<domain>/
├── pyproject.toml      # hatchling; dependencies declare platform-* only
├── service.json        # module card
├── README.md
├── src/<domain>/       # six-piece set: capabilities / rest / mcp_server / worker / store / settings
└── tests/              # flat, no __init__.py
```

---

## Purpose

Seven-piece domain template: capabilities/wiring/rest/mcp_server/store/settings/worker — copy it, rename, and the composition root discovers the domain with zero host changes.

## Configuration

service.json card + module settings.py defs.

## Extension Points

This IS the extension point for new domains.

## Known Limitations

Deliberately minimal: no migrations/worker examples beyond a stub.

## Deferred Work

A generator script (copy + rename in one command).
