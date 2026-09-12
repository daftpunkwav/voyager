/*
 * store.h — Opaque SQLite graph store for code knowledge graphs.
 *
 * All functions are prefixed engine_store_*. The store handle is opaque —
 * callers never touch SQLite internals directly.
 *
 * Thread safety: a single store handle must not be used concurrently.
 * Use one store per thread or external synchronization.
 */
#ifndef ENGINE_STORE_H
#define ENGINE_STORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/* ── Opaque handle ──────────────────────────────────────────────── */

typedef struct engine_store engine_store_t;

/* ── Result codes ───────────────────────────────────────────────── */

#define ENGINE_STORE_OK 0
#define ENGINE_STORE_ERR (-1)
#define ENGINE_STORE_NOT_FOUND (-2)

/* ── Data structures ────────────────────────────────────────────── */

typedef struct {
    int64_t id;
    const char *project;
    const char *label;          /* Function, Class, Method, Module, File, ... */
    const char *name;           /* short name */
    const char *qualified_name; /* full dotted path */
    const char *file_path;      /* relative file path */
    int start_line;
    int end_line;
    const char *properties_json; /* JSON string, NULL → "{}" */
} engine_node_t;

typedef struct {
    int64_t id;
    const char *project;
    int64_t source_id;
    int64_t target_id;
    const char *type;            /* CALLS, HTTP_CALLS, IMPORTS, ... */
    const char *properties_json; /* JSON string, NULL → "{}" */
} engine_edge_t;

typedef struct {
    const char *name;
    const char *indexed_at; /* ISO 8601 */
    const char *root_path;
} engine_project_t;

typedef struct {
    const char *project;
    const char *rel_path;
    const char *sha256;
    int64_t mtime_ns;
    int64_t size;
} engine_file_hash_t;

/* One file's persisted LSP surface: the serialized cross-file definition set
 * (exactly what pass_lsp_cross registration consumes) plus the metadata the
 * closure-repair incremental route needs to decide and bound its work. The
 * store treats defs_json/ref_bloom as opaque; the codec lives with
 * pass_lsp_cross, which is the only writer and reader of their contents. */
typedef struct {
    const char *project;
    const char *rel_path;
    const char *surface_sha; /* sha256 hex of defs_json (the early-cutoff key) */
    const char *defs_json;   /* canonical JSON array of the file's LSP defs */
    const void *ref_bloom;   /* referenced-identifier bloom blob (may be NULL) */
    int ref_bloom_len;
    const char *config_ctx; /* governing-config context hash ("" = none) */
} engine_lsp_surface_row_t;

/* Find nodes overlapping a line range in a file (excludes Module/Package). */
int engine_store_find_nodes_by_file_overlap(engine_store_t *s, const char *project, const char *file_path,
                                         int start_line, int end_line, engine_node_t **out,
                                         int *count);

/* Find nodes whose qualified_name ends with the given suffix (dot-boundary). */
int engine_store_find_nodes_by_qn_suffix(engine_store_t *s, const char *project, const char *suffix,
                                      engine_node_t **out, int *count);

/* Get CALLS degree of a node (inbound and outbound). */
void engine_store_node_degree(engine_store_t *s, int64_t node_id, int *in_deg, int *out_deg);

/* Get distinct file paths for a project. Caller must free each out[i] and out itself.
 * Returns ENGINE_STORE_OK or ENGINE_STORE_ERR. */
int engine_store_list_files(engine_store_t *s, const char *project, char ***out, int *count);

/* Get caller/callee names for a node (CALLS/HTTP_CALLS/ASYNC_CALLS edges).
 * Returns 0 on success. Caller must free each out_callers[i]/out_callees[i]
 * and the arrays themselves. */
int engine_store_node_neighbor_names(engine_store_t *s, int64_t node_id, int limit, char ***out_callers,
                                  int *caller_count, char ***out_callees, int *callee_count);

/* Batch count in/out degree for multiple nodes.
 * edge_type: filter by edge type (e.g. "CALLS"), or NULL/"" for all types.
 * out_in[i] and out_out[i] receive the in/out degree for node_ids[i].
 * Returns ENGINE_STORE_OK or ENGINE_STORE_ERR. */
int engine_store_batch_count_degrees(engine_store_t *s, const int64_t *node_ids, int id_count,
                                  const char *edge_type, int *out_in, int *out_out);

/* Upsert file hashes in batch. */
int engine_store_upsert_file_hash_batch(engine_store_t *s, const engine_file_hash_t *hashes, int count);

