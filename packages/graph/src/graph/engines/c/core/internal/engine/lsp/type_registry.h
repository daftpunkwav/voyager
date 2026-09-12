#ifndef ENGINE_LSP_TYPE_REGISTRY_H
#define ENGINE_LSP_TYPE_REGISTRY_H

#include "type_rep.h"
#include "../arena.h"
#include <stdbool.h>

// Language-specific function metadata. Added at struct tail so existing
// callers that memset to zero before populating other fields keep working.
typedef enum {
    ENGINE_FUNC_FLAG_NONE = 0,
    ENGINE_FUNC_FLAG_PROPERTY = 1 << 0,        // @property -> obj.attr returns getter return
    ENGINE_FUNC_FLAG_CLASSMETHOD = 1 << 1,     // @classmethod -> first arg is cls (the class)
    ENGINE_FUNC_FLAG_STATICMETHOD = 1 << 2,    // @staticmethod -> no implicit self/cls
    ENGINE_FUNC_FLAG_ABSTRACTMETHOD = 1 << 3,  // @abstractmethod -> still callable for resolution
    ENGINE_FUNC_FLAG_OVERLOAD = 1 << 4,        // @overload entry — non-implementation stub
    ENGINE_FUNC_FLAG_ASYNC = 1 << 5,           // async def — return is Coroutine[..., T]
    ENGINE_FUNC_FLAG_GENERATOR = 1 << 6,       // contains yield — return is Generator[T, ...]
    ENGINE_FUNC_FLAG_FINAL = 1 << 7,           // @final — overrides not allowed
    ENGINE_FUNC_FLAG_RUST_TRAIT_IMPL = 1 << 8, // exact method from impl Trait for Type
    ENGINE_FUNC_FLAG_RUST_ABSTRACT = 1 << 9,   // required trait method without a default body
    /* Python only: more than one registered definition has this exact QN.
     * Ordinary call resolution keeps its historical language-specific choice,
     * but a function value cannot name one materialized definition exactly. */
    ENGINE_FUNC_FLAG_AMBIGUOUS_BINDING = 1 << 10,
} EngineFuncFlags;

// Registered function/method with full type signature.
typedef struct {
    const char *qualified_name;    // e.g., "proj.pkg.TypeName.MethodName"
    const char *receiver_type;     // e.g., "proj.pkg.TypeName" (NULL for functions)
    const char *short_name;        // e.g., "MethodName"
    const EngineType *signature;      // FUNC type with param/return types
    const char **type_param_names; // NULL-terminated, e.g., ["T", "R", NULL] for generics
    int min_params;                // Minimum required params (excluding defaulted). -1 = unknown.
    int flags;                     // ENGINE_FUNC_FLAG_* bitfield
    const char **decorator_qns;    // NULL-terminated decorator QNs (Python only); used for
                                   // user-decorator return-type substitution.
    /* Rust only: canonical trait QN for a concrete trait-impl method. It may
     * remain NULL when raw cross-file provenance is ambiguous; the Rust trait
     * flag still prevents that method from being mistaken for inherent. */
    const char *impl_trait_qn;
} EngineRegisteredFunc;

// Registered type with fields and method names.
typedef struct {
    const char *qualified_name;    // e.g., "proj.pkg.TypeName"
    const char *short_name;        // e.g., "TypeName"
    const char **field_names;      // NULL-terminated
    const EngineType **field_types;   // NULL-terminated (parallel to field_names)
    const char **method_names;     // NULL-terminated (short names)
    const char **method_qns;       // NULL-terminated (qualified names, parallel)
    const char **embedded_types;   // NULL-terminated (embedded/anonymous field type QNs)
    const char *alias_of;          // QN of aliased type (type Foo = Bar), NULL if not alias
    const char **type_param_names; // NULL-terminated, e.g., ["T", "K", NULL] for template classes
    bool is_interface;
    bool is_object; // Kotlin `object`/`companion object` singleton (member calls are static)

    // --- TS-specific fields (NULL/empty for non-TS types — backward compatible) ---
    // TS interfaces / object types may be callable: `interface F { (x:number): string }`.
    const EngineType *call_signature; // FUNC type or NULL
    // TS objects can have an index signature: `{ [key:string]: V }` or `{ [i:number]: V }`.
    const EngineType *index_key_type;   // BUILTIN("string"|"number") or NULL
    const EngineType *index_value_type; // V or NULL
    // Generic constraints, parallel to type_param_names. NULL or shorter array means "any".
    const EngineType **type_param_constraints; // NULL-terminated, parallel to type_param_names
} EngineRegisteredType;

// Hash-table bucket entry. Chains collisions via next-index list for overload sets.
typedef struct {
    uint64_t hash;     // FNV-1a of key
    int payload_index; // index into reg->funcs[] or reg->types[]
    int next_index;    // -1 = end of chain; else index of next bucket entry in same chain
    int slot;          // bucket slot this entry sits in (for resize)
} EngineRegistryHashEntry;

