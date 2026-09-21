# Graph 域

[English](graph.md) | 中文

`graph` 域构建并服务知识图谱:由代码分析与 AI 原语写入的规范存储、仓库摄取的索引队列、可插拔引擎(C sidecar + Python 回退)。

源码:`packages/graph/src/graph/` — 端口 8030,默认启用;`depends_on: ["sources"]`(各域中唯一非空 `depends_on`);存储 `data/runtime/graph/`(`graph.db`、`index.db`、`engine-python/`)。

## 能力

`Registry("graph")` — 21 个能力,三组:

- 队列:`enqueue_index`(把 `repo_path` 关进 `workspace/` 内)、`enqueue_l0`、`l0_view`、`cancel_index`、`reorder_queue`、`list_index_jobs`
- AI 写原语:`set_node`、`set_relationship`、`set_nodes`、`set_relationships`、`merge_nodes`、`graph_guide`
- 读取:`query_graph`、`get_subgraph`、`graph_stats`、`list_projects`、`engine_info`、`drop_project_graph`、`expand_neighbors`、`find_path`、`export_subgraph`

## 存储

`store.py` — `GraphStore`(SQLite `graph.db`):`nodes`(唯一 `(project, label, qualified_name)`)与 `edges`(唯一 `(project, src, dst, type)`),每行携带溯源 `source` ∈ `code`/`ai`/`manual`。粗粒度操作在 `operations.py`,行/列助手在 `columns.py`。

`index_queue.py` — `IndexQueue`(SQLite `index.db`,`index_jobs` 表):带优先级的队列,状态机(`queued → running → done/failed/cancelled`),`level`(`l1` 单仓库 / `l0` 跨资源)与 `kinds` 列由 `_migrate` 添加。

## 引擎

`engines/adapter.py` — `EngineAdapter` 按设置 `graph.engine.mode`(`auto`/`c`/`python`)选择引擎:

- **C sidecar** — `engines/c/client.py` `CEngineClient` 走 HTTP,默认 `http://127.0.0.1:8123`(`graph.engine.c_url`)。sidecar 是独立进程(默认端口 9750,见 `engines/c/core/README.md`),**不会被自动拉起**——`auto` 模式下健康探测不通即回落 Python。目前 Voyager 实际只使用 `/api/index`、`/api/index-status` 与 `/api/project-health` 三个端点。
- **Python 回退** — `engines/python/engine.py` `GraphEngine`,含 `engine_search`/`engine_query`/`engine_architecture` 子模块与按语言索引器(`engines/python/indexer/`:python、jsts、markdown、正则回退);数据根 `data/runtime/graph/engine-python/` 加 `data/graph-db/`。

C 引擎不可用时,适配器在总线上发布 `graph.engine.fallback`。

## 管线

- `pipelines/code/analyze.py` — `analyze_repo`:引擎索引 → 以 `source="code"` 导入规范存储,随后自动关系分析。注意:导出步骤调用的 `export_graph` 目前只有 Python 引擎实现——若选中 C sidecar(且可达)该步会失败;sidecar 休眠期间的已知缺口。
- `pipelines/l0/relate.py` — `run_l0`:跨资源关系,经注入的 `call_sync("sources", "list_sources", ...)` 取来源 — graph 从不 import sources。
- `pipelines/ai/guide.py` — 校验 AI 写入的节点与关系。

## 调度器

`scheduler.py` — `IndexScheduler` 轮询队列,在并发信号量下执行任务(`graph.index.concurrency`,1–4),按指数退避重试(`graph.index.max_attempts`),并发出 `task.*` 事件。

## 设置

`graph.engine.mode`、`graph.engine.c_url`、`graph.index.concurrency`、`graph.index.max_attempts`、`graph.query.default_limit`。
