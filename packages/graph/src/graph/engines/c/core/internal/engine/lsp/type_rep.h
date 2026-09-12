#ifndef ENGINE_LSP_TYPE_REP_H
#define ENGINE_LSP_TYPE_REP_H

#include "../arena.h"
#include <stdbool.h>
#include <stdint.h>

// EngineTypeKind enumerates all type representations.
typedef enum {
    ENGINE_TYPE_UNKNOWN = 0,
    ENGINE_TYPE_NAMED,       // named type: "Database", "http.Request"
    ENGINE_TYPE_POINTER,     // *T
    ENGINE_TYPE_SLICE,       // []T
    ENGINE_TYPE_MAP,         // map[K]V
    ENGINE_TYPE_CHANNEL,     // chan T
    ENGINE_TYPE_FUNC,        // func(params) returns
    ENGINE_TYPE_INTERFACE,   // interface{...}
    ENGINE_TYPE_STRUCT,      // struct{...}
    ENGINE_TYPE_BUILTIN,     // int, string, bool, error, etc.
    ENGINE_TYPE_TUPLE,       // multi-return (T1, T2) / TS tuple [T,U]
    ENGINE_TYPE_TYPE_PARAM,  // generic type parameter: T, K, V
    ENGINE_TYPE_REFERENCE,   // T& (C++ lvalue reference)
    ENGINE_TYPE_RVALUE_REF,  // T&& (C++ rvalue reference)
    ENGINE_TYPE_TEMPLATE,    // Parameterized type: vector<T> — stores template name + args
    ENGINE_TYPE_ALIAS,       // Type alias: using/typedef — stores alias name + underlying type
    ENGINE_TYPE_UNION,       // Python: A | B; TS: A | B | C — sorted-canonical list (shared)
    ENGINE_TYPE_LITERAL,     // Python: Literal["foo", 3] — wraps a base type + literal value text
    ENGINE_TYPE_PROTOCOL,    // Python: typing.Protocol — like INTERFACE but matched structurally
    ENGINE_TYPE_MODULE,      // Python: import os; os is a module-typed binding
    ENGINE_TYPE_CALLABLE,    // Python: Callable[[A, B], R] — untyped-named callable variant of FUNC

    // --- TS-specific kinds (added in TS LSP integration) ---
    ENGINE_TYPE_INTERSECTION,  // TS: A & B — intersection type
    ENGINE_TYPE_TS_LITERAL,    // TS: "foo" / 42 / true literal types (tag+value layout, distinct
                            // from Python's ENGINE_TYPE_LITERAL which uses base+literal_text)
    ENGINE_TYPE_INDEXED,       // TS: T[K] — indexed access type
    ENGINE_TYPE_KEYOF,         // TS: keyof T
    ENGINE_TYPE_TYPEOF_QUERY,  // TS: typeof x in type position
    ENGINE_TYPE_CONDITIONAL,   // TS: T extends U ? X : Y
    ENGINE_TYPE_OBJECT_LIT,    // TS: { a: T1; b: T2 } anonymous object type
    ENGINE_TYPE_INFER,         // TS: `infer X` placeholder inside conditional
    ENGINE_TYPE_MAPPED,        // TS: {[K in keyof T]: ...} — v1 stub, members may be NULL
} EngineTypeKind;

// Forward declaration
typedef struct EngineType EngineType;

// Language-specific adapter used to parse one ordered signature type spelling.
typedef const EngineType *(*EngineTypeTextParser)(EngineArena *arena, const char *text, void *parser_ctx);

// EngineTypeParam represents a generic type parameter with optional constraint.
typedef struct {
    const char* name;        // "T", "K", "V"
    const EngineType* constraint; // interface constraint, or NULL for "any"
} EngineTypeParam;