// Cross-file type/function registry.
typedef struct EngineTypeRegistry {
    EngineRegisteredFunc *funcs;
    int func_count;
    int func_cap;

    EngineRegisteredType *types;
    int type_count;
    int type_cap;

    EngineArena *arena; // owns all string data

    /* Optional fallback registry (Tier 2 two-level lookup). When a
     * lookup misses in this registry, it chains to `fallback`. Used by
     * TS/PHP cross-LSP: a small per-file registry (the file's own
     * AST-refined types) chains to a shared, immutable base registry
     * (stdlib + all project defs) built once. NULL = no chaining. */
    const struct EngineTypeRegistry *fallback;

    // Hash indexes (built lazily by engine_registry_finalize, NULL until then).
    // Lookups fall back to linear scan when these are NULL.
    int *func_qn_buckets; // bucket → first entry index in func_qn_entries; -1 = empty
    EngineRegistryHashEntry *func_qn_entries; // entries indexed by linear order
    int func_qn_bucket_count;
    int func_qn_entry_count;

    int *type_qn_buckets;
    EngineRegistryHashEntry *type_qn_entries;
    int type_qn_bucket_count;
    int type_qn_entry_count;

    // Methods indexed by (receiver_type, short_name) — chain holds overloads.
    int *method_buckets;
    EngineRegistryHashEntry *method_entries;
    int method_bucket_count;
    int method_entry_count;

    // Auxiliary short-name / embedded-type indexes (built by finalize alongside the
    // QN buckets). Turn the Rust trait- and free-function fallback scans from
    // O(type_count)/O(func_count) into O(chain). Read-only after finalize.
    // Embedded-type index: fnv1a(bare last-'.'-segment of each embedded_type) -> chain
    // of TYPE indices declaring it. payload_index = type index (a type may appear once
    // per embedded entry; consumers dedup adjacent same-type via the iterator).
    int *type_embed_buckets;
    EngineRegistryHashEntry *type_embed_entries;
    int type_embed_bucket_count;
    int type_embed_entry_count;
    // Free-function short-name index: fnv1a(short_name) -> chain of FREE-function
    // (receiver_type==NULL) indices. payload_index = func index.
    int *ffunc_short_buckets;
    EngineRegistryHashEntry *ffunc_short_entries;
    int ffunc_short_bucket_count;
    int ffunc_short_entry_count;

    /* Sealed / read-only. Set true by the engine_X_build_cross_registry builders
     * (c/cpp, python, c#, ts, go) right after finalize: a Tier-2 cross-registry
     * is built ONCE and shared READ-ONLY across the parallel resolve workers.
     * engine_registry_add_func/_type no-op on a sealed registry, so a per-file
     * resolver can never mutate the shared, finalized registry. Without this,
     * post-finalize adds accumulate in a tail the hash index does not cover ->
     * every lookup linear-scans it -> O(files*defs) (the Linux-kernel full-index
     * hang) plus a heap data race across workers. */
    bool read_only;
} EngineTypeRegistry;

// Initialize a registry.
void engine_registry_init(EngineTypeRegistry *reg, EngineArena *arena);

// Build the hash indexes after all funcs/types have been added. Subsequent lookups
// use O(1) hashed dispatch instead of linear scans. Calling this is OPTIONAL — the
// linear-scan path remains correct. Single-file resolvers (small registries) skip
// finalize and stay linear; project-wide registries (many thousands of entries) call
// it once after pass-1.5 def-collection.
void engine_registry_finalize(EngineTypeRegistry *reg);

// Like engine_registry_finalize, but the hash-index allocations (buckets/entries)
// come from idx_arena instead of reg->arena. Per-file cross resolvers MUST use
// this with a scratch arena destroyed after the walk: their reg->arena is the
// pipeline-lifetime result arena, and per-file index allocations accumulated
// there add GBs across a large repo (FastAPI incremental test: +1.1 GB RSS).
void engine_registry_finalize_into(EngineTypeRegistry *reg, EngineArena *idx_arena);

// Register a function/method.
void engine_registry_add_func(EngineTypeRegistry *reg, EngineRegisteredFunc func);

// Register a type.
void engine_registry_add_type(EngineTypeRegistry *reg, EngineRegisteredType type);

// Look up a method by receiver type QN + method name.
const EngineRegisteredFunc *engine_registry_lookup_method(const EngineTypeRegistry *reg,
                                                    const char *receiver_qn,
                                                    const char *method_name);

// Look up a type by qualified name.
const EngineRegisteredType *engine_registry_lookup_type(const EngineTypeRegistry *reg,
                                                  const char *qualified_name);

// Look up a function by qualified name.
const EngineRegisteredFunc *engine_registry_lookup_func(const EngineTypeRegistry *reg,
                                                  const char *qualified_name);

// Look up a symbol (type or function) in a package by short name.
// package_qn is the package prefix (e.g., "proj.pkg").
const EngineRegisteredFunc *engine_registry_lookup_symbol(const EngineTypeRegistry *reg,
                                                    const char *package_qn, const char *name);

// Resolve type alias chain: follow alias_of until concrete type found (max 16 levels).
const EngineRegisteredType *engine_registry_resolve_alias(const EngineTypeRegistry *reg,
                                                    const char *type_qn);

