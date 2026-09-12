# Frontend Architecture (apps/web)

> Aligned with `docs-local/design/architecture.md` §2.1 / §10.1 / §12. This file records the **current implementation**
> (as-is state after the 2026-09 review); for structure and rules, this file + `eslint.config.js` are authoritative.

## 1. Layering and Shared Artifacts (§10.1 Iron Rule 1, frontend implementation)

| Layer             | Path                                              | Responsibility                                                                                                                                                                                                                                                                                             |
| ----------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **bridge**        | `src/bridge/`                                     | The only layer that talks to the backend: callCapability, uploads, sendBeacon fallback, chat history/online/activity replay/health probes, SSE subscriptions. Pages and hooks **must not** call fetch directly                                                                                             |
| contracts(TS)     | `src/api/types/`                                  | TS mirror of the backend DTOs (split into 10 files by domain + `types.ts` barrel re-export). Note: for now a manual mirror of `platform/contracts`, reconciled via contract tests; the generation pipeline does not exist yet (known gap)                                                                  |
| Base UI           | `src/components/common/`, `src/components/icons/` | Cross-domain generic UI (Toast/GlassCard/EmptyState/MarkdownRenderer, etc.) and icons                                                                                                                                                                                                                      |
| Domain components | `src/components/<domain>/`                        | Single-domain business components (project=settings/sources domain, settings, usage, graph, code-graph, agent). Consumed by a single page by default; when genuinely needed across pages, keep them in this layer and register them here; pushing them down into pages that import each other is forbidden |
| Page shell        | `src/pages/<domain>/`                             | Page assembly (provider + Page component + domain-internal slices); pages do not import each other                                                                                                                                                                                                         |
| App shell         | `src/shell/`                                      | AppShell + Sidebar/Topbar + route probes + global mount points; domain side effects are injected by `App.tsx` via `bridges`; the shell does not import page-private modules                                                                                                                                |

**Mandatory rules** (codified as four ESLint `no-restricted-imports` blocks in `eslint.config.js`):

- Pages do not import each other (`@/pages/*` is banned outright); sharing goes only through bridge / contracts / base UI / the domain components layer;
- Shared layers (components/common, hooks, stores) must not import page modules;
- Non-chat pages must not touch `@/stores/chatStore` / `@/stores/floatingStore` directly; cross-domain interaction goes through the `bridge/chatSend` contract (sendUserTurn / openFloatingChat / markChatInterrupted / chatSystemNote).

## 2. Directory Structure (as-is)

```
apps/web/src/
├── api/                # per-domain thin data layer + types
│   ├── <domain>.ts     # projects/sources/notes/graph/auth/settings/overview/usage:
│   │                   #   call callCapability directly, return payload directly (no envelope); shape normalization lives in this layer
│   ├── types.ts        # barrel re-export → types/
│   └── types/          # 10 files by domain: agent/codeGraph/common/graph/llm/notes/settings/sources/system/usage
│
├── bridge/             # ★ the only layer that talks to the backend
│   ├── client.ts       # callCapability<T> + uploadFile + beaconCapability (unload fallback) + unwrapDataField (migration period)
│   ├── chatSend.ts     # send messages / chat history / online events + cross-domain chat contract (sendUserTurn, etc.)
│   ├── stream.ts       # shared SSE (resumes from after_seq after disconnects)
│   ├── session.ts      # loopback bootstrap + /health liveness probe
│   ├── activity.ts     # behavior reporting (privacy hard switch) + activity replay
│   └── feed.ts / events.ts / pageContext.ts / quotaGuard.ts
│
├── components/         # Base UI + domain components layer (see §1)
│   ├── common/  icons/
│   ├── project/        # sources domain components (project table/import/category tags/AI panel)
│   ├── settings/       # settings domain components (with agent/ llm/ subdirectories)
│   ├── usage/ graph/ code-graph/ graph-viz/ agent/
│
├── hooks/              # data hooks (via the api/<domain> thin layer; one file per domain)
├── constants/          # cross-domain read-only constants (personas, LLM config)
│
├── pages/              # ★ pages as modules: activity chat code-graph graph health notes overview settings sources team usage
│   └── notes/          # example: Page + provider + notesAutoSave/notesBatch/notesSplit* and other domain-internal slices
│
├── shell/              # app shell: AppShell, Sidebar/Topbar, ServiceBadge, pageProbes, themeBridge
├── stores/             # zustand (0 cross-imports): auth chat codeGraph floating graph note project settings ui
├── styles/             # design-system.css as the single source + shell/global + pages/ page-private CSS
├── utils/              # cross-domain pure functions (one file, one responsibility; errorCodes aligned with the backend ErrorSuffix, locked by contract tests)
├── widgets/            # FloatingChat, PageProbe, chat/ (floating window view group)
├── App.tsx             # route table
└── main.tsx            # entry point
```

## 3. Data Access Status (legacyApi retired as of 2026-09)

- Data access chain: `hooks/components → api/<domain>.ts (per-domain thin layer, direct payload return) → bridge/client.callCapability → gateway`;
  the change surface for adding one capability = backend capability + one function in api/<domain> + call sites,
  with no intermediate registry;
- `bridge/legacyApi.ts` and `api/client.ts` (the getApi facade) have been deleted in full: the 97-method facade,
  the 38-entry METHOD_MAP dispatch table, the `{data}` envelope, and the IApiClient compatibility alias no longer exist;
  `bridge/client.unwrapDataField` is a migration-period equivalent value-extraction helper (passes results through
  when they already carry a data key), to be retired domain by domain as each capability's shape is verified;
- Exception: the settings form domain (settings/* components) calls callCapability directly to read and write setting
  keys — an established pattern, not a bypass; cross-domain chat interaction always goes through the `bridge/chatSend`
  contract (enforced by ESLint);
- The error envelope `{"error":{code,message,hint,trace_id}}` is uniformly unwrapped in bridge/client into
  `ServiceError`; single source for error-code display text: `utils/errorCodes.ts` (suffix-matched against the
  backend ErrorSuffix, contract locked by `tests/unit/errorCodes.test.ts`).

## 4. Domain Boundary Notes

- **"graph" spans two domains**: `pages/graph` = resource relationship graph (L0); `pages/code-graph` = code graph (L1).
  `components/graph/` holds the graph visualization components shared by both domains (ForceGraph, etc.); new domain
  components go into their domain directory first and are promoted only when genuinely needed across domains —
  do not sink them early for the sake of "reuse".
- `components/agent/EmbedAgentChat` is exported through a two-line stub at `widgets/EmbedAgentChat`:
  the domain-component export pattern; other domains must not bypass the stub to import components/agent directly.

## 5. Engineering Commands and Known Status

- Tests: `npm run test:web` (vitest, tests/unit; jsdom stubs matchMedia/scrollIntoView);
- Types: `npm run typecheck:web`; lint: `npm run lint:web` (strict `--max-warnings 0`,
  fully green since 2026-09; new code must keep 0 warnings).
