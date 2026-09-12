# packages/_template — 新领域服务脚手架

复制本目录即得一个新服务(验收标准:不触碰任何其他目录,§13.1):

1. `cp -r packages/_template packages/<domain>`,把 `src/_template/` 改名为
   `src/<domain>/`,并全局替换 `_template` / `template` 为 `<domain>`
   (pyproject 的 `name` 与 `packages = ["src/<domain>"]`、`service.json` 的
   `name`、tests 里的导入);
2. 在根 `pyproject.toml` 的 `tool.uv.workspace.members` 加入 `packages/<domain>`,
   `dependencies` 与 `tool.uv.sources` 同步登记,然后 `uv sync`;
3. 在 `src/<domain>/capabilities.py` 注册本领域能力(初始最小集,完整清单写进
   本包 README);
4. 长任务:handler 只入队返回 `JobRef`(§7.3),进度经事件流,见 `worker.py` 示例;
5. 端口在 `service.json` 声明,向 gateway 登记(packages/README.md 端口表)。

布局(src layout,决策见 docs-local/design/2026-09-10-packages-src-layout.md):

```
packages/<domain>/
├── pyproject.toml      # hatchling;依赖只声明 platform-*
├── service.json        # 模块卡
├── README.md
├── src/<domain>/       # 六件套:capabilities / rest / mcp_server / worker / store / settings
└── tests/              # 平铺,无 __init__.py
```

---

## Purpose

Seven-piece domain template: capabilities/wiring/rest/mcp_server/store/settings/worker — copy it, rename, and the composition root discovers the domain with zero host changes.

## Configuration

service.json card + module settings.py defs.

## Extension Points

This IS the extension point for new domains.

## Known Limitations

Deliberately minimal: no migrations/worker examples beyond a stub.

## Deferred Work

A generator script (copy + rename in one command).
