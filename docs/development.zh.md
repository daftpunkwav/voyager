# 开发

[English](development.md) | 中文

工具链、启动与仓库约定。

## 工具链

- Python 3.11(`.python-version`),用 [uv](https://docs.astral.sh/uv/) 管理。仓库是 uv workspace(根 `pyproject.toml` 的 `[tool.uv.workspace]`),20 个可编辑成员:`agent`、11 个 `packages/*`(10 个业务域加 `_template`)、8 个 `packages/platform/*`。全部是 src 布局的 hatchling 包;`uv sync` 以可编辑方式安装全部成员与开发工具(`ruff`、`mypy`、`pytest`、`pytest-asyncio`、`import-linter`)。
- Node ≥ 20.11(`.nvmrc`:20),npm 10 workspaces(`apps/*`)。前端依赖在 `apps/web/package.json`。
- Ruff(行长 100,isort)、mypy(pydantic 插件,`mypy_path` 覆盖全部 `src` 根)、import-linter(`import-linter.ini`)。

## 运行

- 一条命令:`uv run python -m host.dev` — 后端(`host.assemble:build`)于 `127.0.0.1:8000`,加 Vite 开发服务器于 `127.0.0.1:5173`;两者同起同停(Ctrl+C)。
- 仅后端:`uv run uvicorn host.assemble:build --factory --port 8000`。
- 仅前端:`cd apps/web && npm run dev`(`/api` 代理到 8000)。
- 独立域:`uv run uvicorn <domain>.rest:app_factory --factory --port <port>`(端口在各 `service.json`);独立 MCP:`uv run python -m <domain>.mcp_server`。

## 门禁

| 脚本 | 执行 |
|---|---|
| `npm run lint:py` | 对 `packages agent scripts` 跑 `ruff format --check` + `ruff check` |
| `npm run lint:imports` | `lint-imports --config import-linter.ini` |
| `npm run typecheck:py` | `mypy packages agent` |
| `npm run test:py` | `pytest -q` |
| `npm run graph:check` | 再生成并比对依赖图(`scripts/gen_dep_graph.py --check`) |
| `npm run gate:py` | 以上全部 |
| `npm run gate:web` | `tsc --noEmit` + `eslint --max-warnings 0` + `vitest run` + i18n 键检查 + `prettier --check` |
| `npm run gate` | `gate:py && gate:web` |
| `npm run eval` | agent eval 套件(`agent/tests/eval`,真模型需环境变量门控);`eval:update` 重录基线 |

## 约定

- 提交主题:`<type>(<scope>): <subject>`,type ∈ `feat/fix/refactor/chore/docs/test/perf`。
- Python 文件头是纯模块 docstring(无 `@file` 标签);TypeScript/CSS 用 `/** @file */`。
- 代码注释与 docstring 用英文;UI 文案走 i18n(`zh-CN` 为源语言)。
- 新域:复制 `packages/_template/`(步骤见其 README),把成员加进根 `pyproject.toml` 的 workspace/依赖,放入 `service.json` — host 无需改动。
- 平台约束变更须经 `import-linter.ini` 契约:`platform-no-business`、`domains-independent`、`host-only-wiring`。
