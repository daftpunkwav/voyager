#ifndef ENGINE_H
#define ENGINE_H

#include <stdint.h>
#include <stdbool.h>
#include "arena.h"
#include "tree_sitter/api.h"

// Language enum mirrors lang.Language in Go.
// Order must match lang_specs.c tables.
typedef enum {
    ENGINE_LANG_GO = 0,
    ENGINE_LANG_PYTHON,
    ENGINE_LANG_JAVASCRIPT,
    ENGINE_LANG_TYPESCRIPT,
    ENGINE_LANG_TSX,
    ENGINE_LANG_RUST,
    ENGINE_LANG_JAVA,
    ENGINE_LANG_CPP,
    ENGINE_LANG_CSHARP,
    ENGINE_LANG_PHP,
    ENGINE_LANG_LUA,
    ENGINE_LANG_SCALA,
    ENGINE_LANG_KOTLIN,
    ENGINE_LANG_RUBY,
    ENGINE_LANG_C,
    ENGINE_LANG_BASH,
    ENGINE_LANG_ZIG,
    ENGINE_LANG_ELIXIR,
    ENGINE_LANG_HASKELL,
    ENGINE_LANG_OBJC,
    ENGINE_LANG_SWIFT,
    ENGINE_LANG_DART,
    ENGINE_LANG_PERL,
    ENGINE_LANG_GROOVY,
    ENGINE_LANG_ERLANG,
    ENGINE_LANG_R,
    ENGINE_LANG_HTML,
    ENGINE_LANG_CSS,
    ENGINE_LANG_SCSS,
    ENGINE_LANG_YAML,
    ENGINE_LANG_TOML,
    ENGINE_LANG_HCL,
    ENGINE_LANG_SQL,
    ENGINE_LANG_DOCKERFILE,
    // New languages (v0.5 expansion)
    ENGINE_LANG_CLOJURE,
    ENGINE_LANG_JULIA,
    ENGINE_LANG_JSON,
    ENGINE_LANG_XML,
    ENGINE_LANG_MARKDOWN,
    ENGINE_LANG_MAKEFILE,
    ENGINE_LANG_CMAKE,
    ENGINE_LANG_PROTOBUF,
    ENGINE_LANG_GRAPHQL,
    ENGINE_LANG_VUE,
    ENGINE_LANG_SVELTE,
    ENGINE_LANG_INI,
    // Scientific/math languages
    ENGINE_LANG_MATLAB,
    ENGINE_LANG_POWERSHELL,
    ENGINE_LANG_ASSEMBLY,
    ENGINE_LANG_COUNT
} EngineLanguage;

// --- Extraction result structs ---

typedef struct {
    const char *name;           // short name
    const char *qualified_name; // project.path.name
    const char *label;          // "Function", "Method", "Class", "Variable", "Module"
    const char *file_path;      // relative path
    uint32_t start_line;
    uint32_t end_line;
    const char *signature;              // parameter text (NULL if none)
    const char *return_type;            // return type text (NULL if none)
    const char *receiver;               // Go method receiver (NULL if none)
    const char *docstring;              // leading doc comment (NULL if none)
    const char *parent_class;           // enclosing class QN for methods (NULL if none)
    const char **decorators;            // NULL-terminated array (NULL if none)
    const char **base_classes;          // NULL-terminated array (NULL if none)
    const char **param_names;           // NULL-terminated array (NULL if none)
    const char **param_types;           // NULL-terminated array (NULL if none)
    const char **signature_param_types; // ordered internal signature types; "?" means unknown
    int signature_param_count;          // number of entries in signature_param_types
    const char **return_types;          // NULL-terminated array (NULL if none)
    const char *route_path;   // HTTP route path from decorator (e.g., "/api/users") or NULL
    const char *route_method; // HTTP method from decorator (e.g., "POST") or NULL
    int complexity;           // cyclomatic complexity
    int cognitive;            // cognitive complexity (nesting-weighted)
    int loop_count;           // number of loop constructs in the body
    int loop_depth;           // max nested-loop depth (bottleneck proxy)
    bool is_recursive;        // body contains a direct self-call (seed for "recursive")
    int param_count;          // number of parameters (large = complexity smell)
    int max_access_depth;     // deepest chained member/subscript access (a.b.c.d)
    int linear_scan_in_loop;  // count of linear-scan calls (find/contains/indexOf) inside loops
    int alloc_in_loop;        // count of allocation/append calls inside loops
    bool recursion_in_loop;   // a self-call occurs inside a loop body
    bool unguarded_recursion; // recursive with no self-call guarded by a conditional
    int lines;                // body line count
    uint32_t *fingerprint;    // MinHash fingerprint (arena-allocated, K values) or NULL
    int fingerprint_k;        // number of hash values (ENGINE_MINHASH_K or 0)
    bool is_exported;
    bool is_abstract;
    bool is_test;
    bool is_entry_point;
    const char *structural_profile; // AST structural profile (arena-allocated) or NULL
    const char *body_tokens; // space-separated raw identifier tokens from body (arena) or NULL
    /* Rust only: raw trait path from the exact `impl Trait for Type` block
     * that declared this method.  Kept at the tail so zero-initialised
     * callers in every other language remain ABI/source compatible. */
    const char *impl_trait;
} EngineDefinition;

