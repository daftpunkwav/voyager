/*
 * lsp_surface.h — per-file LSP-surface codec (closure-repair incremental).
 *
 * A file's SURFACE is everything another file's resolution can consume from
 * it: the EngineLSPDefs pass_lsp_cross registers into the cross registries,
 * plus the registry-only symbols (labels the name registry serves that
 * pxc_map_label drops — Field, today). Serialized to canonical JSON, hashed,
 * and persisted per file (store: lsp_surface rows) at publication, so an
 * incremental run can (a) detect that an edit left a file's surface
 * unchanged — a body edit — and skip recomputing its dependents, and
 * (b) rehydrate the cross registries for files it does not re-parse.
 *
 * The JSON is a versioned object {"v":1,"lsp":[...],"reg":[...]}. Field
 * order and array order are fixed by the writer, so byte equality of the
 * serialization is surface equality; the sha256 of these bytes is the
 * stored surface_sha. Rows written by a different codec version fail the
 * "v" check on load and route the run to a full rebuild.
 */
#ifndef ENGINE_PIPELINE_LSP_SURFACE_H
#define ENGINE_PIPELINE_LSP_SURFACE_H

#include "pipeline/pass_lsp_cross.h"
#include "store/store.h"
#include "foundation/arena.h"

/* Build one store row per file that produced surface content. `def_starts`
 * is the (file_count + 1)-entry prefix array from engine_pxc_collect_all_defs:
 * all_defs[def_starts[i] .. def_starts[i+1]) are file i's defs. Rows carry
 * heap strings; release with engine_store_free_lsp_surfaces. Files with an
 * empty surface still get a row (empty arrays hash too — "no defs" must be
 * distinguishable from "no data"). Returns 0, or -1 on allocation failure. */
int engine_lsp_surface_build_rows(const char *project, EngineFileResult **cache,
                               const engine_file_info_t *files, int file_count,
                               const EngineLSPDef *all_defs, const int *def_starts,
                               engine_lsp_surface_row_t **out_rows, int *out_count);

/* Decode one row's defs_json back into the EngineLSPDef array pass_lsp_cross
 * registration consumes. Strings are arena-allocated. Returns the def count,
 * 0 for an empty surface, or -1 when the JSON is missing, malformed, or a
 * different codec version — callers route that to a full rebuild. */
int engine_lsp_surface_defs_from_json(EngineArena *arena, const char *defs_json, EngineLSPDef **out_defs);

#endif /* ENGINE_PIPELINE_LSP_SURFACE_H */
