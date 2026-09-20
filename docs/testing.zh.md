# 测试

[English](testing.md) | 中文

测什么、在哪里测、门禁怎么跑。

## Python 测试

在根 `pyproject.toml` 配置:`testpaths = ["packages", "agent"]`,importlib 导入模式,`asyncio_mode = auto`。以 `uv run pytest -q` 运行(`npm run test:py` 的一部分)。

| 位置 | 范围 |
|---|---|
| `agent/tests/` | 最大套件:循环、工具、策略、上下文、子代理、记忆、运行时机构 |
| `packages/host/tests/` | 组装、规划、接线、parity(`test_settings_parity.py`、`test_parity_surface`) |
| `packages/platform/*/tests/` | 框架包 |
| `packages/<domain>/tests/` | 各域能力与存储 |

## 前端测试

- 单测:`apps/web/tests/unit/**/*.test.{ts,tsx}`,Vitest + jsdom(`tests/setup.ts` 打桩浏览器 API);`npm run test:web`。
- E2E:`apps/web/tests/e2e/` 的 Playwright 用例,对开发服务器运行(`E2E_PORT`,默认 5193;`apps/web/playwright.config.ts`)。

## Agent eval

`agent/tests/eval/` — 面向场景的 turn 行为评估。`npm run eval` 运行(真模型场景由环境变量门控;否则以打桩运行)。`npm run eval:update`(`scripts/update_eval_baseline.py`)重录基线;基线 diff 就是模型面行为变更的可审查记录。

## 依赖图检查

`scripts/gen_dep_graph.py` 从 `import-linter` 检查的同一批 import 再生成包依赖图;提交的图过期时 `npm run graph:check` 失败。

## 运行门禁

```sh
npm run gate        # gate:py && gate:web
npm run gate:py     # ruff + import-linter + mypy + pytest + graph:check
npm run gate:web    # tsc + eslint + vitest + i18n 键 + prettier
```

门禁失败直接读命令退出码;不要把门禁命令接进会吞退出码的管道过滤器。
