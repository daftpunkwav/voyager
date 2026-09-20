# Voyager

> 语言:简体中文 | [English](README.md)

本地优先的 agent 伴侣工作台:导入仓库 / 文档 / 网页,记笔记,构建知识图谱 —— 人与 agent 驱动同一层能力面。

内置人格:一名常驻编排者(显示名 Lucien)加 4 个预设(侦察 / 讲解员 / 整理者 / 图谱向导);人格显示名位于 personas 数据层与 `apps/web/src/constants/agentCatalog.ts`。UI 品牌字符串(产品名、标语)只存于仓库根的 `brand.json`。

**技术栈:** FastAPI + sqlite3 / React + TypeScript + Vite。默认单体装配(`packages/host/`)在单进程内运行 gateway + 各域包 + agent;图谱 C 引擎也可作为 sidecar 运行。

## 快速开始

```bash
uv sync        # Python 依赖(uv workspace)
npm install    # Node 依赖(npm workspaces)
```

启动前需设置 `SECRETS_ENCRYPTION_KEY` 或 `SECRET_KEY`(一串足够长的随机字符串 —— 不要复用 `.env.example` 中的示例值);LLM API Key 在设置页录入(BYOK)。没有 Key 时聊天优雅降级,sources / notes / graph 仍可用。

### 开发

```bash
uv run python -m host.dev    # gateway :8000 + Vite :5173
```

质量门禁在本地运行:`npm run gate`(`gate:py` = ruff format/check、import-linter 分层契约、mypy、pytest、依赖图检查;`gate:web` = tsc、eslint、vitest、i18n 键检查、prettier)。

## 端口

| 服务                   | 默认端口     | 覆盖方式             |
| ---------------------- | ------------ | -------------------- |
| Web(Vite dev)         | 5173         | `VITE_PORT`          |
| gateway(uvicorn)      | 8000         | —                    |
| 图谱 C 引擎 sidecar    | 8123 / 9750  | 见服务设置           |

后端环境变量记录在 `.env.example`。

## 仓库布局

三个源码根(产品代码只识别这三棵树):`agent/` · `apps/` · `packages/`。

```
├── agent/             # ① 源码根:AI 编排层(零导入域实现;src/agent/ + tests/)
├── apps/              # ② 源码根:前端(npm workspaces:apps/*)
│   ├── web/           # React 主应用(只与 gateway 通信)
│   └── config/        # 共享 TS/eslint 配置
├── packages/          # ③ 源码根:后端模块(uv 成员;每个包为 src/<name>/ + tests/)
│   ├── platform/      # 横切机制(contracts / capability / eventbus / …)
│   ├── gateway/       # 聚合 REST/SSE 外壳
│   ├── notes|sources|graph|llm|settings|office|browser|code_exec/
│   └── host/          # 装配根:扫描 service.json 接入各域
├── plugins/           # 声明式用户插件(plugin.json;无热执行)
├── data/              # 本地数据根(gitignored)
│   ├── workspace/     # "家":克隆、书籍、导出、沙箱
│   └── runtime/       # "脑":events/audit/memory/checkpoints
└── brand.json         # 品牌字符串唯一来源
```

每个后端包在自己的 `README.md` 中记录契约(用途 / 配置 / 扩展点 / 工具面 / 限制),从 [packages/README.zh.md](packages/README.zh.md) 开始;agent 源码根从 [agent/README.zh.md](agent/README.zh.md) 开始。

> **产品面**:`packages/office / browser / code_exec` 三域已实现且可独立运行(各自带 rest.py / mcp_server.py),但模块卡为 `enabled_by_default=false`,默认单体装配不挂载,产品 UI 也尚未包含它们。可在设置中显式启用,或用 `ENABLE_DOMAINS` 环境变量。
>
> **仅本地运行**:默认无外部网络依赖;LLM 访问为 BYOK 或本地 OpenAI 兼容端点,无可用模型时 agent 降级。

## 文档

- `docs/` 目录按代码现状编写文档:从 [docs/README.zh.md](docs/README.zh.md) 开始 —— 架构、子系统参考、目录(工具 / 设置 / 数据布局)、前端、测试。
- 前端从 [apps/web/README.zh.md](apps/web/README.zh.md) 开始。

## 约定与贡献

- 工程约定(commit、前端规则):[AGENTS.md](AGENTS.md)。在子树中工作的编码 agent 还应阅读该子树的 `AGENTS.md`([agent/](agent/AGENTS.md)、[packages/](packages/AGENTS.md)、[apps/web/](apps/web/AGENTS.md))。
- 贡献指南:[CONTRIBUTING.zh.md](CONTRIBUTING.zh.md)(English: [CONTRIBUTING.md](CONTRIBUTING.md))。
- 安全策略与漏洞报告:[SECURITY.md](SECURITY.md)。
