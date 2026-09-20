# 贡献指南

> 语言:简体中文 | [English](CONTRIBUTING.md)

本指南是贡献者的入门层,只指向单一事实源文档;当文字与代码不一致时,以代码和门禁脚本为准。

## 环境

- Python 3.11(`.python-version`),使用 [uv](https://docs.astral.sh/uv/) 管理;仓库是 uv workspace,所有成员以 editable 方式安装(`uv sync` 同时安装 ruff、mypy、pytest、import-linter)。
- Node ≥ 20.11(`.nvmrc`:20)与 npm 10 workspaces(`apps/*`)。
- 配置仓库根的 `.env`(绝不提交)。`SECRETS_ENCRYPTION_KEY`(或后备名 `SECRET_KEY`)必须是一串足够长的随机字符串 —— 文档中的示例值会被拒绝。后端环境变量记录在 `.env.example`;少数仅前端的变量(`VITE_API_TARGET`、`E2E_PORT`)从 shell 环境读取。
- 一条命令启动全部:`uv run python -m host.dev`(gateway 8000,Vite 5173)。分进程启动方式见 [docs/development.zh.md](docs/development.zh.md)。

## 工作流

1. 从 `main` 拉分支,命名 `<type>/<kebab-case-description>`,例如 `fix/chat-history-paging`。
2. 提交信息为 `<type>(<scope>): <subject>`,type 取 `feat`、`fix`、`refactor`、`chore`、`docs`、`test`、`perf`。一个 commit 只做一件事;每一行 diff 都能追溯到对应的需求。
3. 不要顺手重构无关代码。完整约定见 [AGENTS.md](AGENTS.md);子树约定放在代码旁([agent/](agent/AGENTS.md)、[packages/](packages/AGENTS.md)、[apps/web/](apps/web/AGENTS.md))。

## 推送前:质量门禁

仓库没有 CI,本地门禁就是门禁。每次推送前运行,并直接确认退出码为绿(不要从管道推断):

```bash
npm run gate        # gate:py && gate:web
npm run eval        # agent 评测套件(agent/tests/eval);真模型需环境变量门控
```

`gate:py` = ruff format/check、import-linter 分层契约、mypy、pytest、依赖图检查。`gate:web` = tsc、eslint(`--max-warnings 0`)、vitest、i18n 键检查、prettier。各脚本内容:[docs/development.zh.md](docs/development.zh.md)。门禁红意味着修改本次变更 —— 不要为了让检查通过而削弱检查。

## 测试

- 位置:各包的测试放在自己的 `tests/`(平铺,无 `__init__.py`);agent 测试在 `agent/tests/`(含粒度审计与 eval harness)。布局与门禁:[docs/testing.zh.md](docs/testing.zh.md)。
- 行为变更要更新或新增钉住该行为的测试;修 bug 必须带回归测试。
- agent 测试套件包含冻结面测试(capability/tool 名字对等、文件粒度、文件头、命名中立)。那里的测试红时,修的是本次改动,不是冻结清单 —— 新增面按 [packages/AGENTS.md](packages/AGENTS.md) 与 [agent/AGENTS.md](agent/AGENTS.md) 中的规则显式登记。

## 文档与文案

- 行为变更在同一变更中更新文档。`docs/` 树以双语镜像代码(每篇文档三个文件;配对契约见 [docs/AGENTS.md](docs/AGENTS.md))。包 README 遵循 [packages/README.zh.md](packages/README.zh.md) 的契约。
- 文档面向代码:陈述现状、论断可验证,不引用计划或报告。
- 代码注释与 docstring 用英文。用户可见的 UI 文案放在 i18n 资源(`apps/web/src/i18n/resources/`),`zh-CN` 为源语言、`en` 为镜像 —— 绝不内联。

## 提交

- 每次变更一个关注点,门禁绿,commit body 描述行为差异。新增域遵循 `packages/_template/` 流程(复制模板、加入 workspace 成员、放一个 `service.json` —— 无需改动 host)。
- 各包的扩展点列在该包 `README.md`(从 [packages/README.zh.md](packages/README.zh.md) 开始)。

## 安全

漏洞不要开公开 issue,按 [SECURITY.md](SECURITY.md) 私密报告。

## 许可

项目基于 [MIT 许可](LICENSE)发布;提交贡献即表示同意你的贡献同样以该许可发布。
