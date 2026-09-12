#ifndef ENGINE_LSP_SCOPE_H
#define ENGINE_LSP_SCOPE_H

#include "type_rep.h"
#include "../arena.h"
#include <stdatomic.h> /* relaxed cache for engine_lsp_max_walk_depth */
#include <stdlib.h>     /* getenv, atoi (engine_lsp_max_walk_depth) */

typedef struct {
    const char* name;
    const EngineType* type;
    /* Exact callable value carried by this lexical binding, or NULL when the
     * binding is not proven to denote one callable.  This is deliberately
     * identity metadata rather than another EngineType kind: aliases need both
     * their ordinary type and the graph QN of the value they reference. */
    const char *callable_qn;
} EngineVarBinding;

#define ENGINE_SCOPE_CHUNK_BINDINGS 16

typedef struct EngineScopeChunk {
    EngineVarBinding bindings[ENGINE_SCOPE_CHUNK_BINDINGS];
    int used;
    struct EngineScopeChunk* next;
} EngineScopeChunk;

typedef struct EngineScope {
    struct EngineScope* parent;
    EngineScopeChunk* chunks;
    EngineArena* arena;        // owning arena, propagated to children at push time
} EngineScope;

// Bail-to-UNKNOWN depth for type-lookup chains: alias resolution, MRO walks,
// embedded-field/struct-traversal. Exceeding this collapses to engine_type_unknown
// rather than recursing — guards against pathological hierarchies.
#define ENGINE_LSP_MAX_LOOKUP_DEPTH 16

// Recursion cap for the per-language "resolve calls in AST node" walkers. These
// recurse once per AST nesting level; a deeply-nested or cyclic file can drive
// them into a native stack overflow (SIGSEGV) that takes down the whole index.
// Past this cap the wrapper skips the subtree — those calls stay unresolved,
// which is graceful degradation, not a crash. 512 is far deeper than any
// hand-written source nests; override for pathological/generated repos via the
// ENGINE_LSP_MAX_WALK_DEPTH env var (positive integer).
#define ENGINE_LSP_MAX_WALK_DEPTH 512

// Resolved walk-depth cap: env override (ENGINE_LSP_MAX_WALK_DEPTH, if a positive
// integer) else ENGINE_LSP_MAX_WALK_DEPTH. Read once and cached — the walkers call
// this per node, so it must not hit getenv on the hot path. The cache is
// idempotent under multi-threaded indexing (every worker computes the same
// value), but a plain data race is undefined behavior even when the values
// agree, so the slot is a relaxed atomic: on the hot path this is a plain load
// with no fence, and a first-touch double-compute simply stores the same
// value. This keeps the parallel extractor TSan-clean.
static inline int engine_lsp_max_walk_depth(void) {
    static _Atomic int cached = -1;
    int value = atomic_load_explicit(&cached, memory_order_relaxed);
    if (value < 0) {
        const char* e = getenv("ENGINE_LSP_MAX_WALK_DEPTH");
        int v = (e && *e) ? atoi(e) : 0;
        value = (v > 0) ? v : ENGINE_LSP_MAX_WALK_DEPTH;
        atomic_store_explicit(&cached, value, memory_order_relaxed);
    }
    return value;
}

EngineScope* engine_scope_push(EngineArena* a, EngineScope* current);
EngineScope* engine_scope_pop(EngineScope* scope);
void engine_scope_bind(EngineScope* scope, const char* name, const EngineType* type);
/* Checked forms: false when the binding could not be recorded in THIS frame
 * (arena exhaustion). The void forms above discard that and return silently,
 * which lets a caller that then does a scope-CHAIN lookup see a PARENT binding
 * of the same name and believe the child was bound -- fabricating callable
 * proof from a shadow that never took effect. Use these, and read the local
 * result, wherever a failed bind must not be mistaken for success. */
bool engine_scope_bind_checked(EngineScope *scope, const char *name, const EngineType *type);
bool engine_scope_bind_callable_checked(EngineScope *scope, const char *name, const EngineType *type,
                                     const char *callable_qn);
/* Bind a value whose identity is one exact callable.  A later ordinary
 * engine_scope_bind of the same name clears this identity, so reassignment fails
 * closed instead of leaking a stale alias target. */
void engine_scope_bind_callable(EngineScope *scope, const char *name, const EngineType *type,
                             const char *callable_qn);
const EngineType* engine_scope_lookup(const EngineScope* scope, const char* name);
/* True when any lexical frame contains name, even when its type is UNKNOWN. */
bool engine_scope_contains(const EngineScope *scope, const char *name);
/* Return the exact callable QN from the nearest binding.  A nearer ordinary
 * binding shadows a parent's callable and therefore returns NULL. */
const char *engine_scope_lookup_callable(const EngineScope *scope, const char *name);
/* Replace (or clear with NULL) callable identity on the nearest existing
 * lexical binding. Returns false when name is unbound. This is for assignment;
 * declarations should continue to use engine_scope_bind[_callable]. */
bool engine_scope_update_callable(EngineScope *scope, const char *name, const char *callable_qn);

#endif // ENGINE_LSP_SCOPE_H