// EngineType is a tagged union representing Go types.
struct EngineType {
    EngineTypeKind kind;
    union {
        struct { const char* qualified_name; } named;      // NAMED
        struct { const EngineType* elem; } pointer;            // POINTER
        struct { const EngineType* elem; } slice;              // SLICE
        struct { const EngineType* key; const EngineType* value; } map;  // MAP
        struct { const EngineType* elem; int direction; } channel;    // CHANNEL (0=bidi, 1=send, 2=recv)
        struct {
            const char** param_names;  // NULL-terminated
            const EngineType** param_types; // NULL-terminated
            const EngineType** return_types; // NULL-terminated
        } func;                                             // FUNC
        struct {
            const char** method_names;  // NULL-terminated
            const EngineType** method_sigs; // NULL-terminated (each is FUNC)
        } interface_type;                                   // INTERFACE
        struct {
            const char** field_names;   // NULL-terminated
            const EngineType** field_types; // NULL-terminated
        } struct_type;                                      // STRUCT
        struct { const char* name; } builtin;               // BUILTIN
        struct {
            const EngineType** elems;      // NULL-terminated
            int count;
        } tuple;                                            // TUPLE
        struct { const char* name; } type_param;            // TYPE_PARAM
        struct { const EngineType* elem; } reference;            // REFERENCE / RVALUE_REF
        struct {
            const char* template_name;      // "std::vector", "std::map"
            const EngineType** template_args;  // NULL-terminated
            int arg_count;
        } template_type;                                      // TEMPLATE
        struct {
            const char* alias_qn;          // "proj.ns.MyAlias"
            const EngineType* underlying;     // the actual type it aliases
        } alias;                                              // ALIAS
        struct {
            const EngineType** members;       // NULL-terminated, deduplicated, sorted by kind/qn
            int count;
        } union_type;                                         // UNION / INTERSECTION (shared)
        struct {
            const EngineType* base;           // base type (e.g. BUILTIN("int"), BUILTIN("str"))
            const char* literal_text;      // canonical text: "3", "\"foo\"", "True"
        } literal;                                            // LITERAL (Python)
        struct {
            const char* qualified_name;    // e.g. "typing.Iterable"
            const char** method_names;     // NULL-terminated method names — structural matching
            const EngineType** method_sigs;   // NULL-terminated signatures (each is FUNC/CALLABLE)
        } protocol;                                           // PROTOCOL
        struct {
            const char* module_qn;         // module qualified name (matches EngineImport.module_path)
        } module;                                             // MODULE
        struct {
            const EngineType** param_types;   // NULL-terminated; NULL element means "Any" / unknown
            const EngineType* return_type;    // single return; for tuples wrap in ENGINE_TYPE_TUPLE
            int param_count;               // -1 = elliptic / Callable[..., R]
        } callable;                                           // CALLABLE

        // --- TS-specific data ---
        struct {
            // Tag distinguishes string / number / boolean / bigint / null / undefined literals.
            // For boolean literals, value points to "true" or "false".
            const char* tag;               // "string" | "number" | "boolean" | "bigint" | "null" | "undefined"
            const char* value;             // textual representation; arena-owned
        } literal_ts;                                         // TS_LITERAL
        struct {
            const EngineType* object;         // T in T[K]
            const EngineType* index;          // K in T[K]
        } indexed;                                            // INDEXED
        struct { const EngineType* operand; } keyof;             // KEYOF
        struct { const char* expr; } typeof_query;            // TYPEOF_QUERY (referenced expression text)
        struct {
            const EngineType* check;          // T
            const EngineType* extends;        // U
            const EngineType* true_branch;    // X
            const EngineType* false_branch;   // Y
        } conditional;                                        // CONDITIONAL
        struct {
            const char** prop_names;       // NULL-terminated
            const EngineType** prop_types;    // NULL-terminated, parallel to prop_names
            const EngineType* call_signature; // FUNC type or NULL
            const EngineType* index_value;    // type produced by string/number index, or NULL
        } object_lit;                                         // OBJECT_LIT
        struct { const char* name; } infer;                   // INFER (e.g., `infer R`)
        struct {
            const char* key_name;          // "K" in {[K in keyof T]: V}
            const EngineType* key_constraint; // `keyof T`
            const EngineType* value;          // V (may reference key_name as TYPE_PARAM)
        } mapped;                                             // MAPPED (v1 stub-friendly)
    } data;
};

// Constructors (arena-allocated)
const EngineType* engine_type_unknown(void);
const EngineType* engine_type_named(EngineArena* a, const char* qualified_name);
const EngineType* engine_type_pointer(EngineArena* a, const EngineType* elem);
const EngineType* engine_type_slice(EngineArena* a, const EngineType* elem);
const EngineType* engine_type_map(EngineArena* a, const EngineType* key, const EngineType* value);
const EngineType* engine_type_channel(EngineArena* a, const EngineType* elem, int direction);
const EngineType* engine_type_func(EngineArena* a, const char** param_names, const EngineType** param_types, const EngineType** return_types);
// Materialize exactly count positional parameter slots. NULL, empty, exact "?",
// and parser failures become UNKNOWN; the returned vector is NULL-terminated.
const EngineType **engine_type_materialize_signature_params(EngineArena *a, const char *const *type_texts,
                                                      int count, EngineTypeTextParser parser,
                                                      void *parser_ctx);
