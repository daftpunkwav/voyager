# Frontend (`apps/web`)

English | [中文](frontend.zh.md)

The browser application: React 19 + TypeScript (strict) + Vite 7, talking to the composed backend on port 8000. Source: `apps/web/src/`. An in-tree overview also lives in `apps/web/src/ARCHITECTURE.md`.

## Stack

React 19 (exact-pinned via the root `package.json` `overrides`), `react-router-dom` 7, `zustand` 5 for UI state, `@tanstack/react-query` 5 for server state, `i18next`/`react-i18next`, CodeMirror 6, Mermaid 11, `pdfjs-dist` 6, D3 7, `react-markdown` + rehype/remark + DOMPurify. Tests: Vitest 4 (jsdom) + Playwright.

## Entry and routing

`src/main.tsx` — QueryClientProvider + BrowserRouter + ErrorBoundary, synchronous `initI18n()`, then `ensureSession()` (`src/bridge/session.ts`), then `<App />`.

`src/App.tsx` mounts every route under `AppShell` (`src/shell/AppShell.tsx`); heavy pages are lazy, chat is eager:

- `/`, `/chat` → `ChatPage` (`/chat/:sessionId` redirects to `/chat`)
- `/team`, `/notes`, `/overview`, `/activity`, `/usage`, `/settings`, `/system/health`
- `/sources`, `/sources/{repo,doc,web}/:id`, `/sources/:id`
- `/graph`, `/code-graph`, `/code-graph/:id`
- Legacy redirects (`/projects` → `/sources`, `/agent` → `/chat`) and `*` → `NotFound`

## Backend access

Two channels, both in `src/bridge/`:

- **Capability calls** — `client.ts: callCapability(domain, name, args)` posts to `/api/<domain>/capabilities/<name>` with credentials and an `X-Trace-Id` header; unwraps `{result}` or raises `ServiceError` from `{error: {code, message, hint, trace_id}}`. `src/api/*.ts` are typed wrappers per domain. `uploadFile` posts multipart to `/api/uploads`; `beaconCapability` uses `navigator.sendBeacon`.
- **Event stream** — `stream.ts` holds a singleton `EventSource` on `GET /api/chat/stream?after_seq=<lastSeq>` with `withCredentials`; fnmatch-style `*` pattern subscriptions; manual reconnect with exponential backoff (1 s → 30 s) replaying from the last seq; the connection opens on first subscriber and closes on last unsubscribe. Consumers: `hooks/useChatStream.ts`, `stores/chatStore.ts`, `bridge/events.ts`.

Non-capability endpoints in use: `/api/chat/messages`, `/api/chat/trajectory`, `/api/chat/rawllm`, `/api/activity[/feed]`, `/api/session/bootstrap`, `/api/workspace/{pick,switch}`, `/api/sources/files/doc/:id`, `/api/notes/assets/...`.

## State and layout

`src/stores/` — zustand stores: `auth`, `chat`, `codeGraph`, `floating`, `graph`, `note`, `project`, `settings`, `ui`. `src/hooks/` — per-domain data hooks (`useNotes`, `useGraph`, `useChatStream`, `useSettings`, ...). `src/components/` — domain component trees (`agent`, `settings`, `graph`, `team`, `usage`, `activity`, `code-graph`, `common`); chat widgets live in `src/widgets/chat/`; `src/pages/` holds route pages.

## i18n

`src/i18n/` — single idempotent i18next init (`bootstrap.ts`), flat dotted keys (`keySeparator: false`, namespace separator `:`), `DEFAULT_LOCALE = 'zh-CN'`, supported `['zh-CN', 'en']` plus a `system` choice resolved against `navigator.languages`. Resources: `src/i18n/resources/{en,zh-CN}/` with 15 identical namespaces each. `apps/web/scripts/check-i18n-keys.mjs` enforces key parity (`npm run i18n:check`).

## Floating layers and dialogs

Non-modal anchored popovers (composer dropdowns, session menus, context ring)
render through `components/common/Popover.tsx` — it owns the open/leaving
lifecycle, outside-click/Escape dismissal, and the `.popover-pop` enter/exit
motion (exit is faster than enter); callers own positioning and glass classes.
Modals render through `components/common/ModalOverlay.tsx` (portal, scrim,
symmetric enter/exit); it also tracks a module-level open stack so Escape only
closes the topmost modal and raises `uiStore.modalDepth` while open. Confirm
actions go through the imperative `confirmDialog()` (`stores/uiStore.ts`) —
rendered by the shell-mounted `ConfirmDialogHost`; `window.confirm` is never
used. Workspace hot-switching must go through `bridge/workspaceSwitch.ts` so
the request marker is stashed before the POST.

## Settings page

`src/pages/settings/SettingsPage.tsx` — one page, 17 sections in three nav groups: basic (`general`, `appearance`, `llm`), agent capabilities (`agents`, `agentLlm`, `subagents`, `plugins`, `mcp`, `skills`, `commands`, `tools`, `toolPerms`), data & system (`health`, `usage`, `activity`, `data`, `about`). Blocks compose from `src/components/settings/`.

## Build and dev

`vite.config.ts` — alias `@` → `./src`; dev server `127.0.0.1:5173` (`VITE_PORT`, `strictPort`); `/api` and `/health` proxy to `VITE_API_TARGET` (default `http://127.0.0.1:8000`); brand strings injected from repo-root `brand.json`; pdf.js assets copied to `/pdfjs/`; vendor chunks for three/mermaid/pdfjs/codemirror/d3; dev CSP injected as a header. `npm run build` = `tsc --noEmit && vite build` into `dist/`; `npm run preview` serves the build. The gateway does not serve the SPA; production serving is an external static server or reverse proxy.
