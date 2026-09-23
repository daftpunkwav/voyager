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
  under `styles/pages/`). Component style conventions:
  - Toast: the `.toast-container` handles horizontal centering (`left: 50%`
    - `translateX(-50%)`); capsules animate vertical translate / opacity
      only — never apply a `translateX` to a capsule that omits the horizontal
      centering, and never redefine same-name `toast-in` / `toast-out`
      keyframes in late-loaded styles (the first frame sits off-center then
      snaps back). Semantic color goes only through the 4px left color bar
      (error red / warning orange / success green / info blue).
  - Chrome (cards / buttons / nav) must not use a left brand-color vertical
    bar (`::before` / inset left edge / glass `::after` highlight) to mark
    selected / active / pinned state; pinned items use a top-right pin icon,
    nav active state uses background and text color. A blockquote's left
    border belongs to content typography, not chrome.
  - Notes list: card view stays equal-height at a given density
    (`--notes-card-h` + `overflow: hidden`); density switches via CSS
    variables and the main column keeps `scrollbar-gutter: stable`; the
    batch action bar enters / exits by animating height + opacity.
  - Danger buttons: `.is-danger` must override the generic button `color`
    in the dark theme with `var(--error)`.
  - Anchored popovers (dropdowns, session menus, info panels) go through
    `components/common/Popover.tsx` (outside-click/Escape/leaving built in);
    never hand-roll an open-state effect. Modals go through
    `components/common/ModalOverlay.tsx` — it owns the Escape topmost-modal
    rule, so never add a second window-level Escape listener for a dialog.
  - Confirm actions use the imperative `confirmDialog()` from `stores/uiStore`
    (answered by the shell-mounted `ConfirmDialogHost`, `danger: true` for
    destructive ones); `window.confirm` is banned.
  - Motion baseline: enter 150-250ms `--ease-apple`/`--ease-out`, exit faster
    than enter, transitions on specific properties only, `:active` scale
    (0.95-0.98) on pressable elements, `@media (prefers-reduced-motion)`
    respected (the global rule shortens durations, it does not disable them).
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
- Tests that need to answer the global confirm use
  `tests/unit/helpers/stubConfirm.ts` instead of stubbing `window.confirm`.
