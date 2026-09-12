/*
 * discover.h — File discovery, language detection, and gitignore matching.
 *
 * Provides:
 *   - Language detection from filename/extension (EngineLanguage registry)
 *   - .m file disambiguation (Objective-C vs MATLAB)
 *   - Gitignore-style pattern parsing and matching
 *   - Recursive directory walk with hardcoded + gitignore filtering
 *
 * Depends on: foundation (platform.h for file ops), engine.h (EngineLanguage enum)
 */
#ifndef ENGINE_DISCOVER_H
#define ENGINE_DISCOVER_H

#include <stdbool.h>
#include <stdint.h>

/* Use the existing EngineLanguage enum from extraction layer */
#include "engine.h"

/* ── Language detection ──────────────────────────────────────────── */

/* Detect language from a filename (basename only, not full path).
 * Checks special filenames first (Makefile, CMakeLists.txt, etc.),
 * then falls back to extension-based lookup.
 * Returns ENGINE_LANG_COUNT if unknown. */
EngineLanguage engine_language_for_filename(const char *filename);

/* Detect language from a file extension (including the dot, e.g. ".go").
 * Returns ENGINE_LANG_COUNT if unknown. */
EngineLanguage engine_language_for_extension(const char *ext);

/* Get the human-readable name for a language enum value.
 * Returns "Unknown" for ENGINE_LANG_COUNT or out-of-range values. */
const char *engine_language_name(EngineLanguage lang);

/* Disambiguate .m files by reading first 4KB of content.
 * Returns ENGINE_LANG_OBJC or ENGINE_LANG_MATLAB.
 * On read failure, defaults to ENGINE_LANG_MATLAB. */
EngineLanguage engine_disambiguate_m(const char *path);

EngineLanguage engine_disambiguate_cls(const char *path);

/* Disambiguate .inc files: returns ENGINE_LANG_C. */
EngineLanguage engine_disambiguate_inc(const char *path);

/* ── Gitignore pattern matching ──────────────────────────────────── */

typedef struct engine_gitignore engine_gitignore_t;

/* Parse gitignore patterns from a file. Returns NULL on error (file not found, etc.).
 * Caller must call engine_gitignore_free(). */
engine_gitignore_t *engine_gitignore_load(const char *path);

/* Parse gitignore patterns from a string (for testing).
 * Caller must call engine_gitignore_free(). */
engine_gitignore_t *engine_gitignore_parse(const char *content);

/* Check if a relative path matches any gitignore pattern.
 * rel_path should use '/' separators. is_dir indicates if path is a directory. */
bool engine_gitignore_matches(const engine_gitignore_t *gi, const char *rel_path, bool is_dir);

/* Free a gitignore matcher. NULL-safe. */
void engine_gitignore_free(engine_gitignore_t *gi);

/* Append all patterns from src into dst. dst takes ownership of deep copies
 * of each src pattern; src is unchanged and must still be freed by the caller.
 * NULL-safe on either argument.
 * Returns true on success (or when there is nothing to merge). Returns false on
 * allocation failure, in which case dst is left exactly as it was (atomic) — no
 * partial merge — so a failed merge degrades to "as if src was absent". */
bool engine_gitignore_merge(engine_gitignore_t *dst, const engine_gitignore_t *src);

/* ── Directory skip / suffix filters ─────────────────────────────── */

/* Index mode controls filtering aggressiveness.
 * IMPORTANT: these values MUST match pipeline.h exactly.  A previous
 * mismatch (this header had FAST=1, pipeline.h has FAST=2) caused
 * fast-mode filtering to silently no-op depending on include order —
 * the pipeline passed value 2, discover.c compared against 1, and no
 * files got filtered. */
#ifndef ENGINE_INDEX_MODE_T_DEFINED
#define ENGINE_INDEX_MODE_T_DEFINED
typedef enum {
    ENGINE_MODE_FULL = 0,     /* parse everything supported */
    ENGINE_MODE_MODERATE = 1, /* aggressive filtering + similarity/semantic edges */
    ENGINE_MODE_FAST = 2,     /* aggressive filtering + no similarity/semantic edges */
} engine_index_mode_t;
#endif

/* Check if a directory name should always be skipped (e.g. .git, node_modules).
 * Only checks the basename, not the full path. */
bool engine_should_skip_dir(const char *dirname, engine_index_mode_t mode);

/* Check if a file has a suffix that should be skipped (e.g. .pyc, .png). */
bool engine_has_ignored_suffix(const char *filename, engine_index_mode_t mode);

/* Check if a specific filename should be skipped in fast mode (e.g. LICENSE, go.sum). */
bool engine_should_skip_filename(const char *filename, engine_index_mode_t mode);

