# Sources domain

English | [中文](sources.zh.md)

The `sources` domain ingests reference material in three kinds — GitHub repositories, documents, and web pages — and serves unified search over them.

Source: `packages/sources/src/sources/` — port 8010, enabled by default; store `data/runtime/sources/` (`repo.db`, `doc.db`, `web.db`). It is the only domain besides `llm` that depends on `platform_secrets`, and the only one on `platform_webguard`.

## Capabilities

`capabilities.py` is an aggregate shell: `Registry("sources").merge(repo, doc, web)`; three fan-out capabilities `list_sources`, `search_sources`, `sources_stats` aggregate over `STORES = {"repo", "doc", "web"}` (per-store cap 2000, merged sort).

Per kind:

- **repo** (`modules/repo/`) — `import_repo`, `list_repos`, `sort_repos`, `get_repo`, `get_readme`, `set_repo_meta`, `list_categories`, `remove_repo`, `search_remote_repos`, `list_starred_repos`, `set_github_token`. `github.py` is an httpx GitHub API client (metadata/README/search/starred); tokens come from `SecretStore`; owner/repo names pass a strict charset check.
- **doc** (`modules/doc/`) — `add_document`, `list_documents`, `get_document`, `get_doc_section`, `search_documents`, `set_document_meta`, `remove_document`.
- **web** (`modules/web/`) — `save_url`, `add_page`, `list_pages`, `get_page`, `set_page_meta`, `remove_page`.

## Workers and extraction

`worker.py` — `RepoWorker` clones repositories into `workspace/repo/{owner}__{repo}` (clone function injectable for tests); `DocWorker` parses documents asynchronously. Both run under `Wiring.start`/`stop` with asyncio queues.

`extract.py` — section extraction (`Section(section_no, title, page_start, page_end, text)`) for `.pdf` (bookmarks), `.epub` (spine; zip-bomb caps at 20 MiB/entry, 200 MiB total), `.docx`, and plain text/markdown; failures raise `ExtractError`.

## URL capture

`save_url` fetches with per-hop SSRF protection built on `platform_webguard` primitives (`_assert_pinnable`, `resolve`, `pinned_request`, `read_bounded`), re-validating DNS on every redirect hop up to `_MAX_REDIRECTS`. The capability declares `dimension="network"`, so agent calls pass the network policy. Title/summary/content/meta are stored.

## File preview

`files.py` — `GET /files/doc/{doc_id}` (mounted as `/api/sources/files/doc/{doc_id}`) serves an inline `FileResponse` preview with a media-type map (pdf/epub/docx/txt/md).

## Events

Publishes `source.added`, `source.removed`, `source.ready`, `task.progress`, `task.failed`.

## Settings

`sources.doc.max_file_mb`, `sources.import.clone`, `sources.sort.default`.