/* Argument captured from a call expression */
typedef struct {
    const char *expr;    // raw expression text ("payload.info", "MY_URL", "'hello'")
    const char *value;   // resolved string value or NULL (constant propagation)
    const char *keyword; // keyword name if keyword arg ("url", "topic_id"), NULL if positional
    int index;           // positional index (0-based)
} EngineCallArg;

#define ENGINE_MAX_CALL_ARGS 8

/* Byte offsets are meaningful only within the source buffer that produced
 * them. C/C++/CUDA run both raw and preprocessed extraction passes, and those
 * buffers can contain unrelated occurrences at the same numeric span. */
typedef enum {
    ENGINE_SOURCE_ORIGIN_RAW = 0,
    ENGINE_SOURCE_ORIGIN_PREPROCESSED,
} EngineSourceOrigin;

typedef struct {
    const char *callee_name;            // raw callee text ("pkg.Func", "foo")
    const char *enclosing_func_qn;      // QN of enclosing function (or module QN)
    const char *first_string_arg;       // first string literal argument (URL, topic, key) or NULL
    const char *second_arg_name;        // second argument identifier (handler ref) or NULL
    EngineCallArg args[ENGINE_MAX_CALL_ARGS]; // first N arguments with expressions
    int arg_count;                      // number of captured arguments
    int loop_depth;                     // enclosing loop nesting at the call site
    int branch_depth;                   // enclosing branch nesting at the call site
    int start_line;                     // 1-based source line of the call (for def range-match)
    uint32_t site_start_byte;           // exact AST occurrence span; end > start when present
    uint32_t site_end_byte;             // exclusive byte offset in the source file
    EngineSourceOrigin source_origin;      // raw source or C-family preprocessed buffer
    bool is_method;                     // method/member call with a non-self receiver. Perl:
                                        // arrow/method call ($obj->m). TS/JS/TSX: member call
                                        // x.foo() whose receiver is not this/super. Default false.
    bool requires_lsp_resolution;       // synthetic semantic candidate (for example an implicit
                                        // C++ operator). Never fall back to textual resolution.
} EngineCall;

typedef struct {
    const char *local_name;  // local alias or name
    const char *module_path; // resolved module path / QN
} EngineImport;

typedef enum {
    ENGINE_USAGE_VALUE = 0,
    ENGINE_USAGE_CALL_REFERENCE,
} EngineUsageKind;