/* ── LSP surface rows (closure-repair incremental) ───────────────
 * Upsert/get/delete are whole-row, keyed (project, rel_path). get returns
 * heap rows released with engine_store_free_lsp_surfaces. A project with no
 * rows returns OK with *count == 0 — callers treat that as "no surface
 * data" and route to a full rebuild, which is also the upgrade path for
 * databases written before this table existed. */
int engine_store_upsert_lsp_surface_batch(engine_store_t *s, const engine_lsp_surface_row_t *rows,
                                       int count);
int engine_store_get_lsp_surfaces(engine_store_t *s, const char *project, engine_lsp_surface_row_t **out,
                               int *count);
int engine_store_delete_lsp_surfaces(engine_store_t *s, const char *project);
void engine_store_free_lsp_surfaces(engine_lsp_surface_row_t *rows, int count);

/* Reverse-dependency lookup for closure-repair routing: the DISTINCT
 * file_paths of nodes with at least one edge INTO a node of any file in
 * target_files, excluding the target files themselves. This is "who consumed
 * these files' definitions" as recorded by the previous generation — served
 * by idx_edges_target + idx_nodes_file, so cost tracks the result size, not
 * the graph size. out gets a malloc'd array of malloc'd strings; free with
 * engine_store_free_dependent_files. */
int engine_store_get_dependent_files(engine_store_t *s, const char *project,
                                  const char *const *target_files, int target_count, char ***out,
                                  int *out_count);
void engine_store_free_dependent_files(char **files, int count);

/* Find edges whose properties contain a url_path matching the keyword. */
int engine_store_find_edges_by_url_path(engine_store_t *s, const char *project, const char *keyword,
                                     engine_edge_t **out, int *count);

/* Restore database from another store (backup API). */
int engine_store_restore_from(engine_store_t *dst, engine_store_t *src);

/* Copy a transactionally-consistent snapshot, including committed WAL frames,
 * from an existing DB into a same-directory staging path. */
int engine_store_backup_path(const char *source_path, const char *staging_path);

/* Seal a staging DB into one self-contained main file before atomic publish.
 * The store must have no concurrent users. */
int engine_store_prepare_for_publish(engine_store_t *s);

/* Checkpoint and detach sidecars from an existing destination immediately
 * before replacement. Fails closed while another process prevents sealing. */
int engine_store_prepare_path_for_replace(const char *path);

/* ── Search ─────────────────────────────────────────────────────── */

typedef struct {
    const char *project;
    const char *label;        /* NULL = any label */
    const char *name_pattern; /* regex on name, NULL = any */
    const char *qn_pattern;   /* regex on qualified_name, NULL = any */
    const char *file_pattern; /* glob on file_path, NULL = any */
    const char *relationship; /* edge type filter, NULL = any */
    const char *direction;    /* "inbound" / "outbound" / "any", NULL = any */
    int min_degree;           /* -1 = no filter (default), 0+ = minimum */
    int max_degree;           /* -1 = no filter (default), 0+ = maximum */
    int limit;                /* 0 = default (10) */
    int offset;
    bool exclude_entry_points;
    bool include_connected;
    const char *sort_by; /* "relevance" / "name" / "degree", NULL = relevance */
    bool case_sensitive;
    const char **exclude_labels; /* NULL-terminated array, or NULL */
} engine_search_params_t;

typedef struct {
    engine_node_t node;
    int in_degree;
    int out_degree;
    /* connected_names: allocated array of strings, count in connected_count */
    const char **connected_names;
    int connected_count;
} engine_search_result_t;

typedef struct {
    engine_search_result_t *results;
    int count;
    int total; /* total before pagination */
} engine_search_output_t;

/* ── Traversal ──────────────────────────────────────────────────── */

typedef struct {
    engine_node_t node;
    int hop; /* BFS depth from root */
} engine_node_hop_t;

typedef struct {
    const char *from_name;
    const char *to_name;
    const char *type;
    double confidence;
    int64_t source_id; /* edge endpoints — let callers match an edge to a hop node */
    int64_t target_id;
    const char *properties_json; /* raw edge properties (carries CALLS arg expressions) */
} engine_edge_info_t;

typedef struct {
    engine_node_t root;
    engine_node_hop_t *visited;
    int visited_count;
    engine_edge_info_t *edges;
    int edge_count;
} engine_traverse_result_t;

/* ── Schema introspection ───────────────────────────────────────── */

