# 前端(`apps/web`)

[English](frontend.md) | 中文

浏览器应用:React 19 + TypeScript(strict)+ Vite 7,与 8000 端口上的组合后端通信。源码:`apps/web/src/`。树内另有概览 `apps/web/src/ARCHITECTURE.md`。

## 技术栈

React 19(经根 `package.json` 的 `overrides` 精确钉版)、`react-router-dom` 7、`zustand` 5(UI 状态)、`@tanstack/react-query` 5(服务端状态)、`i18next`/`react-i18next`、CodeMirror 6、Mermaid 11、`pdfjs-dist` 6、D3 7、`react-markdown` + rehype/remark + DOMPurify。测试:Vitest 4(jsdom)+ Playwright。

## 入口与路由

`src/main.tsx` — QueryClientProvider + BrowserRouter + ErrorBoundary,同步 `initI18n()`,再 `ensureSession()`(`src/bridge/session.ts`),然后渲染 `<App />`。

`src/App.tsx` 把所有路由挂在 `AppShell`(`src/shell/AppShell.tsx`)下;重页面懒加载,chat 即时加载:

- `/`、`/chat` → `ChatPage`(`/chat/:sessionId` 重定向到 `/chat`)
- `/team`、`/notes`、`/overview`、`/activity`、`/usage`、`/settings`、`/system/health`
- `/sources`、`/sources/{repo,doc,web}/:id`、`/sources/:id`
- `/graph`、`/code-graph`、`/code-graph/:id`
- 旧路由重定向(`/projects` → `/sources`、`/agent` → `/chat`)与 `*` → `NotFound`

## 后端访问

两个通道,都在 `src/bridge/`:

- **能力调用** — `client.ts: callCapability(domain, name, args)` POST 到 `/api/<domain>/capabilities/<name>`,带凭据与 `X-Trace-Id` 头;解包 `{result}`,或从 `{error: {code, message, hint, trace_id}}` 抛 `ServiceError`。`src/api/*.ts` 是按域的类型化包装。`uploadFile` multipart POST 到 `/api/uploads`;`beaconCapability` 走 `navigator.sendBeacon`。
- **事件流** — `stream.ts` 维护单例 `EventSource`,连 `GET /api/chat/stream?after_seq=<lastSeq>`,带 `withCredentials`;fnmatch 式 `*` 模式订阅;手动重连指数退避(1 秒 → 30 秒),从最后 seq 重放;首个订阅者到来时建立连接,最后一个退订时关闭。消费方:`hooks/useChatStream.ts`、`stores/chatStore.ts`、`bridge/events.ts`。

在用的非能力端点:`/api/chat/messages`、`/api/chat/trajectory`、`/api/chat/rawllm`、`/api/activity[/feed]`、`/api/session/bootstrap`、`/api/workspace/{pick,switch}`、`/api/sources/files/doc/:id`、`/api/notes/assets/...`。

## 状态与布局

`src/stores/` — zustand store:`auth`、`chat`、`codeGraph`、`floating`、`graph`、`note`、`project`、`settings`、`ui`。`src/hooks/` — 按域数据钩子(`useNotes`、`useGraph`、`useChatStream`、`useSettings` 等)。`src/components/` — 域组件树(`agent`、`settings`、`graph`、`team`、`usage`、`activity`、`code-graph`、`common`);chat 部件在 `src/widgets/chat/`;`src/pages/` 存放路由页。

## i18n

`src/i18n/` — 单次幂等的 i18next 初始化(`bootstrap.ts`),平铺点号键(`keySeparator: false`,命名空间分隔符 `:`),`DEFAULT_LOCALE = 'zh-CN'`,支持 `['zh-CN', 'en']` 加 `system` 选项(按 `navigator.languages` 解析)。资源:`src/i18n/resources/{en,zh-CN}/`,各 15 个相同命名空间。`apps/web/scripts/check-i18n-keys.mjs` 强制键 parity(`npm run i18n:check`)。

## 浮层与弹窗

非模态锚定浮层(composer 下拉、会话菜单、上下文环)经 `components/common/Popover.tsx` 渲染——它持有 open/leaving 生命周期、外点/Escape 关闭与 `.popover-pop` 进出场动效(退场快于进场);调用方自持定位与玻璃材质类。模态经 `components/common/ModalOverlay.tsx`(portal、scrim、对称进出场);它还维护模块级打开栈,保证 Escape 只关最上层模态,并在打开期间抬高 `uiStore.modalDepth`。确认操作走命令式 `confirmDialog()`(`stores/uiStore.ts`)——由 shell 挂载的 `ConfirmDialogHost` 渲染;不使用 `window.confirm`。工作区热切换必须经 `bridge/workspaceSwitch.ts`,确保请求 marker 先于 POST 落入 chatStore。

## 设置页

`src/pages/settings/SettingsPage.tsx` — 单页 17 节,三个导航组:基础(`general`、`appearance`、`llm`)、Agent 能力(`agents`、`agentLlm`、`subagents`、`plugins`、`mcp`、`skills`、`commands`、`tools`、`toolPerms`)、数据与系统(`health`、`usage`、`activity`、`data`、`about`)。块由 `src/components/settings/` 组合。

## 构建与开发

`vite.config.ts` — 别名 `@` → `./src`;开发服务器 `127.0.0.1:5173`(`VITE_PORT`、`strictPort`);`/api` 与 `/health` 代理到 `VITE_API_TARGET`(默认 `http://127.0.0.1:8000`);品牌字符串从仓库根 `brand.json` 注入;pdf.js 资源复制到 `/pdfjs/`;three/mermaid/pdfjs/codemirror/d3 各拆 vendor chunk;开发 CSP 以响应头注入。`npm run build` = `tsc --noEmit && vite build` 产出到 `dist/`;`npm run preview` 服务构建产物。gateway 不服务 SPA;生产环境由外部静态服务器或反向代理承载。