typedef struct {
    const char *ref_name;            // referenced identifier
    const char *enclosing_func_qn;   // QN of enclosing function (or module QN)
    EngineUsageKind kind;               // ordinary USAGE or explicit callable reference
    bool may_be_call_reference;      // syntactic candidate; exact LSP proof may upgrade its edge
    bool semantic_reference_blocked; // lexical evidence blocks only unproven textual fallback
    bool semantic_reference_local_shadow; // blocker belongs to a non-module lexical scope
    uint32_t lexical_scope_id;            // extraction-local scope instance; never graph identity
    uint32_t site_start_byte;             // exact reference-token span; end > start when present
    uint32_t site_end_byte;               // exclusive byte offset in the source file
    EngineSourceOrigin source_origin;        // raw source or C-family preprocessed buffer
} EngineUsage;

typedef struct {
    const char *exception_name;    // exception class/type name
    const char *enclosing_func_qn; // QN of enclosing function
} EngineThrow;

typedef struct {
    const char *var_name;          // variable name
    const char *enclosing_func_qn; // QN of enclosing function
    bool is_write;                 // true = write, false = read
} EngineReadWrite;

typedef struct {
    const char *type_name;         // referenced type/class name
    const char *enclosing_func_qn; // QN of enclosing function
} EngineTypeRef;

typedef struct {
    const char *env_key;           // environment variable key
    const char *enclosing_func_qn; // QN of enclosing function
} EngineEnvAccess;

typedef struct {
    const char *var_name;          // variable being assigned
    const char *type_name;         // class/type name of RHS constructor
    const char *enclosing_func_qn; // QN of enclosing function
} EngineTypeAssign;

// String reference: URL, config key, or async target found in source.
// Extracted from string literals during AST walk.
typedef enum {
    ENGINE_STRREF_URL = 0,    // REST path or full URL
    ENGINE_STRREF_CONFIG = 1, // config file path or env var key
} EngineStringRefKind;

typedef struct {
    const char *value;             // the string literal content
    const char *enclosing_func_qn; // QN of enclosing function
    const char *key_path;          // dotted key path from YAML/JSON nesting (NULL if flat)
    EngineStringRefKind kind;         // URL, CONFIG
} EngineStringRef;

/* Infrastructure binding: topic/queue → endpoint URL.
 * Extracted from YAML/HCL/JSON subscription/scheduler configs.
 * Used by pass_route_nodes to connect async Route nodes to handler services. */
typedef struct {
    const char *source_name; // topic, queue, or schedule name
    const char *target_url;  // push_endpoint, uri, or http_target URL
    const char *broker;      // "pubsub", "cloud_tasks", "cloud_scheduler", "sqs", "kafka"
} EngineInfraBinding;

/* Pub/sub channel participation.  One record per emit() or on()/addListener()
 * call detected in source — the receiver (e.g. Socket.IO client, EventEmitter
 * instance) is intentionally NOT identified; matching is by channel_name
 * across files, which captures the common pattern of one logical bus per
 * service.  Transport disambiguates Socket.IO vs EventEmitter vs future
 * detectors (Kafka, Cloud Pub/Sub, etc.). */
typedef enum {
    ENGINE_CHANNEL_EMIT = 0,
    ENGINE_CHANNEL_LISTEN = 1,
} EngineChannelDirection;

typedef struct {
    const char *channel_name;      // literal channel name (e.g. "user.created")
    const char *transport;         // "socketio", "event_emitter", ...
    const char *enclosing_func_qn; // QN of the function containing the emit/on call
    EngineChannelDirection direction;
} EngineChannel;

// Rust: impl Trait for Struct
typedef struct {
    const char *trait_name;  // trait name (raw text)
    const char *struct_name; // struct/type name (raw text)
    /* Exact extracted QN of the implementing type.  Unlike struct_name this
     * does not need a later leaf-name guess, and the relation exists even for
     * an empty `impl Trait for Type {}` block. */
    const char *struct_qn;
} EngineImplTrait;

typedef enum {
    ENGINE_RESOLVED_INVOCATION = 0,
    ENGINE_RESOLVED_CALL_REFERENCE,
} EngineResolvedKind;

