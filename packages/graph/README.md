# graph

## Purpose

Graph domain: build and query a knowledge graph (nodes/relations) from imported sources; code and L0 pipelines plus an AI guide.

## Configuration

graph.* settings keys (engine choice, queue concurrency).

## Extension Points

New pipeline = one directory under pipelines/ (they must not import each other); engine adapter in engines/.

## Model Experience

Tools: graph__enqueue_index, graph__query_graph, graph__expand_neighbors, graph__find_path, graph__cancel_index, ... Jobs are async (task.* events); queries return bounded subgraphs.

## Known Limitations

C engine is vendored and platform-specific; layout is basic.

## Deferred Work

Incremental graph updates without full re-index.