typedef struct {
    const char *label;
    int count;
    char **properties; /* distinct property keys for this label (base + JSON) */
    int property_count;
} engine_label_count_t;

typedef struct {
    const char *type;
    int count;
    char **properties; /* distinct property keys for this edge type (base + JSON) */
    int property_count;
} engine_type_count_t;

typedef struct {
    engine_label_count_t *node_labels;
    int node_label_count;
    engine_type_count_t *edge_types;
    int edge_type_count;
    /* relationship patterns like "(Function)-[CALLS]->(Function) [123x]" */
    const char **rel_patterns;
    int rel_pattern_count;
    const char **sample_func_names;
    int sample_func_count;
    const char **sample_class_names;
    int sample_class_count;
    const char **sample_qns;
    int sample_qn_count;
} engine_schema_info_t;

/* ── Lifecycle ──────────────────────────────────────────────────── */

/* Open an in-memory database (for testing). */
engine_store_t *engine_store_open_memory(void);

/* Open a file-backed database at the given path. Creates if needed. */
engine_store_t *engine_store_open_path(const char *db_path);

/* Open an existing file-backed database read-write without CREATE. Intended
 * for coordinated mutations where a missing/typo path must never materialize
 * a ghost database. Returns NULL when the file does not exist. */
engine_store_t *engine_store_open_path_existing(const char *db_path);

/* Open an existing file-backed database for querying only. Opened READ-ONLY
 * (no SQLITE_OPEN_CREATE, no write pragmas) so queries never mutate the DB and
 * work on a read-only file / filesystem. Returns NULL if the file does not
 * exist — never creates a new .db file. */
engine_store_t *engine_store_open_path_query(const char *db_path);

/* Validate and seal an existing DB for atomic replacement without creating or
 * migrating its schema. Returns OK when sealed, NOT_FOUND when the bytes are
 * definitely corrupt/incompatible and should be quarantined, or ERR when the
 * file is busy/unavailable and must be left in place. */
int engine_store_seal_existing_path_for_replace(const char *db_path);

/* On-disk path of a file-backed store, or NULL for an in-memory (:memory:)
 * store. The returned pointer is owned by the store. */
const char *engine_store_db_path(const engine_store_t *s);

/* Check database integrity. Returns true if the DB passes basic sanity checks
 * (projects table has correct types, no corruption indicators).
 * Returns false if corruption is detected — caller should delete and re-index. */
bool engine_store_check_integrity(engine_store_t *s);
/* Shallow check + PRAGMA quick_check — catches page-level corruption.
 * O(db size); use on rare paths (artifact import), not hot opens. */
bool engine_store_check_integrity_deep(engine_store_t *s);

/* Open database for a named project in the default cache dir. */
engine_store_t *engine_store_open(const char *project);

/* Close the store and free all resources. NULL-safe. */
void engine_store_close(engine_store_t *s);

/* Get the underlying sqlite3 handle (for testing only). */
struct sqlite3 *engine_store_get_db(engine_store_t *s);

/* Get the last error message (static string, valid until next call). */
const char *engine_store_error(engine_store_t *s);

/* ── Transaction ────────────────────────────────────────────────── */

/* Begin a transaction. Returns ENGINE_STORE_OK on success. */
int engine_store_begin(engine_store_t *s);

/* Commit the current transaction. */
int engine_store_commit(engine_store_t *s);

/* Rollback the current transaction. */
int engine_store_rollback(engine_store_t *s);

/* ── Bulk write optimization ────────────────────────────────────── */

/* Tune pragmas for bulk write throughput (synchronous=OFF, large cache).
 * WAL journal mode is preserved throughout for crash safety. */
int engine_store_begin_bulk(engine_store_t *s);

/* Restore normal pragmas (synchronous=NORMAL, default cache) after bulk writes. */
int engine_store_end_bulk(engine_store_t *s);

/* Drop user indexes for faster bulk inserts. */
int engine_store_drop_indexes(engine_store_t *s);

/* Recreate user indexes after bulk inserts. */
int engine_store_create_indexes(engine_store_t *s);

/* ── WAL / Checkpoint ───────────────────────────────────────────── */

/* Force WAL checkpoint + PRAGMA optimize. */
int engine_store_checkpoint(engine_store_t *s);

/* #1083: the WAL size limit (journal_size_limit) applied to this write
 * connection, in bytes; -1 = unlimited (SQLite default / pre-fix). */
int64_t engine_store_journal_size_limit(engine_store_t *s);

