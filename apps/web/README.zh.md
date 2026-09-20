# apps/web/ — React 主应用

> 语言：简体中文 | [English](README.md)

唯一的前端应用：React 19 + TypeScript + Vite 单页应用，只与后端 gateway 通信（`/api` 下的 REST/SSE，外加 `/health`）。入口是 `src/main.tsx`，它挂载 `src/App.tsx`，并带上主题与 locale 桥接、一个错误边界、React Query client 和路由。品牌字符串在构建时从仓库根 `brand.json` 注入（见 `vite.config.ts`）。

## 命令

在本目录内以 `npm run <script>` 运行，或在仓库根经括号中所示的 `-w web` 别名运行。要求 Node >= 20.11。

| 脚本 | 别名（仓库根） | 作用 |
| --- | --- | --- |
| `dev` | `dev:web` | Vite dev server，监听 `127.0.0.1:5173`（`VITE_PORT`，严格端口）；把 `/api` 与 `/health` 代理到 `VITE_API_TARGET`（默认 `http://127.0.0.1:8000`）。端口与代理位于 `vite.config.ts`。 |
| `build` | `build:web` | 先 `tsc --noEmit` 类型检查，随后 `vite build` 输出到 `dist/`。 |
| `preview` | `preview:web` | 在本地伺服生产构建。 |
| `test` | `test:web` | 来自 `tests/unit` 的 Vitest 单元测试（jsdom 环境，setup 文件为 `tests/setup.ts`）。变体：`test:watch`、`test:coverage`。 |
| `test:e2e` | — | 来自 `tests/e2e` 的 Playwright 规格；`playwright.config.ts` 会在端口 `5193`（`E2E_PORT`）自启 dev server。 |
| `lint` | `lint:web` | 以 `--max-warnings 0` 对 `src/` 运行 ESLint（flat 配置位于 `eslint.config.js`）。 |
| `typecheck` | `typecheck:web` | 对继承 `../config/tsconfig.base.json` 的 tsconfig 运行 `tsc --noEmit`。 |
| `i18n:check` | `i18n:web` | i18n 键一致性检查（`scripts/check-i18n-keys.mjs`）。 |
| `format` / `format:check` | `format:web`（check） | 对本包运行 Prettier 写入 / 检查。 |

## 布局（`src/`）

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

`tests/` 与这一划分镜像：`tests/unit/` 存放 Vitest 规格（`.test.ts`/`.test.tsx`），`tests/e2e/` 存放 Playwright 规格；`tests/setup.ts` 注册 `@testing-library/jest-dom`，并强制使用 React 开发构建以支持 `act()`。

## 备注

- 详细前端文档：[docs/web/frontend.zh.md](../../docs/web/frontend.zh.md)。
- 本目录的工作规则：[AGENTS.md](AGENTS.md)。
- 安装与运行说明：仓库根 [README.zh.md](../../README.zh.md)。