// LSP-resolved invocation/reference: high-confidence type-aware resolution.
typedef struct {
    const char *caller_qn;         // enclosing function QN
    const char *callee_qn;         // resolved target QN (fully qualified)
    const char *strategy;          // "lsp_type_dispatch", "lsp_direct", etc.
    float confidence;              // 0.90-0.95
    const char *reason;            // diagnostic label for unresolved calls (NULL if resolved)
    EngineResolvedKind kind;          // invocation (CALLS) or explicit callable reference
    uint32_t site_start_byte;      // exact source occurrence; end > start when present
    uint32_t site_end_byte;        // exclusive byte offset in the source file
    EngineSourceOrigin source_origin; // raw source or C-family preprocessed buffer
} EngineResolvedCall;

typedef struct {
    EngineResolvedCall *items;
    int count;
    int cap;
} EngineResolvedCallArray;

// Growable arrays used during extraction.
typedef struct {
    EngineDefinition *items;
    int count;
    int cap;
} EngineDefArray;

typedef struct {
    EngineCall *items;
    int count;
    int cap;
} EngineCallArray;

typedef struct {
    EngineImport *items;
    int count;
    int cap;
} EngineImportArray;

typedef struct {
    EngineUsage *items;
    int count;
    int cap;
} EngineUsageArray;

typedef struct {
    EngineThrow *items;
    int count;
    int cap;
} EngineThrowArray;

typedef struct {
    EngineReadWrite *items;
    int count;
    int cap;
} EngineRWArray;

typedef struct {
    EngineTypeRef *items;
    int count;
    int cap;
} EngineTypeRefArray;

typedef struct {
    EngineEnvAccess *items;
    int count;
    int cap;
} EngineEnvAccessArray;

typedef struct {
    EngineTypeAssign *items;
    int count;
    int cap;
} EngineTypeAssignArray;

typedef struct {
    EngineStringRef *items;
    int count;
    int cap;
} EngineStringRefArray;

typedef struct {
    EngineInfraBinding *items;
    int count;
    int cap;
} EngineInfraBindingArray;

typedef struct {
    EngineImplTrait *items;
    int count;
    int cap;
} EngineImplTraitArray;

typedef struct {
    EngineChannel *items;
    int count;
    int cap;
} EngineChannelArray;

// Full extraction result for one file.
typedef struct EngineFileResult {
    EngineArena arena; // owns local memory; composites may also retain child arenas below

    EngineDefArray defs;
    EngineCallArray calls;
    EngineImportArray imports;
    EngineUsageArray usages;
    EngineThrowArray throws;
    EngineRWArray rw;
    EngineTypeRefArray type_refs;
    EngineEnvAccessArray env_accesses;
    EngineTypeAssignArray type_assigns;
    EngineImplTraitArray impl_traits;       // Rust: impl Trait for Struct pairs
    EngineResolvedCallArray resolved_calls; // LSP-resolved invocations/references (high confidence)
    EngineStringRefArray string_refs;       // URL/config string literals from AST
    EngineInfraBindingArray infra_bindings; // topic→URL pairs from IaC configs
    EngineChannelArray channels;            // Socket.IO / EventEmitter pub/sub participation

    const char *module_qn;      // module qualified name
    const char *namespace_name; // declared namespace/package (Java/Kotlin/C#/PHP), NULL if none
    const char **exports;       // NULL-terminated (NULL if none)
    const char **constants;     // NULL-terminated (NULL if none)
    const char **global_vars;   // NULL-terminated (NULL if none)
    const char **macros;        // NULL-terminated, C/C++ only (NULL if none)

    bool has_error;
    const char *error_msg;
    /* Best-effort parse-coverage signal (experimental). parse_incomplete is true
     * when the parse tree contains tree-sitter ERROR/MISSING nodes — constructs
     * in those regions are silently absent from the graph. error_ranges is a
     * compact "start-end,start-end" list of 1-based line ranges (arena-owned) or
     * NULL. This only marks what we can DETECT: the absence of a flag is NOT a
     * completeness guarantee. Callers should treat a flagged file as "prefer
     * grep here", never treat an unflagged file as provably complete. */
    bool parse_incomplete;
    const char *error_ranges;
    int error_region_count;
    bool is_test_file;
    int imports_count;
    TSTree *cached_tree;     // retained parse tree (caller frees via engine_free_tree)
    EngineLanguage cached_lang; // language of cached tree (for parser selection)

    // Retained source bytes — copied into `arena` by the parallel
    // extract pass so the fused cross-file LSP step in resolve_worker
    // can run without re-reading the file from disk. NULL when the
    // file exceeded the per-file (100 MB) or total (2 GB) retention
    // cap; in that case the cross-file LSP step is skipped for this
    // file (defs/calls already extracted are unaffected).
    const char *source;
    int source_len;

    // Composite extraction results (currently ObjectScript Studio Export)
    // retain their per-unit results so shallow-copied carrier strings remain
    // valid for the composite's full lifetime. Owned and recursively released
    // by engine_free_result(); ordinary single-file results leave these zeroed.
    struct EngineFileResult **owned_results;
    int owned_result_count;
} EngineFileResult;