/* Opaque store generation for pagination-cursor staleness detection:
 * "u<db_uid>g<mutation_gen>" — db_uid is minted per DB file, mutation_gen
 * bumps on every index run. "legacy" for DBs predating store_meta. */
int engine_store_generation(engine_store_t *s, char *buf, size_t bufsz);

/* Seal a fully-written staging database before atomic publication.
 * Raises synchronous to FULL, requires an exclusive TRUNCATE checkpoint to
 * complete, then leaves the database in verified DELETE journal mode so the
 * main file is self-contained (no required -wal/-shm sidecars). This is a
 * fail-closed operation: SQLITE_BUSY and an unconfirmed mode transition are
 * errors. The caller must own the staging database exclusively. */
int engine_store_seal_for_atomic_publish(engine_store_t *s);

/* Resolve the mmap_size pragma value applied to on-disk stores from the
 * ENGINE_SQLITE_MMAP_SIZE environment variable. Defaults to 67108864 (64 MB)
 * when the variable is unset, malformed, or partially numeric. Negative
 * values clamp to 0 (which disables mmap and reverts to read()/pread()
 * I/O — recoverable SQLITE_IOERR instead of SIGBUS when concurrent
 * processes truncate the DB file under live mappings). Exposed for
 * testability. */
int64_t engine_store_resolve_mmap_size(void);

/* ── Dump / Restore ─────────────────────────────────────────────── */

/* Dump in-memory database to a file. */
int engine_store_dump_to_file(engine_store_t *s, const char *dest_path);

/* ── Project CRUD ───────────────────────────────────────────────── */

int engine_store_upsert_project(engine_store_t *s, const char *name, const char *root_path);
int engine_store_get_project(engine_store_t *s, const char *name, engine_project_t *out);
int engine_store_list_projects(engine_store_t *s, engine_project_t **out, int *count);
int engine_store_delete_project(engine_store_t *s, const char *name);

/* ── Node CRUD ──────────────────────────────────────────────────── */

/* Upsert a single node. Returns node ID (>0) or ENGINE_STORE_ERR. */
int64_t engine_store_upsert_node(engine_store_t *s, const engine_node_t *n);

/* Upsert nodes in batch. out_ids must have room for count entries. */
int engine_store_upsert_node_batch(engine_store_t *s, const engine_node_t *nodes, int count,
                                int64_t *out_ids);

/* Find node by primary key. Returns ENGINE_STORE_OK or ENGINE_STORE_NOT_FOUND. */
int engine_store_find_node_by_id(engine_store_t *s, int64_t id, engine_node_t *out);

/* Find node by project + qualified_name. */
int engine_store_find_node_by_qn(engine_store_t *s, const char *project, const char *qn, engine_node_t *out);

/* Find node by qualified_name only (no project filter — QNs are globally unique). */
int engine_store_find_node_by_qn_any(engine_store_t *s, const char *qn, engine_node_t *out);

/* Find nodes by name (exact match). Returns allocated array, caller frees. */
int engine_store_find_nodes_by_name(engine_store_t *s, const char *project, const char *name,
                                 engine_node_t **out, int *count);

/* Find nodes by name across all projects. Returns allocated array, caller frees. */
int engine_store_find_nodes_by_name_any(engine_store_t *s, const char *name, engine_node_t **out,
                                     int *count);

/* Find nodes by label. */
int engine_store_find_nodes_by_label(engine_store_t *s, const char *project, const char *label,
                                  engine_node_t **out, int *count);

/* Find nodes by file path. */
int engine_store_find_nodes_by_file(engine_store_t *s, const char *project, const char *file_path,
                                 engine_node_t **out, int *count);

/* Batch lookup: map qualified names → node IDs.
 * qns[i] is resolved; out_ids[i] receives the ID or 0 if not found.
 * Returns number of QNs actually found, or ENGINE_STORE_ERR. */
int engine_store_find_node_ids_by_qns(engine_store_t *s, const char *project, const char **qns,
                                   int qn_count, int64_t *out_ids);

/* Count nodes in project. Returns count or ENGINE_STORE_ERR. */
int engine_store_count_nodes(engine_store_t *s, const char *project);

int engine_store_count_nodes_scoped(engine_store_t *s, const char *project, const char *path);

int engine_store_count_edges_scoped(engine_store_t *s, const char *project, const char *path);

/* True when path is a non-empty scope after normalization (issue #604). */
bool engine_store_arch_path_scoped(const char *path);

/* When scoped, writes normalized directory prefix into norm_out. Returns false if unscoped. */
bool engine_store_normalize_arch_path(const char *path, char *norm_out, size_t norm_sz);

