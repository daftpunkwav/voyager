# 前端架构(apps/web)

> 与 `docs-local/design/architecture.md` §2.1 / §10.1 / §12 对齐。本文件记录**当前实施**
> (2026-09 审查后实况),结构与规则以本文件 + `eslint.config.js` 为准。

## 1. 分层与共享物(§10.1 铁律 1 前端落实)

| 层                | 路径                                              | 职责                                                                                                                                                       |
| ----------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **bridge**        | `src/bridge/`                                     | 唯一与后端对话的层:callCapability、上传、sendBeacon 兜底、聊天历史/上线/活动回放/健康探测、SSE 订阅。页面与 hooks **不得**直连 fetch                       |
| **contracts(TS)** | `src/api/types/`                                  | 后端 DTO 的 TS 镜像(按域拆 10 文件 + `types.ts` 桶式 re-export)。注:与 `platform/contracts` 之间暂为手工镜像 + 契约测试对账,生成管线未建(已知差距)         |
| **基础 UI**       | `src/components/common/`、`src/components/icons/` | 跨域通用 UI(Toast/GlassCard/EmptyState/MarkdownRenderer 等)与图标                                                                                          |
| **域组件层**      | `src/components/<域>/`                            | 单域业务组件(project=settings/sources 域、settings、usage、graph、code-graph、agent)。默认仅单一页面消费;确需跨页共享时留在本层并在此登记,禁止下放各页互引 |
| **页面壳**        | `src/pages/<域>/`                                 | 页面装配(provider + Page 组件 + 域内切段);页面之间互不 import                                                                                              |
| **应用壳**        | `src/shell/`                                      | AppShell + Sidebar/Topbar + 路由探针 + 全局挂载点;域副作用经 `bridges` 由 `App.tsx` 注入,壳不 import 页面私有模块                                          |

**强制规则**(ESLint `no-restricted-imports` 四段固化,`eslint.config.js`):

- 页面之间互不 import(整禁 `@/pages/*`);共享只经 bridge / contracts / 基础 UI / 域组件层;
- 共享层(components/common、hooks、stores)禁止 import 页面模块;
- 非 chat 页面禁止直触 `@/stores/chatStore` / `@/stores/floatingStore`,跨域交互走 `bridge/chatSend` 契约(sendUserTurn / openFloatingChat / markChatInterrupted / chatSystemNote)。

## 2. 目录结构(实况)

```
apps/web/src/
├── api/                # 按域数据薄层 + 类型
│   ├── <域>.ts         # projects/sources/notes/graph/auth/settings/overview/usage:
│   │                   #   直接 callCapability,直接返回 payload(无信封);形状归一化在本层
│   ├── types.ts        # 桶式 re-export → types/
│   └── types/          # 按域 10 文件:agent/codeGraph/common/graph/llm/notes/settings/sources/system/usage
│
├── bridge/             # ★ 唯一后端对话层
│   ├── client.ts       # callCapability<T> + uploadFile + beaconCapability(unload 兜底)+ unwrapDataField(迁移期)
│   ├── chatSend.ts     # 发消息 / 聊天历史 / 上线事件 + 跨域 chat 契约(sendUserTurn 等)
│   ├── stream.ts       # 共享 SSE(断线续传 after_seq)
│   ├── session.ts      # 环回 bootstrap + /health 探活
│   ├── activity.ts     # 行为上报(隐私硬开关)+ 活动回放
│   └── feed.ts / events.ts / pageContext.ts / quotaGuard.ts
│
├── components/         # 基础 UI + 域组件层(见 §1)
│   ├── common/  icons/
│   ├── project/        # sources 域组件(项目表/导入/分类标签/AI 面板)
│   ├── settings/       # 设置域组件(含 agent/ llm/ 子目录)
│   ├── usage/ graph/ code-graph/ graph-viz/ agent/
│
├── hooks/              # 数据 hooks(经 api/<域> 薄层;一域一文件)
├── constants/          # 跨域只读常量(人格、LLM 配置)
│
├── pages/              # ★ 页面即模块:activity chat code-graph graph health notes overview settings sources team usage
│   └── notes/          # 例:Page + provider + notesAutoSave/notesBatch/notesSplit* 等域内切段
│
├── shell/              # 应用壳:AppShell、Sidebar/Topbar、ServiceBadge、pageProbes、themeBridge
├── stores/             # zustand(0 互引):auth chat codeGraph floating graph note project settings ui
├── styles/             # design-system.css 单一来源 + shell/global + pages/ 页面私有 CSS
├── utils/              # 跨域纯函数(单文件单职责;errorCodes 与后端 ErrorSuffix 对齐,契约测试锁定)
├── widgets/            # FloatingChat、PageProbe、chat/(悬浮窗视图组)
├── App.tsx             # 路由表
└── main.tsx            # 入口
```

## 3. 数据访问现状(2026-09 legacyApi 已退役)

- 数据访问链:`hooks/组件 → api/<域>.ts(按域薄层,payload 直返)→ bridge/client.callCapability → gateway`;
  加一个能力的改动面 = 后端 capability + api/<域> 一个函数 + 调用点,无中间注册表;
- `bridge/legacyApi.ts` 与 `api/client.ts`(getApi 门面)已整体删除:97 方法门面、
  38 条 METHOD_MAP 分发表、`{data}` 信封与 IApiClient 兼容别名不再存在;
  `bridge/client.unwrapDataField` 是迁移期等价取值助手(结果自带 data 键则透传),
  随各能力形状核实逐域退役;
- 例外:settings 表单域(settings/* 组件)直调 callCapability 读写设置键,是既定
  模式而非绕行;跨域聊天交互一律走 `bridge/chatSend` 契约(ESLint 固化);
- 错误信封 `{"error":{code,message,hint,trace_id}}` 统一在 bridge/client 解包为
  `ServiceError`;错误码展示文案单一来源:`utils/errorCodes.ts`(按后端 ErrorSuffix
  后缀匹配,`tests/unit/errorCodes.test.ts` 锁定契约)。

## 4. 域边界备注

- **graph 一词两域**:`pages/graph` = 资源关系图(L0);`pages/code-graph` = 代码图谱(L1)。
  `components/graph/` 是两域共用的图可视化组件(ForceGraph 等);新域组件先放域目录,
  确需跨域再提升,不要为"复用"提前下沉。
- `components/agent/EmbedAgentChat` 经 `widgets/EmbedAgentChat` 两行 stub 导出:
  域组件出口模式,其他域不得绕过 stub 直引 components/agent。

## 5. 工程命令与已知状态

- 测试:`npm run test:web`(vitest,tests/unit;jsdom 打桩 matchMedia/scrollIntoView);
- 类型:`npm run typecheck:web`;lint:`npm run lint:web`(严格 `--max-warnings 0`,
  2026-09 起全绿;新增代码必须保持 0 warning)。