// --- Enclosing function cache ---
// Avoids repeated parent-chain walks for nodes within the same function body.
// Each entry records a function's byte range and its precomputed QN.
#define EFC_SIZE 64 // power of 2 for fast modulo

typedef struct {
    uint32_t start_byte;
    uint32_t end_byte;
    const char *qn;
} EFCEntry;

typedef struct {
    EFCEntry entries[EFC_SIZE];
    int count;
} EFCache;

// --- Extraction context passed to sub-extractors ---

// Module-level string constant map (for constant propagation)
#define ENGINE_MAX_STRING_CONSTANTS 256
typedef struct {
    const char *names[ENGINE_MAX_STRING_CONSTANTS];
    const char *values[ENGINE_MAX_STRING_CONSTANTS];
    int count;
} EngineStringConstantMap;

// Forward declaration: ObjectScript macro table (defined in macro_table.h).
typedef struct EngineMacroTable EngineMacroTable;

// Method-return-type table for ObjectScript variable type inference. Populated
// from definition nodes (method QN -> declared return type) so a later
// `Set x = obj.Method()` can resolve x's class.
#define ENGINE_RETURN_TYPE_TABLE_CAP 2048

typedef struct {
    const char *method_qn;
    const char *return_type;
} EngineReturnTypeEntry;

typedef struct {
    EngineReturnTypeEntry entries[ENGINE_RETURN_TYPE_TABLE_CAP];
    int count;
} EngineReturnTypeTable;

typedef struct {
    EngineArena *arena;
    EngineFileResult *result;
    const char *source;
    int source_len;
    EngineLanguage language;
    const char *project;
    const char *rel_path;
    const char *module_qn;
    TSNode root;
    EFCache ef_cache;                            // enclosing function cache
    const char *enclosing_class_qn;              // for nested class QN computation
    EngineStringConstantMap string_constants;       // module-level NAME = "value" pairs
    const EngineMacroTable *macro_table;            // ObjectScript $$$macro table (NULL if none)
    const EngineReturnTypeTable *return_type_table; // ObjectScript method return types (NULL if none)
    /* Set by extract_class_variables around its extract_var_names calls, so a
     * class-body variable def records which class declares it (parent_class)
     * without changing its module-level qualified name. NULL elsewhere. */
    const char *var_parent_class;
} EngineExtractCtx;

// --- Public API ---

// Bind third-party allocators (tree-sitter, sqlite3) to mimalloc as
// defense-in-depth, so they never depend on the fragile MI_OVERRIDE symbol
// override (#424). MUST be called as the very first statement of main(), before
// any sqlite3_open*/sqlite3_initialize (SQLITE_CONFIG_MALLOC returns
// SQLITE_MISUSE once sqlite has initialized).
// Idempotent (static guard); intended for single-threaded startup. engine_init()
// also calls it so non-main entry points (pipeline passes) still get the binds.
// In the test build (no ENGINE_BIND_TS_ALLOCATOR) this is a no-op.
void engine_alloc_init(void);