/* True when architecture aspect `name` belongs to the "overview" subset:
 * every aspect EXCEPT the large per-file listing (file_tree). Shared by both
 * aspect gates — want_aspect (store.c) and aspect_wanted (mcp.c) — so the
 * two sites cannot drift. */
bool engine_store_arch_aspect_in_overview(const char *name);

/* Delete all nodes for a project (cascade deletes edges). */
int engine_store_delete_nodes_by_project(engine_store_t *s, const char *project);

/* Delete nodes by file path. */
int engine_store_delete_nodes_by_file(engine_store_t *s, const char *project, const char *file_path);

/* Delete nodes by label. */
int engine_store_delete_nodes_by_label(engine_store_t *s, const char *project, const char *label);

/* ── Edge CRUD ──────────────────────────────────────────────────── */

/* Insert or update edge. Returns edge ID (>0) or ENGINE_STORE_ERR. */
int64_t engine_store_insert_edge(engine_store_t *s, const engine_edge_t *e);

/* Insert edges in batch. */
int engine_store_insert_edge_batch(engine_store_t *s, const engine_edge_t *edges, int count);

/* Fetch all CALLS edges among Function/Method nodes for a project as parallel
 * (source_id, target_id) arrays (caller frees both). For SCC / cycle analysis.
 * Stops at max_edges and sets *truncated — never a silent cap. Returns
 * ENGINE_STORE_OK (or _ERR); *count is the number returned. */
int engine_store_fetch_call_edges(engine_store_t *s, const char *project, int max_edges,
                               int64_t **out_src, int64_t **out_tgt, int *count, bool *truncated);

/* Find edges by source node. */
int engine_store_find_edges_by_source(engine_store_t *s, int64_t source_id, engine_edge_t **out, int *count);

/* Find edges by target node. */
int engine_store_find_edges_by_target(engine_store_t *s, int64_t target_id, engine_edge_t **out, int *count);

/* Find edges by source + type. */
int engine_store_find_edges_by_source_type(engine_store_t *s, int64_t source_id, const char *type,
                                        engine_edge_t **out, int *count);

/* Find edges by target + type. */
int engine_store_find_edges_by_target_type(engine_store_t *s, int64_t target_id, const char *type,
                                        engine_edge_t **out, int *count);

/* Find all edges of a type in project. */
int engine_store_find_edges_by_type(engine_store_t *s, const char *project, const char *type,
                                 engine_edge_t **out, int *count);

/* Count all edges in project. */
int engine_store_count_edges(engine_store_t *s, const char *project);

/* Count edges of given type. */
int engine_store_count_edges_by_type(engine_store_t *s, const char *project, const char *type);

/* Delete all edges for a project. */
int engine_store_delete_edges_by_project(engine_store_t *s, const char *project);

/* Delete edges by type. */
int engine_store_delete_edges_by_type(engine_store_t *s, const char *project, const char *type);

/* ── File hash CRUD ─────────────────────────────────────────────── */

int engine_store_upsert_file_hash(engine_store_t *s, const char *project, const char *rel_path,
                               const char *sha256, int64_t mtime_ns, int64_t size);

int engine_store_get_file_hashes(engine_store_t *s, const char *project, engine_file_hash_t **out,
                              int *count);

/* Fetch one exact file-hash record. The returned strings are heap-owned and
 * must be released with engine_store_clear_file_hash(). */
int engine_store_get_file_hash(engine_store_t *s, const char *project, const char *rel_path,
                            engine_file_hash_t *out);

/* Free heap-owned fields in one exact file-hash record and zero it. */
void engine_store_clear_file_hash(engine_file_hash_t *hash);

int engine_store_delete_file_hash(engine_store_t *s, const char *project, const char *rel_path);

int engine_store_delete_file_hashes(engine_store_t *s, const char *project);

/* ── Index coverage (#963) ──────────────────────────────────────── */

/* One best-effort coverage row: a file the indexer could not fully cover.
 * kind "parse_partial" = indexed but the parse tree had ERROR/MISSING regions
 * (detail = 1-based line ranges "12-40,88-90"); skip kinds "read"/"extract"/
 * "oversized" = not indexed at all (detail = reason). Stored in the separate
 * index_coverage table — coverage is metadata ABOUT the graph, never mixed
 * into the graph itself. */
typedef struct {
    const char *rel_path;
    const char *kind;
    const char *detail;
} engine_coverage_row_t;

