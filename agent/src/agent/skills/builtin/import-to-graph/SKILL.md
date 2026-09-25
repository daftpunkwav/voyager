# import-to-graph

The workflow for turning a local resource into graph nodes:

1. Import via the `sources` domain (import_repo for repos, save_url for pages) and wait for the `source.ready` event;
2. Enqueue graph building with `graph__enqueue_index` and track progress with `graph__list_index_jobs`;
3. When done, report node/relation counts with `graph__graph_stats` and spot-check key nodes with `graph__query_graph`;
4. For relation questions use `graph__expand_neighbors` / `graph__find_path`; never export the whole graph.