// Initialize the library. Call once at startup. Returns 0 on success.
int engine_init(void);

// True when rel_path is in the crash-quarantine set — the newline-delimited list
// of files (ENGINE_INDEX_QUARANTINE_FILE) the crash supervisor pinned as crashers
// during its single-threaded recovery re-run. Loaded once, lazily; read-only
// after load. engine_extract_file short-circuits such files to an empty result so no
// pass can crash on them; the pipeline extract loops call this to also REPORT the
// skip as phase="crash". Always false (cheap no-op) when the env var is unset.
bool engine_index_is_quarantined(const char *rel_path);

// Phase a quarantined file was pinned under: "crash" (a fault signal) or "hang"
// (killed for making no progress). Returns NULL when rel_path is not quarantined.
// Drives the same lazy once-load as engine_index_is_quarantined. Used by the pipeline
// extract loops to report the skip's phase in skipped[] (falls back to "crash").
const char *engine_index_quarantine_phase(const char *rel_path);

// Crash-supervisor marker journal (parallel-safe): appends "S <rel_path>" /
// "D <rel_path>" to ENGINE_INDEX_MARKER_FILE. Files with an S but no D form the
// parent's crash/hang suspect set. No-ops when the env var is unset.
// engine_extract_file journals its own start/done; long-running per-file phases
// (cross-LSP resolve) call these around their per-file work so a hang there
// is attributed to the RIGHT file instead of a stale extraction marker.
void engine_index_mark_start(const char *rel_path);
void engine_index_mark_done(const char *rel_path);

// Extract all data from one file. Caller must call engine_free_result().
// source must remain valid for the duration of the call.
// timeout_micros: per-file parse timeout in microseconds (0 = no timeout).
EngineFileResult *engine_extract_file(const char *source, int source_len, EngineLanguage language,
                                const char *project, const char *rel_path, int64_t timeout_micros,
                                const char **extra_defines, // NULL-terminated, or NULL
                                const char **include_paths  // NULL-terminated, or NULL
);

// Pipeline-internal variant of engine_extract_file() carrying ObjectScript
// per-project tables (macro table + method-return-type table). The public
// engine_extract_file() is a thin wrapper that passes NULL, NULL for both.
EngineFileResult *engine_extract_file_ex(
    const char *source, int source_len, EngineLanguage language, const char *project,
    const char *rel_path, int64_t timeout_micros,
    const char **extra_defines,                 // NULL-terminated, or NULL
    const char **include_paths,                 // NULL-terminated, or NULL
    const EngineMacroTable *macro_table,           // ObjectScript macros, or NULL
    const EngineReturnTypeTable *return_type_table // OS return types, or NULL
);

// Free all memory associated with a result.
void engine_free_result(EngineFileResult *result);

// Free only the cached tree from a result (caller retained it for reuse).
void engine_free_tree(EngineFileResult *result);

// Free a standalone TSTree pointer (for Go layer cleanup).
void engine_free_tree_ptr(TSTree *tree);

// Reset the thread-local parser's internal state, releasing slab-allocated
// subtrees. Must be called BEFORE engine_slab_reset_thread() so the slab rebuild
// doesn't corrupt live parser state.
void engine_reset_thread_parser(void);

// Destroy the thread-local parser. Call on worker thread exit.
void engine_destroy_thread_parser(void);

// Shutdown the library. Call once at exit.
void engine_shutdown(void);

// Profiling: get accumulated parse/extraction times and file count.
typedef struct {
    uint64_t *parse_ns;
    uint64_t *extract_ns;
    uint64_t *files;
} engine_profile_out_t;
void engine_get_profile(engine_profile_out_t out);
uint64_t engine_get_lsp_ns(void);
uint64_t engine_get_preprocess_ns(void);
uint64_t engine_get_files_preprocessed(void);
void engine_reset_profile(void);

#if defined(ENGINE_KOTLIN_DEDUP_TEST_API) && ENGINE_KOTLIN_DEDUP_TEST_API
// Test-build-only operation counter for Kotlin operator-carrier deduplication.
// Production builds do not expose or retain this instrumentation.
void engine_kotlin_operator_dedup_test_reset(void);
uint64_t engine_kotlin_operator_dedup_test_comparisons(void);
#endif

