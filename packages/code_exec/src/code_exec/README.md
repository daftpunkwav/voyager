# code_exec — code execution domain implementation

Implementation of the code-exec domain: one-shot snippet/file execution in docker-first runtimes (python / node / shell) with an explicit host fallback, returning `JobRef`s and streaming results over events. Package-level contract (tools, configuration, limitations) lives in [packages/code_exec/README.md](../../README.md); the domain is covered in [docs/subsystems/auxiliary-domains.md](../../../../docs/subsystems/auxiliary-domains.md#code_exec-domain). This README is only a map of the files in this directory.

## Files

| File | Responsibility |
| --- | --- |
| `__init__.py` | Package docstring only. |
| `capabilities.py` | Capability registry: `run_snippet` / `run_file` kick off one-shot executions as fire-and-forget background tasks and return a `JobRef` immediately (`run_file` accepts only paths under `workspace/sandbox/`); `list_runtimes` reports the configured runtimes; streams `task.*` events and persists execution rows. |
| `executor.py` | `run_in_runtime`: one-shot docker container when available (artifact directory mounted at `/workspace`, timeout / memory / network switch applied, image / command-token / file-extension whitelist validation before execution); restricted host subprocess fallback limited to known interpreters (`python` / `node` / `bash`). |
| `settings.py` | `code_exec.*` setting definitions: `code_exec.runtimes` (JSON runtime table, defaults python:3.11-slim / node:20-slim / bash:5.2), `code_exec.timeout_seconds`, `code_exec.memory_mb`, `code_exec.network`, `code_exec.use_host`. |
| `store.py` | `ExecutionStore`: SQLite `executions` table (runtime, kind, status, exit_code, stdout, stderr, artifact_dir); results themselves travel over the event stream, artifact files land under `workspace/sandbox/artifacts/<job_id>/`. |
| `wiring.py` | `wire(data_dir, workspace, ...) -> Wiring` shared by standalone (`rest.py`) and aggregate (`packages/host/`) runs: registers `DEFS`, creates the store, injects `Deps`. |
| `rest.py` | Thin FastAPI shell; run standalone with `uvicorn code_exec.rest:app_factory --factory --port 8050`. |
| `mcp_server.py` | Stdio MCP entry point: `python -m code_exec.mcp_server` builds the server from `wire().registry`. |

## Notes

- Language environments are data: adding a runtime only changes the `code_exec.runtimes` setting, not code (`settings.py` docstring); host fallback runtimes are hardcoded in `executor.py`'s `_HOST_INTERPRETERS`.
- Executions are one-shot with no persisted environment state (`capabilities.py`).
