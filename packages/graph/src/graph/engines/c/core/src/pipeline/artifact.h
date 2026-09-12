/*
 * artifact.h — Persistent artifact export/import for team sharing.
 *
 * Exports the SQLite knowledge graph as a zstd-compressed artifact
 * to .graph-engine/graph.db.zst in the repository. Teammates
 * can import the artifact to bootstrap their local index instead
 * of running a full pipeline from scratch.
 */
#ifndef ENGINE_ARTIFACT_H
#define ENGINE_ARTIFACT_H

#include <stdbool.h>

/* Schema version — increment when DB schema changes (new tables/indexes).
 * Import refuses artifacts with schema_version > current.
 * v2: edges uniqueness widened to (source_id, target_id, type,
 *     local_name_gen) so sibling named imports coexist (#768) — old
 *     binaries cannot upsert against the widened constraint. */
#define ENGINE_ARTIFACT_SCHEMA_VERSION 2

#define ENGINE_ARTIFACT_FILENAME "graph.db.zst"
#define ENGINE_ARTIFACT_META "artifact.json"
#define ENGINE_ARTIFACT_DIR ".graph-engine"

/* Export quality levels */
enum {
    ENGINE_ARTIFACT_FAST = 0, /* zstd -3, no index stripping (watcher path) */
    ENGINE_ARTIFACT_BEST = 1, /* zstd -9 + drop indexes + VACUUM INTO (explicit index) */
};

/* Export DB to .graph-engine/graph.db.zst artifact.
 * quality: ENGINE_ARTIFACT_FAST or ENGINE_ARTIFACT_BEST.
 * Creates .graph-engine/ dir, .gitattributes, and artifact.json.
 * Returns 0 on success, -1 on error. */
int engine_artifact_export(const char *db_path, const char *repo_path, const char *project_name,
                        int quality);

/* Get details for the most recent export failure on this thread.
 * Returns NULL if no export error is recorded. */
const char *engine_artifact_export_last_error(void);

/* Import artifact from .graph-engine/graph.db.zst to cache_db_path.
 * Decompresses, runs integrity check, recreates indexes.
 * Returns 0 on success, -1 on error. */
int engine_artifact_import(const char *repo_path, const char *cache_db_path);

/* Check if a compatible artifact exists in repo_path/.graph-engine/.
 * Returns true only if both graph.db.zst and artifact.json exist
 * and schema_version is compatible. */
bool engine_artifact_exists(const char *repo_path);

/* Get the git commit hash from artifact metadata. Caller must free().
 * Returns NULL if artifact doesn't exist or has no commit field. */
char *engine_artifact_commit(const char *repo_path);

/* Whether repo_path is safe to interpolate into a double-quoted `git -C "…"` shell
 * command (as artifact.c does via engine_popen). Rejects quote / backslash / shell
 * substitution metacharacters (engine_validate_shell_arg); on Windows also rejects the
 * cmd.exe expansion metacharacters % ! ^. Spaces ARE allowed — double quotes handle
 * them on both POSIX sh and cmd.exe (single quotes, which cmd.exe does not honor,
 * were the pre-existing bug). Exposed so the shell-safety contract is unit-tested. */
bool engine_artifact_repo_path_is_shell_safe(const char *repo_path);

#endif /* ENGINE_ARTIFACT_H */
