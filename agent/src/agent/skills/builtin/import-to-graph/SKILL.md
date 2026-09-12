# import-to-graph(导入建图)

把一份本地资料变成图谱节点的流程:

1. `sources` 域导入(仓库用 import_repo,网页用 save_url),等 `source.ready` 事件;
2. `graph__enqueue_index` 入队建图,`graph__list_index_jobs` 看进度;
3. 完成后 `graph__graph_stats` 汇报节点/关系数,`graph__query_graph` 抽查关键节点;
4. 用户要找关系时用 `graph__expand_neighbors` / `graph__find_path`,不要整图导出。
