# packages — 后端模块根

platform(横切机制)+ 领域包(可独立进程)+ host(装配根)。

每个领域目录 = 可独立进程(§13.1):自带注册表 → REST + MCP,测试只跑自己目录。
新增领域 = 复制 `_template`,写 `service.json` 模块卡,不触碰任何其他目录——
重启后 host 扫描自动接入(`packages/host/src/host/scan.py` 读卡装配),agent 工具花名册
出现 `<domain>__*`。

独立运行:各域 `rest.py` 暴露 `create_app` 工厂,
`uvicorn <domain>.rest:app_factory --factory --port <下表端口>`;
MCP:`python -m <domain>.mcp_server`(成员已 editable 安装,任意目录可运行)。

## 包内布局(src layout)

```
packages/<domain>/
├── pyproject.toml     # hatchling;依赖只声明 platform-*
├── service.json       # 模块卡(host 扫描读这里,不进 src)
├── README.md
├── src/<domain>/      # 导入名即目录名:from <domain>.rest import create_app
└── tests/             # 平铺,无 __init__.py(根 pytest 为 importlib 模式)
```

- platform 组同形:`packages/platform/<pkg>/src/platform_<pkg>/`;
- 所有成员由 `uv sync` 以 editable 方式装入 venv,不再依赖任何 sys.path 注入;
- 新增域要同时进根 `pyproject.toml` 的 members / dependencies / tool.uv.sources;
- 决策与迁移记录:docs-local/design/2026-09-10-packages-src-layout.md。

## 数据根(双轨语义,有意为之)

- **独立运行**:数据默认写领域目录内 `packages/<domain>/data/`
  (自包含、可整目录删除;已列入 .gitignore 防误提交);
- **聚合运行**(packages/host 装配根,日常形态):共享 `data/runtime/` 单例注入,
  与 agent/事件流同根;agent 工作区在 `data/workspace/`。
两形态的数据互不相通;切回独立运行时是空库属预期,不是数据丢失。

## 端口登记处(单一登记,新服务在此领号)

| 端口 | 服务 | 状态 |
|---|---|---|
| 8000 | gateway | 已实现 |
| 8010 | sources | 已实现 |
| 8020 | notes | 已实现 |
| 8030 | graph | 已实现 |
| 8040 | office | 已实现 |
| 8050 | code-exec | 已实现 |
| 8060 | browser | 已实现 |
| 8070 | llm | 已实现 |
| 8080 | settings | 已实现 |
| 8090 | _template | 示例 |

## 历史布局迁移(已完成)

- 旧 `services/api`、`services/agent`、`services/graph_engine`、`services/mcp`
  已分别迁为 `gateway`、顶层 `agent/`、`graph`、各域自带 `mcp_server.py`;
- 2026-09-06 三源码根收敛:顶层 `services/` → `packages/`、`platform/` →
  `packages/platform/`、`deploy/` → `packages/host/`、TS 共享配置 →
  `apps/config/`、`workspace/` → `data/workspace/`、`runtime-data/` →
  `data/runtime/`(见 docs-local/design/2026-09-06-three-source-roots.md);
- 2026-09-10 src 布局:各成员源码由包根平铺迁入 `src/<name>/`,导入前缀
  `packages.<x>` 退役为 `<x>`,成员从 virtual 转为 editable 安装
  (见 docs-local/design/2026-09-10-packages-src-layout.md)。