/* Check if a path matches fast-mode substring patterns (e.g. .d.ts, .pb.go). */
bool engine_matches_fast_pattern(const char *filename, engine_index_mode_t mode);

/* ── File discovery ──────────────────────────────────────────────── */

typedef struct {
    char *path;           /* absolute path (heap-allocated) */
    char *rel_path;       /* relative to repo root (heap-allocated) */
    EngineLanguage language; /* detected language */
    int64_t size;         /* file size in bytes */
} engine_file_info_t;

typedef struct {
    engine_index_mode_t mode;   /* ENGINE_MODE_FULL or ENGINE_MODE_FAST */
    const char *ignore_file; /* path to .engineignore file, or NULL */
    int64_t max_file_size;   /* 0 = no limit */
} engine_discover_opts_t;

typedef enum {
    ENGINE_DISCOVER_ERROR = -1,
    ENGINE_DISCOVER_OK = 0,
    ENGINE_DISCOVER_LIMIT_EXCEEDED = 1,
} engine_discover_status_t;

/* Walk a repository directory tree and discover all source files.
 * Applies hardcoded filters, gitignore patterns, and language detection.
 * Returns 0 on success, -1 on error.
 * Caller must call engine_discover_free() on the results. */
int engine_discover(const char *repo_path, const engine_discover_opts_t *opts, engine_file_info_t **out,
                 int *count);

/* Apply the exact same full discovery/filter policy without retaining a file
 * array. Stops before counting more than max_files and performs no per-file
 * allocation. deadline_ms is an absolute engine_now_ms() deadline; zero disables
 * it. Returns LIMIT_EXCEEDED when at least max_files + 1 indexable files exist,
 * ERROR on traversal/deadline/allocation failure, or OK with the exact count. */
engine_discover_status_t engine_discover_count_bounded(const char *repo_path,
                                                 const engine_discover_opts_t *opts, int max_files,
                                                 uint64_t deadline_ms, int *count_out);

/* Like engine_discover(), but also reports the directory subtrees that were
 * skipped during the walk (hardcoded ALWAYS_SKIP/FAST_SKIP dirs + gitignore
 * matches), so callers can surface which subtrees were dropped (#411).
 * On success, *excluded_out receives a heap-allocated array of strdup'd
 * relative directory paths and *excluded_count_out its length; the caller
 * owns it and must free via engine_discover_free_excluded(). Pass NULL for
 * excluded_out (and/or excluded_count_out) to discard the list — the internal
 * accumulator is freed in that case (no leak).
 * Returns 0 on success, -1 on error. */
int engine_discover_ex(const char *repo_path, const engine_discover_opts_t *opts, engine_file_info_t **out,
                    int *count, char ***excluded_out, int *excluded_count_out);

/* One deliberately-not-indexed file (#963): an individual file dropped by an
 * ignore mechanism during the walk (its parent directory was NOT excluded —
 * whole subtrees are reported separately as excluded dirs). BY DESIGN, not a
 * failure. */
typedef struct {
    char *rel_path; /* heap-allocated, relative to repo root */
    char *reason;   /* heap-allocated: "gitignore" | "engineignore" |
                     * "skip-list" | "ignored-suffix" | "fast-pattern" |
                     * "size-cap" */
} engine_ignored_file_t;

/* Stored per-file ignore entries are capped (the walk still counts ALL of
 * them in *ignored_total_out, so truncation is always explicit, never
 * silent). Whole excluded subtrees stay exhaustive via excluded_out. */
enum { ENGINE_DISCOVER_IGNORED_CAP = 2000 };

/* Like engine_discover_ex(), but additionally reports the individual files that
 * ignore rules dropped (#963 "purposely not indexed"). *ignored_out receives
 * a heap array (caller frees via engine_discover_free_ignored),
 * *ignored_count_out its stored length (<= ENGINE_DISCOVER_IGNORED_CAP), and
 * *ignored_total_out the TOTAL number of ignored files seen. Pass NULL to
 * skip the collection entirely. */
int engine_discover_ex2(const char *repo_path, const engine_discover_opts_t *opts, engine_file_info_t **out,
                     int *count, char ***excluded_out, int *excluded_count_out,
                     engine_ignored_file_t **ignored_out, int *ignored_count_out,
                     int *ignored_total_out);

/* Free an array of file info results. NULL-safe. */
void engine_discover_free(engine_file_info_t *files, int count);

/* Free the excluded-directory list returned by engine_discover_ex(). NULL-safe. */
void engine_discover_free_excluded(char **excluded, int count);

/* Free the ignored-file list returned by engine_discover_ex2(). NULL-safe. */
void engine_discover_free_ignored(engine_ignored_file_t *ignored, int count);

#endif /* ENGINE_DISCOVER_H */