#if defined(ENGINE_CALL_REFERENCE_LOOKUP_TEST_API) && ENGINE_CALL_REFERENCE_LOOKUP_TEST_API
// Test-build-only work counter for resolving a node's field role while
// classifying value references. Production builds retain no instrumentation.
void engine_usage_field_lookup_test_reset(void);
uint64_t engine_usage_field_lookup_test_work(void);
uint64_t engine_usage_slow_parent_fallback_test_count(void);
#endif

// Toggle C/C++ preprocessor Macro-node extraction (#375). The pipeline enables
// it only for full/advanced index modes (it dominates extraction on macro-dense
// codebases). Default ON. Set before extraction; read-only during.
void engine_set_macro_extraction(int enabled);
int engine_macro_extraction_enabled(void);

// --- Internal helpers used by extractors ---

// Growable array push functions (arena-allocated, no individual free needed).
void engine_defs_push(EngineDefArray *arr, EngineArena *a, EngineDefinition def);
void engine_calls_push(EngineCallArray *arr, EngineArena *a, EngineCall call);
void engine_imports_push(EngineImportArray *arr, EngineArena *a, EngineImport imp);
void engine_usages_push(EngineUsageArray *arr, EngineArena *a, EngineUsage usage);
void engine_throws_push(EngineThrowArray *arr, EngineArena *a, EngineThrow thr);
void engine_rw_push(EngineRWArray *arr, EngineArena *a, EngineReadWrite rw);
void engine_typerefs_push(EngineTypeRefArray *arr, EngineArena *a, EngineTypeRef tr);
void engine_envaccess_push(EngineEnvAccessArray *arr, EngineArena *a, EngineEnvAccess ea);
void engine_typeassign_push(EngineTypeAssignArray *arr, EngineArena *a, EngineTypeAssign ta);
void engine_stringref_push(EngineStringRefArray *arr, EngineArena *a, EngineStringRef sr);
void engine_infrabinding_push(EngineInfraBindingArray *arr, EngineArena *a, EngineInfraBinding ib);
void engine_impltrait_push(EngineImplTraitArray *arr, EngineArena *a, EngineImplTrait it);
void engine_resolvedcall_push(EngineResolvedCallArray *arr, EngineArena *a, EngineResolvedCall rc);
void engine_channels_push(EngineChannelArray *arr, EngineArena *a, EngineChannel ch);

// --- Sub-extractor entry points ---

void engine_extract_definitions(EngineExtractCtx *ctx);
void engine_extract_imports(EngineExtractCtx *ctx);
void engine_extract_usages(EngineExtractCtx *ctx);
void engine_extract_semantic(EngineExtractCtx *ctx);
void engine_extract_type_refs(EngineExtractCtx *ctx);
void engine_extract_env_accesses(EngineExtractCtx *ctx);
void engine_extract_type_assigns(EngineExtractCtx *ctx);
void engine_extract_channels(EngineExtractCtx *ctx);

// Single-pass unified extraction (replaces the 7 calls above except defs+imports).
void engine_extract_unified(EngineExtractCtx *ctx);


// --- Label predicates ---

// True when `label` names a TYPE-LIKE container definition — a node that can own
// methods/fields, be a base/embedded type, satisfy/declare an interface, and be a
// target of name→type resolution. The canonical set is:
//   Class, Struct, Interface, Enum, Type, Trait.
// Single source of truth for every type-resolution / registry-seeding /
// INHERITS·IMPLEMENTS / LSP-type-registrar consumer, so adding a new type-like
// label (e.g. "Struct" for Rust/Go/Swift/D structs) updates them all at once
// instead of scattering `|| strcmp(label,"Struct")==0` across the tree.
// `label` may be NULL (returns false). Defined in helpers.c.
bool engine_label_is_type_like(const char *label);

#endif // ENGINE_H
