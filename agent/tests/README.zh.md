# tests — agent 包测试套件

> 语言：简体中文 | [English](README.md)

针对 `agent/src/agent` 的 pytest 测试套件，在仓库根目录运行：`npm run test:py`（其内部调用 `uv run pytest -q`）；评测子集经 `npm run eval` 单独运行。`conftest.py` 提供面向装配完成的应用的 fixture 辅助函数（`agent_replies`、`settle`）；`__init__.py` 用于锚定包，使 pytest 的 importlib 模式不会遮蔽已安装的 `agent` 包。

## 布局

根目录下平铺的 `test_*.py` 覆盖横切面：wiring、capabilities、clients（含 resilience）、hooks、plugins、personas、policy（含 notify）、repl（含 replay）、skills、mcp、redaction、streaming UX、LLM 客户端（http / multimodal / structured）、用户钩子重载、命名中立性（源码中的品牌字面量），以及模块 docstring 头部风格。

子目录与包结构镜像（仅列选取的主题，并非穷举）：

- context/ —— 上下文工程：builder、editor、预算、剪枝、prefix cache、plan 门禁、tokenizer
- master/ —— 仲裁、dispatch 面、任务图、goal、sessions、主动 outreach、resilience
- memory/ —— 记忆类型、蒸馏、recorder、读取策略、向量存储（含降级）
- runtime/ —— 事件循环、调度器与队列存储、meter、trace span、恢复、期限、预算
- policy/ —— 权限模式、shell policy、write-roots 确认
- skills/ —— organizer
- subagent/ —— 模式、检查点与恢复、暂停/取消、实例用量、registry
- tools/ —— 工具面：registry、search、edit matchers、web search/fetch、AskUser、结果预算，外加按组用例（extension / memory / observe / session / team）
- eval/ —— 行为基线：`test_eval_scenarios.py` 在 FakeLLM 脚本上回放固定任务场景，完全离线；`npm run eval` 与 `baseline.json` 比对，`npm run eval:update` 在有意的行为变更之后重新生成基线
- granularity/ —— 文件粒度审计：`tools/<group>/` 下一个工具一个文件，`capabilities/<group>/` 下一个能力一个文件，文件名即产品名；mechanism 与聚合文件位于冻结的 allowlist 中
- docs/ —— README 契约审计：被枚举的包 README 必须携带要求的契约段落

## 真实模型评测

`eval/test_eval_real.py` 以同样的场景风格驱动一个在线的 OpenAI 兼容端点，且在未设置 `AGENT_EVAL_BASE_URL`、`AGENT_EVAL_API_KEY` 与 `AGENT_EVAL_MODEL` 时跳过；断言保持行为级且与模型无关。