/* Metadata describing how completely one index run recorded the best-effort
 * coverage signal. `recording_status` is "complete", "truncated", or
 * "unavailable"; it is deliberately separate from hash_records_complete.
 * Strings returned by engine_store_coverage_meta_get are heap-owned. */
typedef struct {
    const char *project;
    const char *generation;
    const char *index_mode;
    const char *recorded_at;
    const char *recording_status;
    int ignored_files_stored;
    int ignored_files_total;
    int coverage_version;
    bool hash_records_complete;
} engine_coverage_meta_t;

/* Replace the project's coverage rows in one transaction, then prune rows for
 * files absent from file_hashes (deleted from the repo). Call AFTER hashes
 * were persisted for the run. */
int engine_store_coverage_replace(engine_store_t *s, const char *project, const engine_coverage_row_t *rows,
                               int count);

/* Replace coverage rows and their run metadata atomically. Passing NULL meta
 * clears any older metadata so it cannot be mistaken for the new row set. */
int engine_store_coverage_replace_ex(engine_store_t *s, const char *project,
                                  const engine_coverage_row_t *rows, int count,
                                  const engine_coverage_meta_t *meta);

/* Fetch all coverage rows (ordered by rel_path). Caller frees via
 * engine_store_free_coverage. */
int engine_store_coverage_get(engine_store_t *s, const char *project, engine_coverage_row_t **out,
                           int *count);

/* Fetch coverage rows for one path. Exact rows are returned together with any
 * not_indexed_dir ancestor that covers the path. */
int engine_store_coverage_get_path(engine_store_t *s, const char *project, const char *rel_path,
                                engine_coverage_row_t **out, int *count);

/* Fetch coverage rows at/below a directory scope, plus a not_indexed_dir
 * ancestor that covers the scope. Prefix matching is segment-boundary safe. */
int engine_store_coverage_get_scope(engine_store_t *s, const char *project, const char *scope,
                                 engine_coverage_row_t **out, int *count);

/* Fetch/free the metadata paired with the current coverage row set. */
int engine_store_coverage_meta_get(engine_store_t *s, const char *project, engine_coverage_meta_t *out);
void engine_store_coverage_meta_clear(engine_coverage_meta_t *meta);

/* Name of the derived miss-graph shadow project ("<project>::missed").
 * engine_store_coverage_replace materializes the coverage rows as a file-
 * structure graph (Project → Folder → File{kind, detail}) under this project
 * name — queryable via the normal cypher path without touching the real
 * project's graph. */
void engine_store_coverage_shadow_project(char *dst, size_t dstsz, const char *project);

void engine_store_free_coverage(engine_coverage_row_t *rows, int count);

/* ── Search ─────────────────────────────────────────────────────── */

int engine_store_search(engine_store_t *s, const engine_search_params_t *params, engine_search_output_t *out);

/* Free a search output's allocated memory. */
void engine_store_search_free(engine_search_output_t *out);

/* ── Traversal ──────────────────────────────────────────────────── */

int engine_store_bfs(engine_store_t *s, int64_t start_id, const char *direction, const char **edge_types,
                  int edge_type_count, int max_depth, int max_results, engine_traverse_result_t *out);

/* Multi-source BFS from ALL seed ids at once (one CTE, temp-table anchored).
 * Seeds are EXCLUDED from the result (impact semantics); MIN(hop) across the
 * seed set; canonical (hop,id) order; *truncated set when the max_results
 * memory-safety ceiling was hit (counting is otherwise uncapped). */
int engine_store_bfs_multi(engine_store_t *s, const int64_t *seed_ids, int seed_count,
                        const char *direction, const char **edge_types, int edge_type_count,
                        int max_depth, int max_results, engine_traverse_result_t *out,
                        bool *truncated);

/* Free a traverse result's allocated memory. */
void engine_store_traverse_free(engine_traverse_result_t *out);

/* ── Impact analysis ────────────────────────────────────────────── */

typedef enum {
    ENGINE_RISK_CRITICAL = 0,
    ENGINE_RISK_HIGH = 1,
    ENGINE_RISK_MEDIUM = 2,
    ENGINE_RISK_LOW = 3,
} engine_risk_level_t;

/* Map BFS hop depth to risk level. */
engine_risk_level_t engine_hop_to_risk(int hop);

/* String representation of risk level. */
const char *engine_risk_label(engine_risk_level_t level);

typedef struct {
    int critical;
    int high;
    int medium;
    int low;
    int total;
    bool has_cross_service;
} engine_impact_summary_t;

