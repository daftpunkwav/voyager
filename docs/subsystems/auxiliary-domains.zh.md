# 辅助域

[English](auxiliary-domains.md) | 中文

四个小域补全集:`settings`(面向用户的设置)、`browser`(浏览器控制;外部 browser host 接通前所有命令都被拒绝)、`code_exec`(沙箱代码执行)、`office`(块式文档与幻灯片)。

## settings 域

源码:`packages/settings/src/settings/` — 端口 8080,默认启用。区别于框架包 `platform_settings`。

能力:`list_themes`、`get_theme`、`set_theme`、`get_settings`(全部已注册模块的聚合 schema,可按 `module` 过滤)、`get_setting`(secret 项只返回 `has_value`)、`set_setting`(对 secret 项的写入被 `platform_settings.SettingsStore` 拒绝)。

持有外观与隐私键:`appearance.theme`(`dark`/`light`/`system`)、`appearance.locale`(`zh-CN`/`en`/`system`)、`appearance.font_scale`、`appearance.code_font`、`privacy.activity_report`。组合进程中无自有存储 — `wire()` 把自己的 `DEFS` 注册到共享 `SettingsStore`;独立运行时创建 `SettingsStore(<data_dir>/settings.db)`。

## browser 域

源码:`packages/browser/src/browser/` — 端口 8060,**默认禁用**。存储 `data/runtime/browser/browser.db`(仅一张 `sessions` 元数据表)。

能力:`navigate`、`click`、`type`、`read`、`screenshot`,各自返回 `BrowserResult`(`ok`、`url`、`title`、`text`、`screenshot_path`、`error`)。`navigate` 按 `browser.allowed_domains` 对 netloc 做后缀/相等匹配,否则 `ServiceError(FORBIDDEN)`。

`host.py` 以 `BROWSER.UNAVAILABLE` 拒绝所有命令,直至与外部 browser host(`desktop/browser-host`)的 IPC 通道接通 — 它绝不会以占位内容报告 `ok=True`。设置:`browser.allowed_domains`、`browser.headless`。

## code_exec 域

源码:`packages/code_exec/src/code_exec/` — 端口 8050,**默认禁用**。存储 `data/runtime/code_exec/code-exec.db`(`executions` 表;行按 30 天保留并受 200 行上限约束,被清理行的 artifact 目录随之删除)。

能力:`list_runtimes`;`run_snippet(runtime, code)` 与 `run_file(runtime, file_path)` — 均为 `long_running=True`:拉起后台工作并立即返回 `JobRef`。`run_file` 拒绝逃出 `workspace/sandbox/` 的路径。最多 4 个执行并发(超出报 `QUEUE_FULL`),超过 256 KB 的代码被拒绝(`INVALID_INPUT`)。

`executor.py` — `run_in_runtime(...)`:把代码写到 `workspace/sandbox/artifacts/<exec_id>/`,然后一次性运行 `docker run --rm -m <memory> -v <artifact_dir>:/workspace`(除 `code_exec.network` 开启外网络为 `none`),镜像/命令/扩展名经白名单校验。无 Docker 时,宿主回退(仅内置 `python`/`node`/`shell` 运行时)在 `code_exec.allow_unisolated` 未启用时直接拒绝:宿主模式无法落实内存/网络限制,启用后以完整宿主权限执行、发出警告,并在结果中标记 `isolation="none"`。每路输出上限 1 MiB;超时杀死并回收子进程,并保留实际执行的隔离归属。发出 `task.progress`/`task.completed`/`task.failed`。

设置:`code_exec.runtimes`(`{id, image, cmd, file_ext}` 的 JSON 列表)、`code_exec.timeout_seconds`、`code_exec.memory_mb`、`code_exec.network`、`code_exec.use_host`、`code_exec.allow_unisolated`(仅用户可改,默认 `false`)。

## office 域

源码:`packages/office/src/office/` — 端口 8040,**默认禁用**。存储 `data/runtime/office/office.db`(一张 `documents` 表承载两种类型)。

能力合并两个子 registry:doc(`create_doc`、`get_doc`、`update_doc`、`insert_block`、`delete_doc`)与 slides(`create_deck`、`get_deck`、`update_deck`、`add_slide`、`delete_deck`)。文档是块数组(`kind='doc'|'slides'`,`blocks` JSON)。发布 `doc.created`、`doc.edited`。设置:`office.export.dir`。
