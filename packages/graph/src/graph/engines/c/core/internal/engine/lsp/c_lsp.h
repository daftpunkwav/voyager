#ifndef ENGINE_LSP_C_LSP_H
#define ENGINE_LSP_C_LSP_H

#include "type_rep.h"
#include "scope.h"
#include "type_registry.h"
#include "../engine.h"
#include "go_lsp.h" // for EngineLSPDef, EngineResolvedCallArray

// CLSPContext holds state for C/C++ expression type evaluation within a file.
typedef struct {
    EngineArena *arena;
    const char *source;
    int source_len;
    const EngineTypeRegistry *registry;
    EngineScope *current_scope;

    // Include map: header_path -> namespace QN prefix
    const char **include_paths;
    const char **include_ns_qns;
    int include_count;

    // Namespace state
    const char *current_namespace; // current namespace QN (e.g., "proj.ns1.ns2")

    // Using namespace directives
    const char **using_namespaces;
    int using_ns_count;
    int using_ns_cap;

    // Using declarations: specific names imported into scope
    const char **using_decl_names;
    const char **using_decl_qns;
    int using_decl_count;
    int using_decl_cap;

    // Namespace aliases: short -> full QN
    const char **ns_alias_names;
    const char **ns_alias_qns;
    int ns_alias_count;
    int ns_alias_cap;

    // Current context
    const char *enclosing_func_qn;
    const char *enclosing_class_qn; // for implicit `this` resolution
    const char *module_qn;
    size_t module_qn_len; // cached strlen(module_qn); for stack-buffer QN building

    // Negative-lookup memo for c_lookup_member_depth (depth==0 misses only).
    // Open-addressing uint64 hash SET; 0 is the empty-slot sentinel. Populated
    // ONLY when the Tier-2 registry is shared+read-only (registry_shared), where
    // the module-prefix/base-class/short-name cascades are pure, stable functions
    // of (type_qn, registry) — so a recorded miss can never turn into a hit. Lets
    // the hot resolve path skip the sprintf("%s.%s") strlen storm + the O(type_count)
    // short-name scan on repeated misses of the same (type_qn, member). malloc-owned;
    // freed at end of c_lsp_process_file.
    uint64_t *neg_memo;
    int neg_memo_cap;   // power-of-two; 0 until first insert
    int neg_memo_count; // live entries (grow by rehash at 70% load)

    // Output
    EngineResolvedCallArray *resolved_calls;
    EngineSourceOrigin source_origin; // source buffer represented by emitted occurrence spans

    // Function pointer targets: lexical binding -> exact target function QN.
    // A NULL target is an explicitly unknown/ambiguous binding and must shadow
    // any outer exact target of the same name.
    const char **fp_var_names;
    const char **fp_target_qns;
    const EngineScope **fp_binding_scopes;
    int fp_count;
    int fp_cap;

    // Template parameter defaults for current template scope
    const char **template_param_names;       // e.g., ["T", "U"]
    const EngineType **template_param_defaults; // e.g., [int_type, NULL]
    int template_param_count;

    // Pending template calls: member calls on TYPE_PARAM inside template functions.
    // At call sites with known arg types, these are resolved retroactively.
    struct {
        const char *func_qn;     // enclosing template function
        const char *type_param;  // e.g., "T"
        const char *method_name; // e.g., "draw"
        int arg_count;
    } *pending_template_calls;
    int pending_tc_count;
    int pending_tc_cap;

    // Flags
    bool cpp_mode;        // C++ features enabled
    bool in_template;     // currently inside template declaration
    bool registry_shared; // ctx->registry is the Tier-2 cross registry, shared
                          // READ-ONLY across resolve workers — never mutate it
                          // (and never store per-worker arena pointers into it)
    bool debug;
    int eval_depth; // recursion depth for c_eval_expr_type (crash guard)
    int eval_steps; // total expression eval calls for current file (hang guard)
    int walk_depth; // c_resolve_calls_in_node self-recursion (AST nesting)
    int control_flow_depth; // if/loop/switch/catch nesting; assignments merge fail-closed
} CLSPContext;

