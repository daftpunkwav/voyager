# Notes 域

[English](notes.md) | 中文

`notes` 域是知识库:带版本历史的 Markdown 笔记、wiki 链接、标签、附件、保存视图与回收站生命周期。

源码:`packages/notes/src/notes/` — 端口 8020,默认启用,存储 `data/runtime/notes/`(`notes.db`、`assets.db`)。

## 能力

注册按关注点拆分(`capabilities/`:`batch`、`catalog`、`history`、`lifecycle`、`transfer`、`view`;共享运行时在 `runtime.py`),全部合并进 `Registry("notes")` — 共 26 个能力:`create_note`、`update_note`、`edit_note_range`、`delete_note`、`restore_note`、`purge_note`、`empty_trash`、`list_notes`、`get_note`、`get_note_toc`、`resolve_links`、`import_note`、`link_note`、`get_backlinks`、`list_tags`、`rename_tag`、`notes_stats`、`list_versions`、`read_version`、`restore_version`、`export_note`、`batch_notes`、`add_asset`、`get_notes_view`、`set_notes_view`、`mark_note_span`。

## 存储

`store.py` — `NoteStore`(SQLite `notes.db`):

- 每次内容变更生成版本快照(`note_versions`,保留最近 `notes.history.per_note` 个,默认 20)。
- 写入时把 `[[wiki 链接]]` 解析进 `note_links` — 先精确 id,再大小写不敏感标题;悬空链接被丢弃。这支撑 `get_backlinks`。
- 回收站经由 `trashed_ts`;`purge_note`/`empty_trash` 永久删除行。
- 对标题/正文做转义 LIKE 全文检索;基于 PRAGMA 的列迁移。
- 链接助手在 `store_links.py`;TOC、区间标记、校验与保存视图在 `toc.py`/`marks.py`/`validate.py`/`view.py`。

`assets.py` — `AssetStore`:元数据在 SQLite `assets.db`,二进制在工作区下;尺寸上限 `notes.assets.max_mb`(默认 20)。只读附件路由以 `Wiring.extra_router` 挂载(`/api/notes/assets/...`)。

## 后台工作

`wiring.py` 启动 `TrashPruner`:启动时清扫一次,之后每 24 小时一次,依据 `notes.trash.retention_days`(0 = 不动作)。

## 事件

发布 `note.created`、`note.edited`、`note.deleted`、`note.restored`、`note.purged` 与 `notes.ui.changed`。

## 设置

`notes.history.per_note`、`notes.trash.retention_days`、`notes.assets.max_mb`、`notes.editor.autosave_s`、`notes.export.dir`、`notes.list.page_size`、`notes.sort.default`,外加为前端持久化的 UI 状态键(`notes.ui.*`)。
