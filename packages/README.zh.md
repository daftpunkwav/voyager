# packages — 后端模块根层

> 语言：简体中文 | [English](README.md)

platform（横切机制）+ domain 包（可独立运行的进程）+ host（装配根）。

每个 domain 目录 = 一个可独立运行的进程：自带 registry → REST + MCP，测试也放在自己的目录内。
新增一个 domain = 复制 `_template`，填写 `service.json` 模块卡，并注册 workspace member——无需改动 host——
重启后 host 扫描会自动将其拾取（`packages/host/src/host/scan.py` 读取模块卡并装配），`<domain>__*` 便会出现在 agent 的工具名册中。

独立运行：每个 domain 的 `rest.py` 暴露 `create_app` 工厂，
`uvicorn <domain>.rest:app_factory --factory --port <port from the table below>`；
MCP：`python -m <domain>.mcp_server`（各成员以 editable 方式安装，可在任意目录运行）。

## 包内布局（src layout）

```
packages/<domain>/
├── pyproject.toml     # hatchling; dependencies declare platform-* only
├── service.json       # module card (the host scan reads this; not inside src)
├── README.md
├── src/<domain>/      # import name = directory name: from <domain>.rest import create_app
└── tests/             # flat, no __init__.py (root pytest runs in importlib mode)
```

- platform 一组结构相同：`packages/platform/<pkg>/src/platform_<pkg>/`；
- 所有成员由 `uv sync` 以 editable 方式装入 venv，不注入 sys.path；
- 新增 domain 还须登记进根 `pyproject.toml` 的 members / dependencies / tool.uv.sources；

## 数据根目录（双轨语义，有意为之）

- **独立运行**：数据默认写入 domain 目录内，即 `packages/<domain>/data/`
  （自包含，整个目录可删；已列入 .gitignore 以防误提交）；
- **聚合运行**（packages/host 作为装配根，默认形态）：注入共享的 `data/runtime/` 单例，
  与 agent/事件流同根；agent 工作区位于 `data/workspace/`。
  两种形态的数据互不相通；切回独立运行后数据库为空属预期行为，并非数据丢失。

## 端口注册表（单一注册表；新服务在此认领编号）

| 端口 | 服务      |
| ---- | --------- |
| 8000 | gateway   |
| 8010 | sources   |
| 8020 | notes     |
| 8030 | graph     |
| 8040 | office    |
| 8050 | code-exec |
| 8060 | browser   |
| 8070 | llm       |
| 8080 | settings  |
| 8090 | _template |

本目录树的工程约定：[AGENTS.md](AGENTS.md)。