/* Build impact summary from visited hops and edges. */
engine_impact_summary_t engine_build_impact_summary(const engine_node_hop_t *hops, int hop_count,
                                              const engine_edge_info_t *edges, int edge_count);

/* Deduplicate BFS hops, keeping minimum hop per node ID.
 * Returns allocated array and count via out params. Caller frees result. */
int engine_deduplicate_hops(const engine_node_hop_t *hops, int hop_count, engine_node_hop_t **out,
                         int *out_count);

/* ── Schema ─────────────────────────────────────────────────────── */

int engine_store_get_schema(engine_store_t *s, const char *project, engine_schema_info_t *out);

/* Like engine_store_get_schema but skips per-label/per-type JSON property-key
 * discovery (json_each scans over every row) — for callers that only need
 * label/type counts, e.g. get_architecture. */
int engine_store_get_schema_counts(engine_store_t *s, const char *project, engine_schema_info_t *out);

int engine_store_get_schema_counts_scoped(engine_store_t *s, const char *project, const char *path,
                                       engine_schema_info_t *out);

/* Free a schema info's allocated memory. */
void engine_store_schema_free(engine_schema_info_t *out);

/* ── Architecture ───────────────────────────────────────────────── */

typedef struct {
    const char *language;
    int file_count;
} engine_language_count_t;

typedef struct {
    const char *name;
    int node_count;
    int fan_in;
    int fan_out;
} engine_package_summary_t;

typedef struct {
    const char *name;
    const char *qualified_name;
    const char *file;
} engine_entry_point_t;

typedef struct {
    const char *method;
    const char *path;
    const char *handler;
} engine_route_info_t;

typedef struct {
    const char *name;
    const char *qualified_name;
    int fan_in;
} engine_hotspot_t;

typedef struct {
    const char *from;
    const char *to;
    int call_count;
} engine_cross_pkg_boundary_t;

typedef struct {
    const char *from;
    const char *to;
    const char *type;
    int count;
} engine_service_link_t;

typedef struct {
    const char *name;
    const char *layer;
    const char *reason;
} engine_package_layer_t;

typedef struct {
    int id;
    const char *label;
    int members;
    double cohesion;
    const char **top_nodes;
    int top_node_count;
    const char **packages;
    int package_count;
    const char **edge_types;
    int edge_type_count;
} engine_cluster_info_t;

typedef struct {
    const char *path;
    const char *type; /* "dir" or "file" */
    int children;
} engine_file_tree_entry_t;

typedef struct {
    /* Pointers first to minimize padding */
    engine_language_count_t *languages;
    engine_package_summary_t *packages;
    engine_entry_point_t *entry_points;
    engine_route_info_t *routes;
    engine_hotspot_t *hotspots;
    engine_cross_pkg_boundary_t *boundaries;
    engine_service_link_t *services;
    engine_package_layer_t *layers;
    engine_cluster_info_t *clusters;
    engine_file_tree_entry_t *file_tree;
    /* Counts after pointers */
    int language_count;
    int package_count;
    int entry_point_count;
    int route_count;
    int hotspot_count;
    int boundary_count;
    int service_count;
    int layer_count;
    int cluster_count;
    int file_tree_count;
} engine_architecture_info_t;

int engine_store_get_architecture(engine_store_t *s, const char *project, const char *path,
                               const char **aspects, int aspect_count,
                               engine_architecture_info_t *out);
void engine_store_architecture_free(engine_architecture_info_t *out);

/* ── ADR (Architecture Decision Record) ────────────────────────── */

#define ENGINE_ADR_MAX_LENGTH 8000

typedef struct {
    const char *project;
    const char *content;
    const char *created_at;
    const char *updated_at;
} engine_adr_t;

int engine_store_adr_store(engine_store_t *s, const char *project, const char *content);
int engine_store_adr_get(engine_store_t *s, const char *project, engine_adr_t *out);
int engine_store_adr_delete(engine_store_t *s, const char *project);
int engine_store_adr_update_sections(engine_store_t *s, const char *project, const char **keys,
                                  const char **values, int count, engine_adr_t *out);
void engine_store_adr_free(engine_adr_t *adr);

/* ADR section parsing/rendering (pure functions, no store needed) */

enum { PROPS_MAX = 16 };

typedef struct {
    char *keys[PROPS_MAX];
    char *values[PROPS_MAX];
    int count;
} engine_adr_sections_t;

