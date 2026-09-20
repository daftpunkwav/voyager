# platform/settings — 设置框架

> 语言：简体中文 | [English](README.md)

> 勿与 `packages/settings`（settings *域*：基于本框架构建的 REST/bridge 访问与主题键）混淆。

每个设置由以下各项定义：`key / type / default / owning module / secret flag / description`。

- 各服务在自己的 `settings.py` 中声明设置，并在启动时调用 `register()`；
- `set()` 校验类型/取值域；**密钥项仅用户可写**；
- 变更会发布 `settings.changed` 事件（密钥项的载荷不带值）；
- `list_schema()` 让设置页动态渲染：没有任何设置被硬编码，密钥项只返回 `has_value`。

---

## 用途

设置存储：带类型的 SettingDef 注册表（STR/INT/FLOAT/BOOL/JSON）、热读取值、变更事件、user_only + 密钥强制。

## 配置

无——每个模块注册自己的 defs（register_fresh 幂等）。

## 扩展点

在你的模块中注册 SettingDef；绝不读取未注册的键（get 会抛出 NOT_FOUND）。

## 已知限制

user_only 对每个键是全有或全无（无 scopes）。

## 暂缓事项

按键粒度的 actor scopes。
