# Auxiliary domains

English | [中文](auxiliary-domains.zh.md)

Four small domains complete the set: `settings` (user-facing settings), `browser` (browser control, currently a skeleton adapter), `code_exec` (sandboxed code execution), and `office` (block-based docs and slides).

## settings domain

Source: `packages/settings/src/settings/` — port 8080, enabled by default. Distinct from the framework package `platform_settings`.

Capabilities: `list_themes`, `get_theme`, `set_theme`, `get_settings` (the aggregated schema of every registered module, filterable by `module`), `get_setting` (secret items return `has_value` only), `set_setting` (writes to secret items are refused by `platform_settings.SettingsStore`).

Owns the appearance and privacy keys: `appearance.theme` (`dark`/`light`/`system`), `appearance.locale` (`zh-CN`/`en`/`system`), `appearance.font_scale`, `appearance.code_font`, `privacy.activity_report`. No own storage in the composed process — `wire()` registers its `DEFS` on the shared `SettingsStore`; standalone it creates `SettingsStore(<data_dir>/settings.db)`.

## browser domain

Source: `packages/browser/src/browser/` — port 8060, **disabled by default**. Store `data/runtime/browser/browser.db` (a `sessions` metadata table only).

Capabilities: `navigate`, `click`, `type`, `read`, `screenshot`, each returning a `BrowserResult` (`ok`, `url`, `title`, `text`, `screenshot_path`, `error`). `navigate` enforces the `browser.allowed_domains` suffix/equality match on the netloc, else `ServiceError(FORBIDDEN)`.

`host.py` is a placeholder adapter: all five functions currently return placeholder results; the docstring states the real browser runs in an external browser host and the IPC is pending. Settings: `browser.allowed_domains`, `browser.headless`.

## code_exec domain

Source: `packages/code_exec/src/code_exec/` — port 8050, **disabled by default**. Store `data/runtime/code_exec/code-exec.db` (an `executions` table).

Capabilities: `list_runtimes`; `run_snippet(runtime, code)` and `run_file(runtime, file_path)` — both `long_running=True`: they spawn background work and return a `JobRef` immediately. `run_file` rejects paths escaping `workspace/sandbox/`.

`executor.py` — `run_in_runtime(...)`: writes the snippet to `workspace/sandbox/artifacts/<exec_id>/`, then runs one-shot `docker run --rm --network none -m <memory> -v <artifact_dir>:/workspace` with whitelist-validated image/cmd/extension; without Docker, a host-process fallback exists only for `python`/`node`/`bash` and emits a warning. Streams are capped at 1 MiB each; timeout kills and reaps. Emits `task.progress`/`task.completed`/`task.failed`.

Settings: `code_exec.runtimes` (JSON list of `{id, image, cmd, file_ext}`), `code_exec.timeout_seconds`, `code_exec.memory_mb`, `code_exec.network`, `code_exec.use_host`.

## office domain

Source: `packages/office/src/office/` — port 8040, **disabled by default**. Store `data/runtime/office/office.db` (one `documents` table for both kinds).

Capabilities merge two sub-registries: doc (`create_doc`, `get_doc`, `update_doc`, `insert_block`, `delete_doc`) and slides (`create_deck`, `get_deck`, `update_deck`, `add_slide`, `delete_deck`). Documents are block arrays (`kind='doc'|'slides'`, `blocks` JSON). Publishes `doc.created`, `doc.edited`. Setting: `office.export.dir`.
