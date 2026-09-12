# Voyager

A local-first agent companion workbench: import repos / documents / web pages, take notes, build knowledge graphs — humans and agents drive the same capability layer.

Personas: a resident orchestrator (display name Lucien) plus 4 presets (recon / explainer / organizer / graph guide). Brand strings live only in the repo-root `brand.json`.

**Stack:** FastAPI + sqlite3 / React + TypeScript + Vite. The default monolithic assembly (`packages/host/`) runs gateway + domain packages + agent in a single process; the graph C engine can also run as a sidecar.

## Quick start

```bash
uv sync        # Python dependencies (uv workspace)
npm install    # Node dependencies (npm workspaces)
```

Set `SECRETS_ENCRYPTION_KEY` or `SECRET_KEY` (a long random string — do not reuse the sample values from `.env.example`) before starting; enter the LLM API key on the settings page (BYOK). Without a key, chat degrades gracefully while sources / notes / graph stay usable.

### Development

```bash
uv run python -m host.dev    # gateway :8000 + Vite :5173
```

Quality gates run locally: `npm run gate` (`gate:py` = ruff format/check, import-linter layering contracts, mypy, pytest; `gate:web` = tsc, eslint, vitest, i18n key checks, prettier).

## Ports

| Service                | Default port | Override             |
| ---------------------- | ------------ | -------------------- |
| Web (Vite dev)         | 5173         | `VITE_PORT`          |
| gateway (uvicorn)      | 8000         | —                    |
| Graph C engine sidecar | 8123 / 9750  | see service settings |

The full environment variable list is in `.env.example`.

## Repository layout

Three source roots (product code only recognizes these three trees): `agent/` · `apps/` · `packages/`.

```
├── agent/             # ① Source root: AI orchestration layer (zero imports of domain
│                      #    implementations; src/agent/ + tests/)
├── apps/              # ② Source root: frontend (npm workspaces: apps/*)
│   ├── web/           # React main app (talks to gateway only)
│   └── config/        # shared TS/eslint config
├── packages/          # ③ Source root: backend modules (uv members; each package is
│                      #    src/<name>/ + tests/)
│   ├── platform/      # cross-cutting mechanisms (contracts / capability / eventbus / …)
│   ├── gateway/       # aggregated REST/SSE shell
│   ├── notes|sources|graph|llm|settings|office|browser|code_exec/
│   └── host/          # assembly root: discovers service.json to wire in domains
├── plugins/           # declarative user plugins (plugin.json; no hot execution)
├── data/              # local data root (gitignored)
│   ├── workspace/     # "home": clones, books, exports, sandbox
│   └── runtime/       # "brain": events/audit/memory/checkpoints
└── brand.json         # single source of brand strings
```

Each package documents its contract in its own `README.md` (purpose / config / extension points / tool surface / limits / deferred), starting from [packages/README.md](packages/README.md).

> **Product surface**: the `packages/office / browser / code_exec` domains are implemented
> and runnable standalone (each ships rest.py / mcp_server.py), but their module cards are
> `enabled_by_default=false`, the default monolithic assembly does not mount them, and the
> product UI does not include them yet. Enable explicitly via settings or the
> `ENABLE_DOMAINS` environment variable.
>
> **Local-only**: no external network dependency by default; LLM access is BYOK or a
> local OpenAI-compatible endpoint, and the agent degrades when no model is available.

Engineering conventions: see [AGENTS.md](AGENTS.md).
