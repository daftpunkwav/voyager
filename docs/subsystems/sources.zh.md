# Sources 域

[English](sources.md) | 中文

`sources` 域摄取三类参考资料 — GitHub 仓库、文档、网页 — 并提供统一检索。

源码:`packages/sources/src/sources/` — 端口 8010,默认启用;存储 `data/runtime/sources/`(`repo.db`、`doc.db`、`web.db`)。它是除 `llm` 外唯一依赖 `platform_secrets` 的域,也是唯一依赖 `platform_webguard` 的域。

## 能力

`capabilities.py` 是聚合壳:`Registry("sources").merge(repo, doc, web)`;三个扇出能力 `list_sources`、`search_sources`、`sources_stats` 在 `STORES = {"repo", "doc", "web"}` 上聚合(单库上限 2000,合并排序)。

各类:

- **repo**(`modules/repo/`)— `import_repo`、`list_repos`、`sort_repos`、`get_repo`、`get_readme`、`set_repo_meta`、`list_categories`、`remove_repo`、`search_remote_repos`、`list_starred_repos`、`set_github_token`。`github.py` 是 httpx GitHub API 客户端(元数据/README/搜索/starred);token 来自 `SecretStore`;owner/repo 名过严格字符集检查。
- **doc**(`modules/doc/`)— `add_document`、`list_documents`、`get_document`、`get_doc_section`、`search_documents`、`set_document_meta`、`remove_document`。
- **web**(`modules/web/`)— `save_url`、`add_page`、`list_pages`、`get_page`、`set_page_meta`、`remove_page`。

## Worker 与抽取

`worker.py` — `RepoWorker` 把仓库克隆到 `workspace/repo/{owner}__{repo}`(clone 函数可注入供测试);`DocWorker` 异步解析文档。两者在 `Wiring.start`/`stop` 下配合 asyncio 队列运行。

`extract.py` — 分节抽取(`Section(section_no, title, page_start, page_end, text)`),支持 `.pdf`(书签)、`.epub`(spine;zip 炸弹上限 20 MiB/条目、总量 200 MiB)、`.docx` 与纯文本/markdown;失败抛 `ExtractError`。

## URL 抓取

`save_url` 基于 `platform_webguard` 原语(`_assert_pinnable`、`resolve`、`pinned_request`、`read_bounded`)做逐跳 SSRF 防护,每个重定向跳(至多 `_MAX_REDIRECTS`)都重新校验 DNS。该能力声明 `dimension="network"`,agent 调用须过网络策略。标题/摘要/正文/元数据入库。

## 文件预览

`files.py` — `GET /files/doc/{doc_id}`(挂载为 `/api/sources/files/doc/{doc_id}`)以内联 `FileResponse` 提供预览,带媒体类型映射(pdf/epub/docx/txt/md)。

## 事件

发布 `source.added`、`source.removed`、`source.ready`、`task.progress`、`task.failed`。

## 设置

`sources.doc.max_file_mb`、`sources.import.clone`、`sources.sort.default`。