// Look up a method by receiver type QN + method name, following alias chains.
const EngineRegisteredFunc *engine_registry_lookup_method_aliased(const EngineTypeRegistry *reg,
                                                            const char *receiver_qn,
                                                            const char *method_name);

// Look up a method by receiver type + name, preferring the overload with matching arg count.
// Falls back to any match if no exact arg count match found.
const EngineRegisteredFunc *engine_registry_lookup_method_by_args(const EngineTypeRegistry *reg,
                                                            const char *receiver_qn,
                                                            const char *method_name, int arg_count);

// Look up a free function by package + name, preferring matching arg count.
const EngineRegisteredFunc *engine_registry_lookup_symbol_by_args(const EngineTypeRegistry *reg,
                                                            const char *package_qn,
                                                            const char *name, int arg_count);

// Look up a method by receiver type + name, scoring overloads by parameter type match.
// arg_types may contain NULL entries for unknown types. Falls back to arg-count matching.
const EngineRegisteredFunc *engine_registry_lookup_method_by_types(const EngineTypeRegistry *reg,
                                                             const char *receiver_qn,
                                                             const char *method_name,
                                                             const EngineType **arg_types,
                                                             int arg_count);

// Look up a free function by package + name, scoring overloads by parameter type match.
const EngineRegisteredFunc *engine_registry_lookup_symbol_by_types(const EngineTypeRegistry *reg,
                                                             const char *package_qn,
                                                             const char *name,
                                                             const EngineType **arg_types,
                                                             int arg_count);

// --- Auxiliary index iterators (Rust trait / free-function fallback fast paths) ---
//
// Iterate registry TYPE indices whose embedded_types contain an entry whose BARE
// name (last '.'-segment) equals `bare`. On a finalized registry this walks the
// embedded-type index plus any post-finalize tail; on an unfinalized registry it
// degrades to a full linear scan over all types (identical candidate set). Each
// matching type index is yielded at most once, in ascending registry order. The
// index is a bare-name PREFILTER — the caller MUST still apply its own exact
// predicate on each yielded type. Read-only, allocation-free. Usage:
//   EngineTypeEmbedIter it; engine_registry_types_by_embedded_bare(reg, bare, &it);
//   int ti; while ((ti = engine_type_embed_iter_next(&it)) >= 0) { ... reg->types[ti] ... }
typedef struct {
    const EngineTypeRegistry *reg;
    uint64_t hash;
    int chain_idx; // next entry in the embed chain, or -1
    int tail_i;    // next tail/linear type index
    int tail_end;  // reg->type_count snapshot
    int prev_type; // last yielded type index (adjacent-dedup); -1 = none
} EngineTypeEmbedIter;
void engine_registry_types_by_embedded_bare(const EngineTypeRegistry *reg, const char *bare,
                                         EngineTypeEmbedIter *out);
int engine_type_embed_iter_next(EngineTypeEmbedIter *it);

// Iterate FREE-function (receiver_type==NULL) indices whose short_name equals
// `short_name`. Same finalized/unfinalized behavior as above; caller re-checks its
// own predicate. Read-only, allocation-free.
typedef struct {
    const EngineTypeRegistry *reg;
    uint64_t hash;
    int chain_idx;
    int tail_i;
    int tail_end;
} EngineFreeFuncIter;
void engine_registry_free_funcs_by_short_name(const EngineTypeRegistry *reg, const char *short_name,
                                           EngineFreeFuncIter *out);
int engine_free_func_iter_next(EngineFreeFuncIter *it);

// Iterate function indices for one exact (receiver QN, method name) key.  This
// exposes the existing finalized method bucket without making Rust scan the
// project-wide func array merely to distinguish inherent and trait-impl
// entries that intentionally share the same source-level QN.  The caller may
// filter on language-specific flags. Read-only and allocation-free.
typedef struct {
    const EngineTypeRegistry *reg;
    const char *receiver_qn;
    const char *method_name;
    uint64_t hash;
    int chain_idx;
    int tail_i;
    int tail_end;
} EngineMethodIter;
void engine_registry_methods(const EngineTypeRegistry *reg, const char *receiver_qn,
                          const char *method_name, EngineMethodIter *out);
int engine_method_iter_next(EngineMethodIter *it);

// --- TS-specific helpers (return NULL for types without these signatures) ---

// If the type has a call signature (e.g., `interface F { (x:number): string }`), return
// a synthesised EngineRegisteredFunc whose qualified_name is "<type_qn>.__call" and
// short_name is "__call". Returns NULL if no call signature is present, the type is
// missing, or the receiver type was not registered. Caller must NOT free.
const EngineRegisteredFunc *engine_registry_lookup_callable(const EngineTypeRegistry *reg, EngineArena *arena,
                                                      const char *type_qn);

// If the type has an index signature, return the value type produced by indexing with
// the given key type (string vs number). Returns NULL if no matching index signature.
const EngineType *engine_registry_lookup_index_signature(const EngineTypeRegistry *reg, const char *type_qn,
                                                   const EngineType *key_type);

#endif // ENGINE_LSP_TYPE_REGISTRY_H
