/* compact_out.h — TOON (Token-Oriented Object Notation) emission helpers.
 *
 * Tool responses are consumed by LLM agents, where every byte is context
 * tokens. TOON encodes the same data as JSON but declares tabular fields
 * once in a header and streams rows line by line, cutting 40-60% of tokens
 * on homogeneous result sets at equal-or-better retrieval accuracy
 * (toonformat.dev/guide/benchmarks). Emitters here cover the subset we
 * emit: scalar key-value lines and flat tables with explicit [N] lengths.
 *
 * Quoting: a cell/scalar is double-quoted iff it is empty, has leading or
 * trailing whitespace, contains a comma, quote, newline, or CR, or would
 * read as a non-string literal (true/false/null/number). Quotes and
 * backslashes are escaped JSON-style; newlines become \n.
 */
#ifndef ENGINE_MCP_COMPACT_OUT_H
#define ENGINE_MCP_COMPACT_OUT_H

#include <stdbool.h>
#include <stddef.h>

/* Minimal growing string buffer (OOM-safe: sticky flag, finish returns NULL). */
typedef struct {
    char *buf;
    size_t len;
    size_t cap;
    bool oom;
} engine_sb_t;

void engine_sb_init(engine_sb_t *sb);
void engine_sb_append_n(engine_sb_t *sb, const char *s, size_t n);
void engine_sb_append(engine_sb_t *sb, const char *s);
/* Returns the heap buffer (caller frees) and resets sb. NULL on OOM. */
char *engine_sb_finish(engine_sb_t *sb);
void engine_sb_free(engine_sb_t *sb);

/* `key: value` scalar lines (top-level, no indent). */
void engine_tree_scalar_str(engine_sb_t *sb, const char *key, const char *val);
void engine_tree_scalar_int(engine_sb_t *sb, const char *key, long long v);
void engine_tree_scalar_bool(engine_sb_t *sb, const char *key, bool v);

/* `key[n]{col1,col2,...}:` table header; rows follow at 2-space indent. */
void engine_tree_table_header(engine_sb_t *sb, const char *key, int n, const char *const *cols,
                           int ncols);

/* Row cells: call row_begin, then cell_* per column (first=true for the
 * first cell), then row_end. Empty/NULL strings emit as empty cells. */
void engine_tree_row_begin(engine_sb_t *sb);
void engine_tree_cell_str(engine_sb_t *sb, const char *val, bool first);
void engine_tree_cell_int(engine_sb_t *sb, long long v, bool first);
void engine_tree_cell_real(engine_sb_t *sb, double v, bool first);
void engine_tree_cell_bool(engine_sb_t *sb, bool v, bool first);
void engine_tree_row_end(engine_sb_t *sb);

#endif /* ENGINE_MCP_COMPACT_OUT_H */
