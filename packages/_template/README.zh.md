# packages/_template — 新域服务脚手架

> 语言：简体中文 | [English](README.md)

复制本目录,你就得到一个新服务(验收标准:不触碰任何其他目录):

1. `cp -r packages/_template packages/<domain>`,把 `src/_template/` 重命名为 `src/<domain>/`,并全局把 `_template` / `template` 替换为 `<domain>`(pyproject 中的 `name` 与 `packages = ["src/<domain>"]`、`service.json` 中的 `name`、测试中的 import);
2. 把 `packages/<domain>` 加入根 `pyproject.toml` 的 `tool.uv.workspace.members`,并同样在 `dependencies` 与 `tool.uv.sources` 中注册,然后运行 `uv sync`;
3. 在 `src/<domain>/capabilities.py` 中注册本域的能力(初始最小集合;完整清单写入本包的 README);
4. 长任务:handler 只负责入队并返回一个 `JobRef`;进度经由事件流传递 —— 参见 `worker.py` 示例;
5. 端口在 `service.json` 中声明,并向 gateway 注册(端口表见 packages/README.zh.md)。

布局(src layout):

```
packages/<domain>/
├── pyproject.toml      # hatchling; dependencies declare platform-* only
├── service.json        # module card
├── README.md
├── src/<domain>/       # seven-piece set: capabilities / wiring / rest / mcp_server / worker / store / settings
└── tests/              # flat, no __init__.py
```

---

## 目的

七件套域模板:capabilities/wiring/rest/mcp_server/store/settings/worker —— 复制、重命名,装配根即可零 host 改动地发现该域。

## 配置

service.json 模块卡 + 模块 settings.py 定义。

## 扩展点

本目录正是新域的扩展点。

## 已知限制

刻意保持最小:除一个 stub 外没有迁移/worker 示例。

## 暂缓事项

一个生成器脚本(一条命令完成复制 + 重命名)。
