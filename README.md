# Voyager

本地优先的 agent 共生工作台：导入仓库/文档/网页，笔记与知识图谱，人和 agent 走同一套 capability。

人格：常驻 orchestrator（显示名 Lucien）+ 4 个预设（侦察 / 讲解 / 整理 / 图谱向导）。品牌字符串只在仓库根 `brand.json`。

**技术栈：** FastAPI + sqlite3 / React + TypeScript + Vite。默认单体装配（`packages/host/`）一进程跑 gateway + 领域包 + agent；图谱 C 引擎可作为 sidecar。

## 快速开始

```bash
uv sync        # Python 依赖（uv workspace）
npm install    # Node 依赖（npm workspaces）
```

配置 `SECRETS_ENCRYPTION_KEY` 或 `SECRET_KEY`（随机长串，不要用 `.env.example` 里的示例值）后启动；在设置页填入 LLM API Key（BYOK）。无 Key 时对话降级，资料库/笔记/图谱仍可用。

### 开发启动

```bash
uv run python -m host.dev    # gateway :8000 + Vite :5173
```

质量门禁在本地执行:`npm run gate`（`gate:py` = ruff format/check、import-linter 层级脱耦合同、mypy、pytest;`gate:web` = tsc、eslint、vitest、i18n 键检查、prettier）。

## 端口

| 服务 | 默认端口 | 覆盖变量 |
|------|----------|----------|
| Web（Vite dev） | 5173 | `VITE_PORT` |
| gateway（uvicorn） | 8000 | — |
| 图谱 C 引擎 sidecar | 8123 / 9750 | 见服务设置 |

完整环境变量清单见 `.env.example`。架构见 `docs-local/design/architecture.md`(本地设计稿,不入库)。

## 目录结构

三源码根（产品代码只认这三棵）：`agent/` · `apps/` · `packages/`。

```
├── agent/             # ① 源码根:AI 编排层（零 import 领域实现;src/agent/ + tests/）
├── apps/              # ② 源码根:前端（npm workspaces: apps/*）
│   ├── web/           # React 主应用（只经 gateway）
│   └── config/        # 共享 TS/eslint 配置
├── packages/          # ③ 源码根:后端模块（uv 成员;每包 src/<name>/ + tests/）
│   ├── platform/      # 横切机制（contracts / capability / eventbus / …）
│   ├── gateway/       # 聚合 REST/SSE 壳
│   ├── notes|sources|graph|llm|settings|office|browser|code_exec/
│   └── host/          # 装配根:扫描 service.json 自动接入领域
├── plugins/           # 声明式用户插件（plugin.json,禁止热执行）
├── data/              # 本地数据根(gitignore)
│   ├── workspace/     # 「家」:克隆、书籍、导出、沙箱
│   └── runtime/       # 「脑」:events/audit/memory/checkpoints
└── brand.json         # 品牌字符串唯一来源
```

> **产品面说明**：`packages/office / browser / code_exec` 三域已实现且可独立运行
> （各带 rest.py / mcp_server.py），模块卡 `enabled_by_default=false`,默认单体
> 装配不挂载，产品界面暂不含这三域；经设置或 `ENABLE_DOMAINS` 环境变量显式打开。
>
> **纯本地**：默认不依赖外网；LLM 走 BYOK / 本地兼容端点，无可用模型时 agent 降级。

工程规范见 `AGENTS.md`。
