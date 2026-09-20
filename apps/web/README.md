# apps/web/ — React main application

The single frontend application: a React 19 + TypeScript + Vite single-page app that talks to the backend gateway only (REST/SSE under `/api`, plus `/health`). The entry point is `src/main.tsx`, which mounts `src/App.tsx` with the theme and locale bridges, an error boundary, a React Query client and the router. Brand strings are injected at build time from the repository-root `brand.json` (see `vite.config.ts`).

## Commands

Run from this directory with `npm run <script>`, or from the repository root via the `-w web` aliases shown in parentheses. Requires Node >= 20.11.

| Script | Alias (repo root) | What it does |
| --- | --- | --- |
| `dev` | `dev:web` | Vite dev server on `127.0.0.1:5173` (`VITE_PORT`, strict port); proxies `/api` and `/health` to `VITE_API_TARGET` (default `http://127.0.0.1:8000`). Port and proxy live in `vite.config.ts`. |
| `build` | `build:web` | `tsc --noEmit` type check followed by `vite build` into `dist/`. |
| `preview` | `preview:web` | Serve the production build locally. |
| `test` | `test:web` | Vitest unit tests from `tests/unit` (jsdom environment, setup file `tests/setup.ts`). Variants: `test:watch`, `test:coverage`. |
| `test:e2e` | — | Playwright specs from `tests/e2e`; `playwright.config.ts` boots its own dev server on port `5193` (`E2E_PORT`). |
| `lint` | `lint:web` | ESLint over `src/` with `--max-warnings 0` (flat config in `eslint.config.js`). |
| `typecheck` | `typecheck:web` | `tsc --noEmit` against the tsconfig that extends `../config/tsconfig.base.json`. |
| `i18n:check` | `i18n:web` | i18n key consistency check (`scripts/check-i18n-keys.mjs`). |
| `format` / `format:check` | `format:web` (check) | Prettier write / check over the package. |

## Layout (`src/`)

```
src/
├── api/          # Per-domain HTTP API modules (agent, auth, codeGraph, graph, llm, notes,
│                 #   overview, projects, settings, sources, usage, workspace) plus shared
│                 #   response types (types/, types.ts)
├── bridge/       # Cross-page contracts and domain bridges injected by App into pages
│                 #   (chatSend, session, events stream, activity/feed, quotaGuard, pageContext)
├── components/   # Shared UI grouped by domain/feature (activity, agent, code-graph, graph,
│                 #   graph-viz, common, icons, project, settings, team, usage)
├── constants/    # Shared constant tables (agentCatalog, personas, glassTokens, llmConfig,
│                 #   usageChartColors)
├── hooks/        # Per-domain React hooks (useChatSend, useNotes, useGraph, useSettings, ...)
├── i18n/         # i18next setup (bootstrap/config/catalog/format) with en and zh-CN resources
├── lib/          # code-runner/: in-browser JavaScript, TypeScript and Python runners with a registry
├── pages/        # One directory per routed page (activity, chat, code-graph, graph, health,
│                 #   notes, overview, settings, sources, team, usage); pages never import each other
├── shell/        # App shell chrome (AppShell, Sidebar, ServiceBadge, Degraded, NotFound),
│                 #   theme/locale bridges, pageProbes
├── stores/       # Zustand stores (auth, chat, codeGraph, floating, graph, note, project,
│                 #   settings, ui)
├── styles/       # Global and design-system CSS (design-system.css, global.css, shell.css,
│                 #   liquid-glass.css, glass-select.css, per-page styles)
├── utils/        # Pure helpers (cn, date, format, errors, errorCodes, markdownNodes, ...)
├── widgets/      # Cross-page widgets (FloatingChat, PageProbe, chat/ components)
├── App.tsx       # Root component: wires bridges into the shell and routes
├── main.tsx      # Application entry point
└── ARCHITECTURE.md
```

`tests/` mirrors this split: `tests/unit/` holds Vitest specs (`.test.ts`/`.test.tsx`) and `tests/e2e/` holds Playwright specs; `tests/setup.ts` registers `@testing-library/jest-dom` and forces the React development build for `act()` support.

## Notes

- Detailed frontend documentation: [docs/web/frontend.md](../../docs/web/frontend.md).
- Working rules for this directory: [AGENTS.md](AGENTS.md).
- Install and run instructions: repository-root [README.md](../../README.md).
