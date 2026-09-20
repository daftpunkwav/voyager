# apps/web/ agent rules

Working rules for coding agents in the React app. Stack, routing, state
stores, and the capability bridge are documented in
[docs/web/frontend.md](../../docs/web/frontend.md) and [README.md](README.md);
this file is only the working conventions.

## Commands

```
npm run dev -w web          # Vite dev server (proxies /api to :8000)
npm run test -w web         # vitest run
npm run lint -w web         # eslint src --max-warnings 0
npm run typecheck -w web    # tsc --noEmit
npm run i18n:check -w web   # scripts/check-i18n-keys.mjs
npm run format:check -w web # prettier --check
npm run test:e2e -w web     # Playwright (playwright.config.ts)
```

All of these except `test:e2e` run as part of the root `npm run gate:web`
(typecheck + lint + vitest + i18n check + prettier check); the web gate is
red until every one of them is green. `test:e2e` boots its own server and is
not part of the gate.

## Boundaries

- The app talks to the backend only through the gateway HTTP/SSE surface.
  Request wrappers live in `src/api/` (one module per domain, thin payload
  pass-through), and the SSE/cross-cutting client plumbing lives in
  `src/bridge/`. Pages and components do not hand-roll `fetch` calls to
  endpoints outside these modules.
- Shared TS/eslint config comes from `apps/config/` (`tsconfig.base.json`).

## i18n

- UI copy lives in `src/i18n/resources/` — `zh-CN` is the source locale,
  `en` mirrors it; the two catalogs must stay key-symmetric, enforced by
  `npm run i18n:check`. A new resource namespace must also be registered in
  the bootstrap (`src/i18n/bootstrap.ts`).
- User-visible strings are never inline; new keys go into both locales in the
  same change. Adding a key without its mirror fails the gate.

## Styles

- Global layers live in `src/styles/` (`design-system.css`, per-page files
  under `styles/pages/`). Component styles follow the conventions in the root
  [AGENTS.md](../../AGENTS.md) (toast capsules, no left-edge chrome bars,
  notes list density, danger buttons) — those rules are the reference, not
  suggestions.
- Do not redefine same-name keyframes or selectors in late-loaded stylesheets;
  check `src/styles/` for an existing definition first.

## Tests

- Unit tests live in `tests/unit/` and run under vitest; `tests/setup.ts`
  registers `@testing-library/jest-dom` and forces the React development
  build. Browser APIs that jsdom lacks (e.g. `matchMedia`, `scrollIntoView`)
  are stubbed in the individual test files that need them.
- E2E tests live in `tests/e2e/` under Playwright and need the dev stack
  running.
- TypeScript is strict; a change that weakens a type to make the compiler
  quiet is wrong.
