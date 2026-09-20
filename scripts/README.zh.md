# scripts/ — 仓库维护脚本

> 语言：简体中文 | [English](README.md)

用于仓库维护的小型 Python 工具。它们经下面列出的仓库根 `package.json` npm 脚本调用，或直接以 `uv run python scripts/<name>.py` 运行。

## 脚本

| 脚本 | 调用方 | 职责 |
| --- | --- | --- |
| `bootstrap_readmes.py` | —（无 npm 脚本） | 一次性生成器：为其内部 `CONTENT` 表所列的后端包与 agent 目录写出带固定段落（Purpose、Configuration、Extension Points、Model Experience、Known Limitations、...）的契约式 README 骨架；会跳过已包含 `## Purpose` 与 `## Known Limitations` 段落的文件。 |
| `gen_dep_graph.py` | `npm run graph` | 重新生成 `docs-local/arch-diagrams/module-graph.md` —— 一张用 grimp 依 `import-linter.ini` 所声明的 `root_packages` 构建的 mermaid 依赖图（直接 import 按顶层包聚合，输出经过排序）。带 `--check`（暴露为 `npm run graph:check`）时，文件缺失或过期即以退出码 1 结束。 |
| `update_eval_baseline.py` | `npm run eval:update` | 重新生成 agent 评测基线：运行 `agent/tests/eval/test_eval_scenarios.py` 中的每个场景，并重写该模块所引用的基线 JSON。 |

## 备注

- `scripts/` 由 Python 格式化/lint 门禁覆盖（`npm run lint:py` 对 `packages agent scripts` 运行 ruff format 与 check）；mypy（`typecheck:py`）与 pytest（`test:py`）只针对 `packages` 与 `agent`。
- `gen_dep_graph.py` 依赖 `grimp`，uv 环境中可用。