engine_adr_sections_t engine_adr_parse_sections(const char *content);
char *engine_adr_render(const engine_adr_sections_t *sections);
int engine_adr_validate_content(const char *content, char *errbuf, int errbuf_size);
int engine_adr_validate_section_keys(const char **keys, int count, char *errbuf, int errbuf_size);
void engine_adr_sections_free(engine_adr_sections_t *s);

/* ── Search helpers (exposed for testing) ───────────────────────── */

/* Convert a glob pattern to SQL LIKE pattern. Caller must free result. */
char *engine_glob_to_like(const char *pattern);

/* Extract literal substrings (>= 3 chars) from a regex pattern for LIKE pre-filtering.
 * Bails on alternation (|). Returns count of hints written to out[].
 * Each out[i] is malloc'd — caller must free each string. */
int engine_extract_like_hints(const char *pattern, char **out, int max_out);

/* Prepend (?i) to a regex pattern if not already present.
 * Returns a static buffer — do NOT free. */
const char *engine_ensure_case_insensitive(const char *pattern);

/* Strip leading (?i) from a regex pattern.
 * Returns a static buffer — do NOT free. */
const char *engine_strip_case_flag(const char *pattern);

/* ── Architecture helpers (exposed for testing) ────────────────── */

const char *engine_qn_to_package(const char *qn);
const char *engine_qn_to_top_package(const char *qn);
bool engine_is_test_file_path(const char *fp);
int engine_store_find_architecture_docs(engine_store_t *s, const char *project, char ***out, int *count);

/* ── Community detection (Leiden) ──────────────────────────────── */

typedef struct {
    int64_t src;
    int64_t dst;
} engine_louvain_edge_t;

typedef struct {
    int64_t node_id;
    int community;
} engine_louvain_result_t;

/* Multi-level Leiden community detection (Traag, Waltman & van Eck 2019,
 * arXiv:1810.08473): local moving + refinement + aggregation, repeated until
 * the partition can no longer be coarsened. Refinement guarantees every
 * reported community is internally connected. The resolution parameter
 * controls granularity (higher -> more, smaller communities); 1.0 is standard.
 * Allocates *out (length *out_count == node_count); the caller frees it. */
int engine_leiden(const int64_t *nodes, int node_count, const engine_louvain_edge_t *edges,
               int edge_count, double resolution, engine_louvain_result_t **out, int *out_count);

/* Convenience wrapper: engine_leiden with resolution 1.0. */
int engine_louvain(const int64_t *nodes, int node_count, const engine_louvain_edge_t *edges,
                int edge_count, engine_louvain_result_t **out, int *out_count);

/* ── Memory management helpers ──────────────────────────────────── */

/* Free heap-allocated strings in a stack-allocated node (does NOT free the node itself). */
void engine_node_free_fields(engine_node_t *n);

/* Free heap-allocated strings in a stack-allocated project (does NOT free the project itself). */
void engine_project_free_fields(engine_project_t *p);

/* Free an array of nodes returned by find_nodes_by_* functions. */
void engine_store_free_nodes(engine_node_t *nodes, int count);

/* Free an array of edges returned by find_edges_by_* functions. */
void engine_store_free_edges(engine_edge_t *edges, int count);

/* Free an array of projects. */
void engine_store_free_projects(engine_project_t *projects, int count);

/* Free an array of file hashes. */
void engine_store_free_file_hashes(engine_file_hash_t *hashes, int count);

/* ── Vector search ───────────────────────────────────────────────── */

/* Result from vector similarity search. */
typedef struct {
    int64_t node_id;
    char *name;
    char *qualified_name;
    char *file_path;
    char *label;
    double score;
} engine_vector_result_t;

/* Search for nodes similar to the given query keywords using stored RI vectors.
 * Builds a merged query vector from the keywords, then does cosine scan via
 * the engine_cosine_i8 SQL function joined with the nodes table.
 * Returns results sorted by score DESC. Caller must free with engine_store_free_vector_results. */
int engine_store_vector_search(engine_store_t *s, const char *project, const char **keywords,
                            int keyword_count, int limit, engine_vector_result_t **out,
                            int *out_count);

/* Free vector search results. */
void engine_store_free_vector_results(engine_vector_result_t *results, int count);

/* Count vectors for a project. */
int engine_store_count_vectors(engine_store_t *s, const char *project);

/* Execute an arbitrary SQL statement (pragmas, FTS5 maintenance, etc).
 * Returns ENGINE_STORE_OK on success. */
int engine_store_exec(engine_store_t *s, const char *sql);

#endif /* ENGINE_STORE_H */
