# browser — browser domain implementation

Implementation of the browser domain: a capability registry that dispatches five browser commands to an external browser host, plus session bookkeeping and the REST / MCP entry points. Package-level contract (tools, configuration, limitations) lives in [packages/browser/README.md](../../README.md); the domain is covered in [docs/subsystems/auxiliary-domains.md](../../../../docs/subsystems/auxiliary-domains.md#browser-domain). This README is only a map of the files in this directory.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring (capability registry, REST entry point, MCP server). |
| `capabilities.py` | Capability registry exposing `navigate` / `click` / `type` / `read` / `screenshot`; touches session metadata on every command and passes settings (headless mode, allowed domains) to the host adapter — plus the workspace directory on `screenshot`. |
| `host.py` | Host adapter: validates commands (domain allowlist on `navigate`, `FORBIDDEN` otherwise) and returns a uniform `BrowserResult`; a skeleton that records calls and returns placeholder results — the docstring places the real browser in an external `desktop/browser-host` process. |
| `settings.py` | `browser.*` setting definitions: `browser.headless` (default true) and `browser.allowed_domains` (empty = inherit agent network permissions). |
| `store.py` | `BrowserStore`: SQLite `sessions` table holding session metadata only (id, url, timestamps) for debugging and auditing, not business data. |
| `wiring.py` | `wire(data_dir, workspace, ...) -> Wiring` shared by standalone and aggregate deployment: registers `DEFS`, creates the store, injects `Deps`, returns registry / probe / close handles. |
| `rest.py` | Thin FastAPI shell; run standalone with `uvicorn browser.rest:app_factory --factory --port 8060`. |
| `mcp_server.py` | Stdio MCP entry point: `python -m browser.mcp_server` builds the server from `wire().registry`. |

## Notes

- `host.py` is the seam for the external browser host; everything else in the package is protocol and bookkeeping around it (`capabilities.py` / `host.py` docstrings).
- Package-level enablement (default-off) is described in [packages/browser/README.md](../../README.md).
