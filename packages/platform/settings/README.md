# platform/settings — 设置项框架

每个设置项的定义:`key / type / 默认值 / 所属模块 / secret 标记 / 描述`(§7.9)。

- 各服务在自己的 `settings.py` 声明本服务设置项,启动时 `register()`;
- `set()` 校验类型/取值域;**secret 项仅 user 可写**(§8.8 隐私例外);
- 变更发布 `settings.changed` 事件(secret 项 payload 不含值);
- `list_schema()` 供设置页动态渲染:不硬编码任何设置项,secret 只回 `has_value`。

---

## Purpose

Settings store: typed SettingDef registry (STR/INT/FLOAT/BOOL/JSON), hot-read values, change events, user_only + secret enforcement.

## Configuration

None — every module registers its own defs (register_fresh is idempotent).

## Extension Points

Register SettingDefs in your module; never read unregistered keys (get raises NOT_FOUND).

## Known Limitations

user_only is all-or-nothing per key (no scopes).

## Deferred Work

Per-key actor scopes.