// --- API ---

void c_lsp_init(CLSPContext *ctx, EngineArena *arena, const char *source, int source_len,
                const EngineTypeRegistry *registry, const char *module_qn, bool cpp_mode,
                EngineResolvedCallArray *out);

void c_lsp_add_include(CLSPContext *ctx, const char *header_path, const char *ns_qn);

void c_lsp_process_file(CLSPContext *ctx, TSNode root);

const EngineType *c_eval_expr_type(CLSPContext *ctx, TSNode node);
const EngineType *c_parse_type_node(CLSPContext *ctx, TSNode node);
void c_process_statement(CLSPContext *ctx, TSNode node);

// Look up a member (method/field) on a type, traversing base classes.
const EngineRegisteredFunc *c_lookup_member(CLSPContext *ctx, const char *type_qn,
                                         const char *member_name);

// Type simplification: unwrap refs, aliases, pointers (like clangd simplifyType).
const EngineType *c_simplify_type(CLSPContext *ctx, const EngineType *t, bool unwrap_pointer);

// --- Entry points ---

// Single-file LSP: build registry from file defs + stdlib, run resolution.
void engine_run_c_lsp(EngineArena *arena, EngineFileResult *result, const char *source, int source_len,
                   TSNode root, bool cpp_mode, EngineSourceOrigin source_origin);

// Cross-file LSP: build registry from defs + stdlib, re-parse and resolve.
void engine_run_c_lsp_cross(EngineArena *arena, const char *source, int source_len, const char *module_qn,
                         bool cpp_mode, EngineLSPDef *defs, int def_count, const char **include_paths,
                         const char **include_ns_qns, int include_count,
                         TSTree *cached_tree, // NULL = parse internally
                         EngineResolvedCallArray *out);

// Tier 2: build a project-wide C/C++/CUDA registry ONCE from all defs
// (filters by lang). Shared READ-ONLY across resolve workers. Def-driven
// (no AST field collection) → identical entries to the per-file build.
EngineTypeRegistry *engine_c_build_cross_registry(EngineArena *arena, EngineLSPDef *defs, int def_count);

// Cross-file LSP using a pre-built shared registry (Tier 2). Skips the
// per-file registry build; just parse + resolve.
void engine_run_c_lsp_cross_with_registry(EngineArena *arena, const char *source, int source_len,
                                       const char *module_qn, bool cpp_mode,
                                       EngineTypeRegistry *reg, // pre-built, finalized, READ-ONLY
                                       const char **include_paths, const char **include_ns_qns,
                                       int include_count,
                                       TSTree *cached_tree, // NULL = parse internally
                                       EngineResolvedCallArray *out);

// Register C stdlib types and functions into a registry.
void engine_c_stdlib_register(EngineTypeRegistry *reg, EngineArena *arena);

// Register C++ stdlib types and functions into a registry.
void engine_cpp_stdlib_register(EngineTypeRegistry *reg, EngineArena *arena);

// --- Batch cross-file LSP ---

// Per-file input for batch C/C++ LSP processing.
typedef struct {
    const char *source;
    int source_len;
    const char *module_qn;
    bool cpp_mode;
    TSTree *cached_tree; // from TSTree caching (NULL = parse internally)
    EngineLSPDef *defs;     // combined file-local + cross-file defs
    int def_count;
    const char **include_paths; // parallel arrays, include_count long
    const char **include_ns_qns;
    int include_count;
} EngineBatchCLSPFile;

// Process multiple C/C++ files' cross-file LSP in one CGo call.
// out must point to file_count pre-zeroed EngineResolvedCallArray structs.
void engine_batch_c_lsp_cross(EngineArena *arena, EngineBatchCLSPFile *files, int file_count,
                           EngineResolvedCallArray *out);

#endif // ENGINE_LSP_C_LSP_H