// Rebuild a FUNC with new returns while preserving its parameter names/types.
const EngineType *engine_type_func_replace_returns(EngineArena *a, const EngineType *old_signature,
                                             const EngineType *const *new_return_types);
const EngineType* engine_type_builtin(EngineArena* a, const char* name);
const EngineType* engine_type_tuple(EngineArena* a, const EngineType** elems, int count);
const EngineType* engine_type_type_param(EngineArena* a, const char* name);
const EngineType* engine_type_reference(EngineArena* a, const EngineType* elem);
const EngineType* engine_type_rvalue_ref(EngineArena* a, const EngineType* elem);
const EngineType* engine_type_template(EngineArena* a, const char* name, const EngineType** args, int arg_count);
const EngineType* engine_type_alias(EngineArena* a, const char* alias_qn, const EngineType* underlying);

// Python-flavored constructors. UNION normalizes input: nested unions are
// flattened, duplicates removed, single-member unions collapse to that
// member, and the empty union is UNKNOWN. Members must be arena-allocated.
// Shared with TS LSP — both call this same constructor for `A | B`.
const EngineType* engine_type_union(EngineArena* a, const EngineType** members, int count);
const EngineType* engine_type_optional(EngineArena* a, const EngineType* t);  // Optional[T] == Union[T, None]
const EngineType* engine_type_literal(EngineArena* a, const EngineType* base, const char* literal_text);
const EngineType* engine_type_protocol(EngineArena* a, const char* qualified_name,
    const char** method_names, const EngineType** method_sigs);
const EngineType* engine_type_module(EngineArena* a, const char* module_qn);
const EngineType* engine_type_callable(EngineArena* a, const EngineType** param_types, int param_count,
    const EngineType* return_type);

// --- TS-specific constructors ---
const EngineType* engine_type_intersection(EngineArena* a, const EngineType** members, int count);
// tag is one of "string"|"number"|"boolean"|"bigint"|"null"|"undefined".
// Distinct from engine_type_literal (Python) which uses base+literal_text.
const EngineType* engine_type_ts_literal(EngineArena* a, const char* tag, const char* value);
const EngineType* engine_type_indexed(EngineArena* a, const EngineType* object, const EngineType* index);
const EngineType* engine_type_keyof(EngineArena* a, const EngineType* operand);
const EngineType* engine_type_typeof_query(EngineArena* a, const char* expr);
const EngineType* engine_type_conditional(EngineArena* a,
    const EngineType* check, const EngineType* extends,
    const EngineType* true_branch, const EngineType* false_branch);
// prop_names and prop_types are NULL-terminated parallel arrays; either may be NULL for empty.
const EngineType* engine_type_object_lit(EngineArena* a,
    const char** prop_names, const EngineType** prop_types,
    const EngineType* call_signature, const EngineType* index_value);
const EngineType* engine_type_infer(EngineArena* a, const char* name);
const EngineType* engine_type_mapped(EngineArena* a,
    const char* key_name, const EngineType* key_constraint, const EngineType* value);

// Operations
const EngineType* engine_type_deref(const EngineType* t);         // remove one pointer level
const EngineType* engine_type_elem(const EngineType* t);           // get element type (slice/chan/pointer)
bool engine_type_is_unknown(const EngineType* t);
bool engine_type_is_interface(const EngineType* t);
bool engine_type_is_pointer(const EngineType* t);
bool engine_type_is_reference(const EngineType* t);
bool engine_type_is_union(const EngineType* t);
bool engine_type_is_protocol(const EngineType* t);
bool engine_type_is_module(const EngineType* t);

// Structural equality on type representation (used by union dedup and
// protocol-method-set matching). Two types are equal if their kinds match
// and their structural members match recursively.
bool engine_type_equal(const EngineType* a, const EngineType* b);

// Test whether `candidate` satisfies the structural protocol `proto`.
// Walks proto.method_names against candidate's method set (NAMED → registry
// lookup is the caller's job; this helper only matches existing method
// signatures stored on a PROTOCOL).
bool engine_type_protocol_satisfied_by(const EngineType* proto, const EngineType* candidate);

// Follow alias chain with cycle detection (max 16 levels).
const EngineType* engine_type_resolve_alias(const EngineType* t);

// Generic type substitution: replace type params in t with concrete types.
// type_params: NULL-terminated array of param names
// type_args: corresponding concrete types
const EngineType* engine_type_substitute(EngineArena* a, const EngineType* t,
    const char** type_params, const EngineType** type_args);

#endif // ENGINE_LSP_TYPE_REP_H
