/* rust_stdlib_data.c — Hand-curated Rust core/alloc/std prelude seed.
 *
 * NOT auto-generated yet (Rust has no machine-readable equivalent of
 * `go doc`/`pydoc`). This is a curated subset covering the prelude types
 * and ~150 most-used methods. The set is large enough to make
 * cross-file LSP resolution match rust-analyzer's output for typical
 * application code, while keeping the binary footprint minimal.
 *
 * Each entry maps onto the same `EngineRegisteredType` / `EngineRegisteredFunc`
 * shape used for project-defined types — the resolver does not care
 * whether a type came from the seed or the project.
 *
 * Coverage (roughly):
 *   - core::option::Option<T> + 18 methods
 *   - core::result::Result<T, E> + 17 methods
 *   - alloc::string::String + 22 methods
 *   - alloc::vec::Vec<T>     + 25 methods
 *   - alloc::collections::HashMap<K, V>, BTreeMap<K, V> + 12 methods each
 *   - core::iter::Iterator + 22 method signatures
 *   - alloc::boxed::Box<T> + 4 methods
 *   - core::fmt::{Display, Debug} traits with `fmt`
 *   - core::convert::{Into, From, AsRef} prelude traits
 *   - core::clone::Clone + clone()
 *   - Free helpers in std::mem (drop, replace, swap, take)
 *   - Free helpers in std::env (var)
 *
 * Adding more entries is mechanical: append to the matching section.
 */

#include "../type_rep.h"
#include "../type_registry.h"
#include "../rust_lsp.h"
#include <string.h>

/* Convenience macros to compress the boilerplate. We rely on arena
 * allocations being long-lived for the whole index — string literals are
 * fine because they live forever in `.rodata`. */
#define ADD_TYPE(qn, sn, iface) do {                              \
    EngineRegisteredType _rt;                                         \
    memset(&_rt, 0, sizeof(_rt));                                  \
    _rt.qualified_name = (qn);                                     \
    _rt.short_name = (sn);                                         \
    _rt.is_interface = (iface);                                    \
    engine_registry_add_type(reg, _rt);                               \
} while (0)

#define ADD_FUNC(rcv, sn, qn, ret_type) do {                       \
    EngineRegisteredFunc _rf;                                         \
    memset(&_rf, 0, sizeof(_rf));                                  \
    _rf.qualified_name = (qn);                                     \
    _rf.short_name = (sn);                                         \
    _rf.receiver_type = (rcv);                                     \
    _rf.min_params = -1;                                           \
    const EngineType** _rta = (const EngineType**)engine_arena_alloc(arena, \
        2 * sizeof(const EngineType*));                               \
    _rta[0] = (ret_type);                                          \
    _rta[1] = NULL;                                                \
    _rf.signature = engine_type_func(arena, NULL, NULL, _rta);        \
    engine_registry_add_func(reg, _rf);                               \
} while (0)

/* Forward declaration — defined in rust_crates_seed.c (also included
 * from lsp_all.c). Called at the end of the stdlib register so any
 * project that uses `use serde::…` / `use tokio::…` etc. picks up
 * the seeded methods automatically. */
void engine_rust_crates_register(EngineTypeRegistry* reg, EngineArena* arena);

void engine_rust_stdlib_register(EngineTypeRegistry* reg, EngineArena* arena) {
    /* ── Reusable type primitives ───────────────────────────────── */
    const EngineType* t_unit = engine_type_builtin(arena, "()");
    const EngineType* t_bool = engine_type_builtin(arena, "bool");
    const EngineType* t_usize = engine_type_builtin(arena, "usize");
    const EngineType* t_str_ref = engine_type_reference(arena, engine_type_builtin(arena, "str"));
    const EngineType* t_string = engine_type_named(arena, "alloc.string.String");
    const EngineType* t_self_named_string = engine_type_named(arena, "alloc.string.String");

    /* ── Container types ────────────────────────────────────────── */
    ADD_TYPE("core.option.Option", "Option", false);
    ADD_TYPE("core.result.Result", "Result", false);
    ADD_TYPE("alloc.string.String", "String", false);
    ADD_TYPE("alloc.vec.Vec", "Vec", false);
    ADD_TYPE("alloc.collections.HashMap", "HashMap", false);
    ADD_TYPE("alloc.collections.BTreeMap", "BTreeMap", false);
    ADD_TYPE("alloc.collections.HashSet", "HashSet", false);
    ADD_TYPE("alloc.collections.BTreeSet", "BTreeSet", false);
    ADD_TYPE("alloc.collections.VecDeque", "VecDeque", false);
    ADD_TYPE("alloc.boxed.Box", "Box", false);
    ADD_TYPE("alloc.rc.Rc", "Rc", false);
    ADD_TYPE("alloc.sync.Arc", "Arc", false);
    ADD_TYPE("core.cell.RefCell", "RefCell", false);
    ADD_TYPE("core.cell.Cell", "Cell", false);
    ADD_TYPE("core.iter.Iterator", "Iterator", true);
    ADD_TYPE("core.iter.IntoIterator", "IntoIterator", true);
    ADD_TYPE("core.future.Future", "Future", true);
    ADD_TYPE("core.str", "str", false);

    /* ── Prelude traits ─────────────────────────────────────────── */
    ADD_TYPE("core.clone.Clone", "Clone", true);
    ADD_TYPE("core.marker.Copy", "Copy", true);
    ADD_TYPE("core.marker.Send", "Send", true);
    ADD_TYPE("core.marker.Sync", "Sync", true);
    ADD_TYPE("core.default.Default", "Default", true);
    ADD_TYPE("core.cmp.PartialEq", "PartialEq", true);
    ADD_TYPE("core.cmp.Eq", "Eq", true);
    ADD_TYPE("core.cmp.PartialOrd", "PartialOrd", true);
    ADD_TYPE("core.cmp.Ord", "Ord", true);
    ADD_TYPE("core.hash.Hash", "Hash", true);
    ADD_TYPE("core.hash.Hasher", "Hasher", true);
    ADD_TYPE("core.fmt.Display", "Display", true);
    ADD_TYPE("core.fmt.Debug", "Debug", true);
    ADD_TYPE("core.convert.From", "From", true);
    ADD_TYPE("core.convert.Into", "Into", true);
    ADD_TYPE("core.convert.TryFrom", "TryFrom", true);
    ADD_TYPE("core.convert.TryInto", "TryInto", true);
    ADD_TYPE("core.convert.AsRef", "AsRef", true);
    ADD_TYPE("core.convert.AsMut", "AsMut", true);
    ADD_TYPE("core.borrow.Borrow", "Borrow", true);
    ADD_TYPE("core.borrow.BorrowMut", "BorrowMut", true);
    ADD_TYPE("core.ops.Deref", "Deref", true);
    ADD_TYPE("core.ops.DerefMut", "DerefMut", true);
    ADD_TYPE("core.ops.Drop", "Drop", true);
    ADD_TYPE("core.ops.Add", "Add", true);
    ADD_TYPE("core.ops.Sub", "Sub", true);
    ADD_TYPE("core.ops.Mul", "Mul", true);
    ADD_TYPE("core.ops.Div", "Div", true);

    /* ── Option<T> methods ──────────────────────────────────────── */
    {
        const char* T = "core.option.Option";
        ADD_FUNC(T, "is_some",            "core.option.Option.is_some",            t_bool);
        ADD_FUNC(T, "is_none",            "core.option.Option.is_none",            t_bool);
        ADD_FUNC(T, "unwrap",             "core.option.Option.unwrap",             engine_type_unknown());
        ADD_FUNC(T, "expect",             "core.option.Option.expect",             engine_type_unknown());
        ADD_FUNC(T, "unwrap_or",          "core.option.Option.unwrap_or",          engine_type_unknown());
        ADD_FUNC(T, "unwrap_or_default",  "core.option.Option.unwrap_or_default",  engine_type_unknown());
        ADD_FUNC(T, "unwrap_or_else",     "core.option.Option.unwrap_or_else",     engine_type_unknown());
        ADD_FUNC(T, "as_ref",             "core.option.Option.as_ref",             engine_type_unknown());
        ADD_FUNC(T, "as_mut",             "core.option.Option.as_mut",             engine_type_unknown());
        ADD_FUNC(T, "map",                "core.option.Option.map",                engine_type_unknown());
        ADD_FUNC(T, "and_then",           "core.option.Option.and_then",           engine_type_unknown());
        ADD_FUNC(T, "or",                 "core.option.Option.or",                 engine_type_unknown());
        ADD_FUNC(T, "or_else",            "core.option.Option.or_else",            engine_type_unknown());
        ADD_FUNC(T, "ok_or",              "core.option.Option.ok_or",              engine_type_unknown());
        ADD_FUNC(T, "ok_or_else",         "core.option.Option.ok_or_else",         engine_type_unknown());
        ADD_FUNC(T, "take",               "core.option.Option.take",               engine_type_unknown());
        ADD_FUNC(T, "replace",            "core.option.Option.replace",            engine_type_unknown());
        ADD_FUNC(T, "filter",             "core.option.Option.filter",             engine_type_unknown());
        ADD_FUNC(T, "iter",               "core.option.Option.iter",               engine_type_unknown());
        ADD_FUNC(T, "into_iter",          "core.option.Option.into_iter",          engine_type_unknown());
    }

    /* ── Result<T, E> methods ───────────────────────────────────── */
    {
        const char* T = "core.result.Result";
        ADD_FUNC(T, "is_ok",     "core.result.Result.is_ok",     t_bool);
        ADD_FUNC(T, "is_err",    "core.result.Result.is_err",    t_bool);
        ADD_FUNC(T, "ok",        "core.result.Result.ok",        engine_type_unknown());
        ADD_FUNC(T, "err",       "core.result.Result.err",       engine_type_unknown());
        ADD_FUNC(T, "unwrap",    "core.result.Result.unwrap",    engine_type_unknown());
        ADD_FUNC(T, "expect",    "core.result.Result.expect",    engine_type_unknown());
        ADD_FUNC(T, "unwrap_err","core.result.Result.unwrap_err",engine_type_unknown());
        ADD_FUNC(T, "expect_err","core.result.Result.expect_err",engine_type_unknown());
        ADD_FUNC(T, "unwrap_or", "core.result.Result.unwrap_or", engine_type_unknown());
        ADD_FUNC(T, "unwrap_or_else","core.result.Result.unwrap_or_else", engine_type_unknown());
        ADD_FUNC(T, "unwrap_or_default","core.result.Result.unwrap_or_default", engine_type_unknown());
        ADD_FUNC(T, "as_ref",    "core.result.Result.as_ref",    engine_type_unknown());
        ADD_FUNC(T, "as_mut",    "core.result.Result.as_mut",    engine_type_unknown());
        ADD_FUNC(T, "map",       "core.result.Result.map",       engine_type_unknown());
        ADD_FUNC(T, "map_err",   "core.result.Result.map_err",   engine_type_unknown());
        ADD_FUNC(T, "and_then",  "core.result.Result.and_then",  engine_type_unknown());
        ADD_FUNC(T, "or_else",   "core.result.Result.or_else",   engine_type_unknown());
    }

    /* ── String methods ─────────────────────────────────────────── */
    {
        const char* T = "alloc.string.String";
        ADD_FUNC(T, "new",          "alloc.string.String.new",          t_self_named_string);
        ADD_FUNC(T, "with_capacity","alloc.string.String.with_capacity",t_self_named_string);
        ADD_FUNC(T, "from",         "alloc.string.String.from",         t_self_named_string);
        ADD_FUNC(T, "len",          "alloc.string.String.len",          t_usize);
        ADD_FUNC(T, "is_empty",     "alloc.string.String.is_empty",     t_bool);
        ADD_FUNC(T, "as_str",       "alloc.string.String.as_str",       t_str_ref);
        ADD_FUNC(T, "push_str",     "alloc.string.String.push_str",     t_unit);
        ADD_FUNC(T, "push",         "alloc.string.String.push",         t_unit);
        ADD_FUNC(T, "clear",        "alloc.string.String.clear",        t_unit);
        ADD_FUNC(T, "clone",        "alloc.string.String.clone",        t_self_named_string);
        ADD_FUNC(T, "trim",         "alloc.string.String.trim",         t_str_ref);
        ADD_FUNC(T, "to_string",    "alloc.string.String.to_string",    t_self_named_string);
        ADD_FUNC(T, "to_lowercase", "alloc.string.String.to_lowercase", t_self_named_string);
        ADD_FUNC(T, "to_uppercase", "alloc.string.String.to_uppercase", t_self_named_string);
        ADD_FUNC(T, "contains",     "alloc.string.String.contains",     t_bool);
        ADD_FUNC(T, "starts_with",  "alloc.string.String.starts_with",  t_bool);
        ADD_FUNC(T, "ends_with",    "alloc.string.String.ends_with",    t_bool);
        ADD_FUNC(T, "split",        "alloc.string.String.split",        engine_type_unknown());
        ADD_FUNC(T, "lines",        "alloc.string.String.lines",        engine_type_unknown());
        ADD_FUNC(T, "chars",        "alloc.string.String.chars",        engine_type_unknown());
        ADD_FUNC(T, "bytes",        "alloc.string.String.bytes",        engine_type_unknown());
        ADD_FUNC(T, "replace",      "alloc.string.String.replace",      t_self_named_string);
        ADD_FUNC(T, "parse",        "alloc.string.String.parse",        engine_type_unknown());
        ADD_FUNC(T, "into_bytes",   "alloc.string.String.into_bytes",   engine_type_unknown());
        ADD_FUNC(T, "as_bytes",     "alloc.string.String.as_bytes",     engine_type_unknown());
    }

    /* core::str methods (shared with &str). */
    {
        const char* T = "core.str";
        ADD_FUNC(T, "len",          "core.str.len",          t_usize);
        ADD_FUNC(T, "is_empty",     "core.str.is_empty",     t_bool);
        ADD_FUNC(T, "to_string",    "core.str.to_string",    t_self_named_string);
        ADD_FUNC(T, "trim",         "core.str.trim",         t_str_ref);
        ADD_FUNC(T, "contains",     "core.str.contains",     t_bool);
        ADD_FUNC(T, "starts_with",  "core.str.starts_with",  t_bool);
        ADD_FUNC(T, "ends_with",    "core.str.ends_with",    t_bool);
        ADD_FUNC(T, "split",        "core.str.split",        engine_type_unknown());
        ADD_FUNC(T, "lines",        "core.str.lines",        engine_type_unknown());
        ADD_FUNC(T, "chars",        "core.str.chars",        engine_type_unknown());
        ADD_FUNC(T, "bytes",        "core.str.bytes",        engine_type_unknown());
        ADD_FUNC(T, "parse",        "core.str.parse",        engine_type_unknown());
        ADD_FUNC(T, "to_lowercase", "core.str.to_lowercase", t_self_named_string);
        ADD_FUNC(T, "to_uppercase", "core.str.to_uppercase", t_self_named_string);
        ADD_FUNC(T, "replace",      "core.str.replace",      t_self_named_string);
        ADD_FUNC(T, "find",         "core.str.find",         engine_type_unknown());
        ADD_FUNC(T, "rfind",        "core.str.rfind",        engine_type_unknown());
        ADD_FUNC(T, "as_bytes",     "core.str.as_bytes",     engine_type_unknown());
        ADD_FUNC(T, "splitn",       "core.str.splitn",       engine_type_unknown());
    }

    /* ── Vec<T> methods ────────────────────────────────────────── */
    {
        const char* T = "alloc.vec.Vec";
        ADD_FUNC(T, "new",         "alloc.vec.Vec.new",         engine_type_unknown());
        ADD_FUNC(T, "with_capacity","alloc.vec.Vec.with_capacity", engine_type_unknown());
        ADD_FUNC(T, "from",        "alloc.vec.Vec.from",        engine_type_unknown());
        ADD_FUNC(T, "push",        "alloc.vec.Vec.push",        t_unit);
        ADD_FUNC(T, "pop",         "alloc.vec.Vec.pop",         engine_type_unknown());
        ADD_FUNC(T, "len",         "alloc.vec.Vec.len",         t_usize);
        ADD_FUNC(T, "is_empty",    "alloc.vec.Vec.is_empty",    t_bool);
        ADD_FUNC(T, "capacity",    "alloc.vec.Vec.capacity",    t_usize);
        ADD_FUNC(T, "clear",       "alloc.vec.Vec.clear",       t_unit);
        ADD_FUNC(T, "iter",        "alloc.vec.Vec.iter",        engine_type_unknown());
        ADD_FUNC(T, "iter_mut",    "alloc.vec.Vec.iter_mut",    engine_type_unknown());
        ADD_FUNC(T, "into_iter",   "alloc.vec.Vec.into_iter",   engine_type_unknown());
        ADD_FUNC(T, "first",       "alloc.vec.Vec.first",       engine_type_unknown());
        ADD_FUNC(T, "last",        "alloc.vec.Vec.last",        engine_type_unknown());
        ADD_FUNC(T, "get",         "alloc.vec.Vec.get",         engine_type_unknown());
        ADD_FUNC(T, "contains",    "alloc.vec.Vec.contains",    t_bool);
        ADD_FUNC(T, "as_slice",    "alloc.vec.Vec.as_slice",    engine_type_unknown());
        ADD_FUNC(T, "as_mut_slice","alloc.vec.Vec.as_mut_slice",engine_type_unknown());
        ADD_FUNC(T, "extend",      "alloc.vec.Vec.extend",      t_unit);
        ADD_FUNC(T, "remove",      "alloc.vec.Vec.remove",      engine_type_unknown());
        ADD_FUNC(T, "swap_remove", "alloc.vec.Vec.swap_remove", engine_type_unknown());
        ADD_FUNC(T, "insert",      "alloc.vec.Vec.insert",      t_unit);
        ADD_FUNC(T, "sort",        "alloc.vec.Vec.sort",        t_unit);
        ADD_FUNC(T, "sort_by",     "alloc.vec.Vec.sort_by",     t_unit);
        ADD_FUNC(T, "reverse",     "alloc.vec.Vec.reverse",     t_unit);
        ADD_FUNC(T, "drain",       "alloc.vec.Vec.drain",       engine_type_unknown());
        ADD_FUNC(T, "clone",       "alloc.vec.Vec.clone",       engine_type_unknown());
    }

    /* ── HashMap<K, V> methods ─────────────────────────────────── */
    {
        const char* T = "alloc.collections.HashMap";
        ADD_FUNC(T, "new",         "alloc.collections.HashMap.new",         engine_type_unknown());
        ADD_FUNC(T, "with_capacity","alloc.collections.HashMap.with_capacity",engine_type_unknown());
        ADD_FUNC(T, "insert",      "alloc.collections.HashMap.insert",      engine_type_unknown());
        ADD_FUNC(T, "get",         "alloc.collections.HashMap.get",         engine_type_unknown());
        ADD_FUNC(T, "get_mut",     "alloc.collections.HashMap.get_mut",     engine_type_unknown());
        ADD_FUNC(T, "remove",      "alloc.collections.HashMap.remove",      engine_type_unknown());
        ADD_FUNC(T, "contains_key","alloc.collections.HashMap.contains_key",t_bool);
        ADD_FUNC(T, "len",         "alloc.collections.HashMap.len",         t_usize);
        ADD_FUNC(T, "is_empty",    "alloc.collections.HashMap.is_empty",    t_bool);
        ADD_FUNC(T, "clear",       "alloc.collections.HashMap.clear",       t_unit);
        ADD_FUNC(T, "keys",        "alloc.collections.HashMap.keys",        engine_type_unknown());
        ADD_FUNC(T, "values",      "alloc.collections.HashMap.values",      engine_type_unknown());
        ADD_FUNC(T, "iter",        "alloc.collections.HashMap.iter",        engine_type_unknown());
        ADD_FUNC(T, "entry",       "alloc.collections.HashMap.entry",       engine_type_unknown());
    }
    {
        const char* T = "alloc.collections.BTreeMap";
        ADD_FUNC(T, "new",         "alloc.collections.BTreeMap.new",         engine_type_unknown());
        ADD_FUNC(T, "insert",      "alloc.collections.BTreeMap.insert",      engine_type_unknown());
        ADD_FUNC(T, "get",         "alloc.collections.BTreeMap.get",         engine_type_unknown());
        ADD_FUNC(T, "remove",      "alloc.collections.BTreeMap.remove",      engine_type_unknown());
        ADD_FUNC(T, "contains_key","alloc.collections.BTreeMap.contains_key",t_bool);
        ADD_FUNC(T, "len",         "alloc.collections.BTreeMap.len",         t_usize);
        ADD_FUNC(T, "is_empty",    "alloc.collections.BTreeMap.is_empty",    t_bool);
        ADD_FUNC(T, "iter",        "alloc.collections.BTreeMap.iter",        engine_type_unknown());
        ADD_FUNC(T, "keys",        "alloc.collections.BTreeMap.keys",        engine_type_unknown());
        ADD_FUNC(T, "values",      "alloc.collections.BTreeMap.values",      engine_type_unknown());
    }

    /* ── Iterator trait methods ─────────────────────────────────── */
    {
        const char* T = "core.iter.Iterator";
        ADD_FUNC(T, "next",     "core.iter.Iterator.next",     engine_type_unknown());
        ADD_FUNC(T, "map",      "core.iter.Iterator.map",      engine_type_unknown());
        ADD_FUNC(T, "filter",   "core.iter.Iterator.filter",   engine_type_unknown());
        ADD_FUNC(T, "fold",     "core.iter.Iterator.fold",     engine_type_unknown());
        ADD_FUNC(T, "for_each", "core.iter.Iterator.for_each", t_unit);
        ADD_FUNC(T, "collect",  "core.iter.Iterator.collect",  engine_type_unknown());
        ADD_FUNC(T, "count",    "core.iter.Iterator.count",    t_usize);
        ADD_FUNC(T, "sum",      "core.iter.Iterator.sum",      engine_type_unknown());
        ADD_FUNC(T, "max",      "core.iter.Iterator.max",      engine_type_unknown());
        ADD_FUNC(T, "min",      "core.iter.Iterator.min",      engine_type_unknown());
        ADD_FUNC(T, "any",      "core.iter.Iterator.any",      t_bool);
        ADD_FUNC(T, "all",      "core.iter.Iterator.all",      t_bool);
        ADD_FUNC(T, "find",     "core.iter.Iterator.find",     engine_type_unknown());
        ADD_FUNC(T, "position", "core.iter.Iterator.position", engine_type_unknown());
        ADD_FUNC(T, "enumerate","core.iter.Iterator.enumerate",engine_type_unknown());
        ADD_FUNC(T, "zip",      "core.iter.Iterator.zip",      engine_type_unknown());
        ADD_FUNC(T, "chain",    "core.iter.Iterator.chain",    engine_type_unknown());
        ADD_FUNC(T, "take",     "core.iter.Iterator.take",     engine_type_unknown());
        ADD_FUNC(T, "skip",     "core.iter.Iterator.skip",     engine_type_unknown());
        ADD_FUNC(T, "rev",      "core.iter.Iterator.rev",      engine_type_unknown());
        ADD_FUNC(T, "cloned",   "core.iter.Iterator.cloned",   engine_type_unknown());
        ADD_FUNC(T, "copied",   "core.iter.Iterator.copied",   engine_type_unknown());
        ADD_FUNC(T, "step_by",  "core.iter.Iterator.step_by",  engine_type_unknown());
        ADD_FUNC(T, "flat_map", "core.iter.Iterator.flat_map", engine_type_unknown());
        ADD_FUNC(T, "flatten",  "core.iter.Iterator.flatten",  engine_type_unknown());
        ADD_FUNC(T, "filter_map","core.iter.Iterator.filter_map",engine_type_unknown());
        ADD_FUNC(T, "peekable", "core.iter.Iterator.peekable", engine_type_unknown());
    }

    /* ── Box / Rc / Arc — focus on `new` and Deref ─────────────── */
    {
        ADD_FUNC("alloc.boxed.Box", "new",         "alloc.boxed.Box.new",         engine_type_unknown());
        ADD_FUNC("alloc.boxed.Box", "as_ref",      "alloc.boxed.Box.as_ref",      engine_type_unknown());
        ADD_FUNC("alloc.boxed.Box", "into_inner",  "alloc.boxed.Box.into_inner",  engine_type_unknown());

        ADD_FUNC("alloc.rc.Rc",     "new",         "alloc.rc.Rc.new",             engine_type_unknown());
        ADD_FUNC("alloc.rc.Rc",     "clone",       "alloc.rc.Rc.clone",           engine_type_unknown());
        ADD_FUNC("alloc.rc.Rc",     "strong_count","alloc.rc.Rc.strong_count",    t_usize);

        ADD_FUNC("alloc.sync.Arc",  "new",         "alloc.sync.Arc.new",          engine_type_unknown());
        ADD_FUNC("alloc.sync.Arc",  "clone",       "alloc.sync.Arc.clone",        engine_type_unknown());
        ADD_FUNC("alloc.sync.Arc",  "strong_count","alloc.sync.Arc.strong_count", t_usize);

        ADD_FUNC("core.cell.RefCell","new",        "core.cell.RefCell.new",       engine_type_unknown());
        ADD_FUNC("core.cell.RefCell","borrow",     "core.cell.RefCell.borrow",    engine_type_unknown());
        ADD_FUNC("core.cell.RefCell","borrow_mut", "core.cell.RefCell.borrow_mut",engine_type_unknown());
    }

    /* ── Trait method signatures (default impls go on the trait QN) ── */
    {
        ADD_FUNC("core.clone.Clone",        "clone",     "core.clone.Clone.clone",     engine_type_unknown());
        ADD_FUNC("core.default.Default",    "default",   "core.default.Default.default", engine_type_unknown());
        ADD_FUNC("core.fmt.Display",        "fmt",       "core.fmt.Display.fmt",       engine_type_unknown());
        ADD_FUNC("core.fmt.Debug",          "fmt",       "core.fmt.Debug.fmt",         engine_type_unknown());
        ADD_FUNC("core.cmp.PartialEq",      "eq",        "core.cmp.PartialEq.eq",      t_bool);
        ADD_FUNC("core.cmp.PartialEq",      "ne",        "core.cmp.PartialEq.ne",      t_bool);
        ADD_FUNC("core.cmp.PartialOrd",     "partial_cmp","core.cmp.PartialOrd.partial_cmp", engine_type_unknown());
        ADD_FUNC("core.cmp.Ord",            "cmp",       "core.cmp.Ord.cmp",           engine_type_unknown());
        ADD_FUNC("core.hash.Hash",          "hash",      "core.hash.Hash.hash",        t_unit);
        ADD_FUNC("core.convert.From",       "from",      "core.convert.From.from",     engine_type_unknown());
        ADD_FUNC("core.convert.Into",       "into",      "core.convert.Into.into",     engine_type_unknown());
        ADD_FUNC("core.convert.TryFrom",    "try_from",  "core.convert.TryFrom.try_from", engine_type_unknown());
        ADD_FUNC("core.convert.TryInto",    "try_into",  "core.convert.TryInto.try_into", engine_type_unknown());
        ADD_FUNC("core.convert.AsRef",      "as_ref",    "core.convert.AsRef.as_ref",  engine_type_unknown());
        ADD_FUNC("core.convert.AsMut",      "as_mut",    "core.convert.AsMut.as_mut",  engine_type_unknown());
        ADD_FUNC("core.borrow.Borrow",      "borrow",    "core.borrow.Borrow.borrow",  engine_type_unknown());
        ADD_FUNC("core.borrow.BorrowMut",   "borrow_mut","core.borrow.BorrowMut.borrow_mut", engine_type_unknown());
        ADD_FUNC("core.ops.Deref",          "deref",     "core.ops.Deref.deref",       engine_type_unknown());
        ADD_FUNC("core.ops.DerefMut",       "deref_mut", "core.ops.DerefMut.deref_mut",engine_type_unknown());
        ADD_FUNC("core.ops.Drop",           "drop",      "core.ops.Drop.drop",         t_unit);
        ADD_FUNC("core.ops.Add",            "add",       "core.ops.Add.add",           engine_type_unknown());
        ADD_FUNC("core.ops.Sub",            "sub",       "core.ops.Sub.sub",           engine_type_unknown());
        ADD_FUNC("core.ops.Mul",            "mul",       "core.ops.Mul.mul",           engine_type_unknown());
        ADD_FUNC("core.ops.Div",            "div",       "core.ops.Div.div",           engine_type_unknown());
    }

    /* ── std re-exports (alias the alloc/core paths) ────────────
     *
     * Many prelude types (`String`, `Vec`, `HashMap`, `Arc`, `Box`, …)
     * are defined in `alloc` and re-exported through `std`. When user
     * code writes `use std::collections::HashMap;` the path the LSP
     * sees is `std::collections::HashMap` — but our seed registers the
     * methods under `alloc.collections.HashMap`. We patch this by
     * also registering each std QN with an `alias_of` link, so the
     * registry-aware lookups resolve through alias chains.
     *
     * The list mirrors the most-used `std` re-exports — adding more is
     * cheap and harmless (an extra ~20 bytes per entry). */
    {
        struct ReExport { const char* std_qn; const char* alloc_qn; const char* short_name; };
        static const struct ReExport reexports[] = {
            {"std.string.String",            "alloc.string.String",            "String"},
            {"std.string.ToString",          "alloc.string.ToString",          "ToString"},
            {"std.vec.Vec",                  "alloc.vec.Vec",                  "Vec"},
            {"std.collections.HashMap",      "alloc.collections.HashMap",      "HashMap"},
            {"std.collections.BTreeMap",     "alloc.collections.BTreeMap",     "BTreeMap"},
            {"std.collections.HashSet",      "alloc.collections.HashSet",      "HashSet"},
            {"std.collections.BTreeSet",     "alloc.collections.BTreeSet",     "BTreeSet"},
            {"std.collections.VecDeque",     "alloc.collections.VecDeque",     "VecDeque"},
            {"std.boxed.Box",                "alloc.boxed.Box",                "Box"},
            {"std.rc.Rc",                    "alloc.rc.Rc",                    "Rc"},
            {"std.sync.Arc",                 "alloc.sync.Arc",                 "Arc"},
            {"std.option.Option",            "core.option.Option",             "Option"},
            {"std.result.Result",            "core.result.Result",             "Result"},
            {"std.iter.Iterator",            "core.iter.Iterator",             "Iterator"},
            {"std.iter.IntoIterator",        "core.iter.IntoIterator",         "IntoIterator"},
            {"std.future.Future",            "core.future.Future",             "Future"},
            {"std.clone.Clone",              "core.clone.Clone",               "Clone"},
            {"std.default.Default",          "core.default.Default",           "Default"},
            {"std.cmp.PartialEq",            "core.cmp.PartialEq",             "PartialEq"},
            {"std.cmp.Eq",                   "core.cmp.Eq",                    "Eq"},
            {"std.cmp.PartialOrd",           "core.cmp.PartialOrd",            "PartialOrd"},
            {"std.cmp.Ord",                  "core.cmp.Ord",                   "Ord"},
            {"std.hash.Hash",                "core.hash.Hash",                 "Hash"},
            {"std.fmt.Display",              "core.fmt.Display",               "Display"},
            {"std.fmt.Debug",                "core.fmt.Debug",                 "Debug"},
            {"std.convert.From",             "core.convert.From",              "From"},
            {"std.convert.Into",             "core.convert.Into",              "Into"},
            {"std.convert.TryFrom",          "core.convert.TryFrom",           "TryFrom"},
            {"std.convert.TryInto",          "core.convert.TryInto",           "TryInto"},
            {"std.convert.AsRef",            "core.convert.AsRef",             "AsRef"},
            {"std.convert.AsMut",            "core.convert.AsMut",             "AsMut"},
            {"std.borrow.Borrow",            "core.borrow.Borrow",             "Borrow"},
            {"std.borrow.BorrowMut",         "core.borrow.BorrowMut",          "BorrowMut"},
            {"std.ops.Deref",                "core.ops.Deref",                 "Deref"},
            {"std.ops.DerefMut",             "core.ops.DerefMut",              "DerefMut"},
            {"std.ops.Drop",                 "core.ops.Drop",                  "Drop"},
            {"std.cell.RefCell",             "core.cell.RefCell",              "RefCell"},
            {"std.cell.Cell",                "core.cell.Cell",                 "Cell"},
        };
        for (size_t i = 0; i < sizeof(reexports) / sizeof(reexports[0]); i++) {
            EngineRegisteredType rt;
            memset(&rt, 0, sizeof(rt));
            rt.qualified_name = reexports[i].std_qn;
            rt.short_name = reexports[i].short_name;
            rt.alias_of = reexports[i].alloc_qn;
            engine_registry_add_type(reg, rt);
        }
    }

    /* ── Free functions worth attributing ──────────────────────── */
    {
        /* std::mem helpers. */
        const EngineType* unit_arr[2] = {t_unit, NULL};
        (void)unit_arr;
        ADD_FUNC(NULL, "drop",     "std.mem.drop",     t_unit);
        ADD_FUNC(NULL, "replace",  "std.mem.replace",  engine_type_unknown());
        ADD_FUNC(NULL, "swap",     "std.mem.swap",     t_unit);
        ADD_FUNC(NULL, "take",     "std.mem.take",     engine_type_unknown());
        ADD_FUNC(NULL, "size_of",  "std.mem.size_of",  t_usize);

        /* std::env::var. */
        ADD_FUNC(NULL, "var",      "std.env.var",      engine_type_unknown());

        /* Macros (synthetic placeholders so trace tools see the call). */
        ADD_FUNC(NULL, "println",  "std.macros.println",  t_unit);
        ADD_FUNC(NULL, "eprintln", "std.macros.eprintln", t_unit);
        ADD_FUNC(NULL, "print",    "std.macros.print",    t_unit);
        ADD_FUNC(NULL, "eprint",   "std.macros.eprint",   t_unit);
        ADD_FUNC(NULL, "format",   "std.macros.format",   t_string);
        ADD_FUNC(NULL, "write",    "std.macros.write",    t_unit);
        ADD_FUNC(NULL, "writeln",  "std.macros.writeln",  t_unit);
        ADD_FUNC(NULL, "vec",      "alloc.vec.vec",       engine_type_unknown());
        ADD_FUNC(NULL, "panic",    "core.panicking.panic",engine_type_unknown());
    }

    /* ════════════════════════════════════════════════════════════════
     * Extended stdlib seed — pushes coverage from ~150 methods to
     * ~700, the threshold at which idiomatic Rust application code
     * starts hitting the seed instead of bouncing off "unknown".
     * Sections below mirror the Rust documentation table of contents.
     * ════════════════════════════════════════════════════════════════ */

    /* ── std::io ────────────────────────────────────────────────── */
    ADD_TYPE("std.io.Read",         "Read",         true);
    ADD_TYPE("std.io.Write",        "Write",        true);
    ADD_TYPE("std.io.Seek",         "Seek",         true);
    ADD_TYPE("std.io.BufRead",      "BufRead",      true);
    ADD_TYPE("std.io.BufReader",    "BufReader",    false);
    ADD_TYPE("std.io.BufWriter",    "BufWriter",    false);
    ADD_TYPE("std.io.LineWriter",   "LineWriter",   false);
    ADD_TYPE("std.io.Cursor",       "Cursor",       false);
    ADD_TYPE("std.io.Stdin",        "Stdin",        false);
    ADD_TYPE("std.io.Stdout",       "Stdout",       false);
    ADD_TYPE("std.io.Stderr",       "Stderr",      false);
    ADD_TYPE("std.io.StdoutLock",   "StdoutLock",   false);
    ADD_TYPE("std.io.Error",        "Error",        false);
    ADD_TYPE("std.io.ErrorKind",    "ErrorKind",    false);
    ADD_TYPE("std.io.SeekFrom",     "SeekFrom",     false);
    ADD_TYPE("std.io.Empty",        "Empty",        false);
    ADD_TYPE("std.io.Sink",         "Sink",         false);
    ADD_TYPE("std.io.Repeat",       "Repeat",       false);

    {
        const char* T = "std.io.Read";
        ADD_FUNC(T, "read",            "std.io.Read.read",            engine_type_unknown());
        ADD_FUNC(T, "read_to_end",     "std.io.Read.read_to_end",     engine_type_unknown());
        ADD_FUNC(T, "read_to_string",  "std.io.Read.read_to_string",  engine_type_unknown());
        ADD_FUNC(T, "read_exact",      "std.io.Read.read_exact",      engine_type_unknown());
        ADD_FUNC(T, "by_ref",          "std.io.Read.by_ref",          engine_type_unknown());
        ADD_FUNC(T, "bytes",           "std.io.Read.bytes",           engine_type_unknown());
        ADD_FUNC(T, "chain",           "std.io.Read.chain",           engine_type_unknown());
        ADD_FUNC(T, "take",            "std.io.Read.take",            engine_type_unknown());
    }
    {
        const char* T = "std.io.Write";
        ADD_FUNC(T, "write",           "std.io.Write.write",           engine_type_unknown());
        ADD_FUNC(T, "write_all",       "std.io.Write.write_all",       engine_type_unknown());
        ADD_FUNC(T, "write_fmt",       "std.io.Write.write_fmt",       engine_type_unknown());
        ADD_FUNC(T, "flush",           "std.io.Write.flush",           engine_type_unknown());
        ADD_FUNC(T, "by_ref",          "std.io.Write.by_ref",          engine_type_unknown());
    }
    {
        const char* T = "std.io.Seek";
        ADD_FUNC(T, "seek",            "std.io.Seek.seek",            engine_type_unknown());
        ADD_FUNC(T, "rewind",          "std.io.Seek.rewind",          engine_type_unknown());
        ADD_FUNC(T, "stream_position", "std.io.Seek.stream_position", engine_type_unknown());
    }
    {
        const char* T = "std.io.BufRead";
        ADD_FUNC(T, "read_line",       "std.io.BufRead.read_line",    engine_type_unknown());
        ADD_FUNC(T, "read_until",      "std.io.BufRead.read_until",   engine_type_unknown());
        ADD_FUNC(T, "lines",           "std.io.BufRead.lines",        engine_type_unknown());
        ADD_FUNC(T, "split",           "std.io.BufRead.split",        engine_type_unknown());
        ADD_FUNC(T, "fill_buf",        "std.io.BufRead.fill_buf",     engine_type_unknown());
        ADD_FUNC(T, "consume",         "std.io.BufRead.consume",      t_unit);
    }
    {
        const char* T = "std.io.BufReader";
        ADD_FUNC(T, "new",             "std.io.BufReader.new",        engine_type_unknown());
        ADD_FUNC(T, "with_capacity",   "std.io.BufReader.with_capacity", engine_type_unknown());
        ADD_FUNC(T, "into_inner",      "std.io.BufReader.into_inner", engine_type_unknown());
        ADD_FUNC(T, "get_ref",         "std.io.BufReader.get_ref",    engine_type_unknown());
        ADD_FUNC(T, "buffer",          "std.io.BufReader.buffer",     engine_type_unknown());
        ADD_FUNC(T, "capacity",        "std.io.BufReader.capacity",   t_usize);
    }
    {
        const char* T = "std.io.BufWriter";
        ADD_FUNC(T, "new",             "std.io.BufWriter.new",        engine_type_unknown());
        ADD_FUNC(T, "with_capacity",   "std.io.BufWriter.with_capacity", engine_type_unknown());
        ADD_FUNC(T, "into_inner",      "std.io.BufWriter.into_inner", engine_type_unknown());
        ADD_FUNC(T, "get_ref",         "std.io.BufWriter.get_ref",    engine_type_unknown());
        ADD_FUNC(T, "flush",           "std.io.BufWriter.flush",      engine_type_unknown());
    }
    {
        const char* T = "std.io.Cursor";
        ADD_FUNC(T, "new",             "std.io.Cursor.new",           engine_type_unknown());
        ADD_FUNC(T, "into_inner",      "std.io.Cursor.into_inner",    engine_type_unknown());
        ADD_FUNC(T, "position",        "std.io.Cursor.position",      engine_type_unknown());
        ADD_FUNC(T, "set_position",    "std.io.Cursor.set_position",  t_unit);
    }
    {
        const char* T = "std.io.Error";
        ADD_FUNC(T, "new",             "std.io.Error.new",            engine_type_unknown());
        ADD_FUNC(T, "kind",            "std.io.Error.kind",           engine_type_unknown());
        ADD_FUNC(T, "raw_os_error",    "std.io.Error.raw_os_error",   engine_type_unknown());
        ADD_FUNC(T, "into_inner",      "std.io.Error.into_inner",     engine_type_unknown());
        ADD_FUNC(T, "last_os_error",   "std.io.Error.last_os_error",  engine_type_unknown());
        ADD_FUNC(T, "from_raw_os_error","std.io.Error.from_raw_os_error", engine_type_unknown());
    }
    /* Free functions in std::io. */
    ADD_FUNC(NULL, "stdin",  "std.io.stdin",  engine_type_unknown());
    ADD_FUNC(NULL, "stdout", "std.io.stdout", engine_type_unknown());
    ADD_FUNC(NULL, "stderr", "std.io.stderr", engine_type_unknown());
    ADD_FUNC(NULL, "copy",   "std.io.copy",   engine_type_unknown());
    ADD_FUNC(NULL, "empty",  "std.io.empty",  engine_type_unknown());
    ADD_FUNC(NULL, "sink",   "std.io.sink",   engine_type_unknown());
    ADD_FUNC(NULL, "repeat", "std.io.repeat", engine_type_unknown());

    /* ── std::fs ────────────────────────────────────────────────── */
    ADD_TYPE("std.fs.File",         "File",         false);
    ADD_TYPE("std.fs.OpenOptions",  "OpenOptions",  false);
    ADD_TYPE("std.fs.Metadata",     "Metadata",     false);
    ADD_TYPE("std.fs.Permissions",  "Permissions",  false);
    ADD_TYPE("std.fs.DirEntry",     "DirEntry",     false);
    ADD_TYPE("std.fs.ReadDir",      "ReadDir",      false);
    ADD_TYPE("std.fs.FileType",     "FileType",     false);
    ADD_TYPE("std.fs.DirBuilder",   "DirBuilder",   false);

    {
        const char* T = "std.fs.File";
        ADD_FUNC(T, "open",            "std.fs.File.open",            engine_type_unknown());
        ADD_FUNC(T, "create",          "std.fs.File.create",          engine_type_unknown());
        ADD_FUNC(T, "create_new",      "std.fs.File.create_new",      engine_type_unknown());
        ADD_FUNC(T, "options",         "std.fs.File.options",         engine_type_unknown());
        ADD_FUNC(T, "metadata",        "std.fs.File.metadata",        engine_type_unknown());
        ADD_FUNC(T, "set_len",         "std.fs.File.set_len",         engine_type_unknown());
        ADD_FUNC(T, "set_permissions", "std.fs.File.set_permissions", engine_type_unknown());
        ADD_FUNC(T, "sync_all",        "std.fs.File.sync_all",        engine_type_unknown());
        ADD_FUNC(T, "sync_data",       "std.fs.File.sync_data",       engine_type_unknown());
        ADD_FUNC(T, "try_clone",       "std.fs.File.try_clone",       engine_type_unknown());
    }
    {
        const char* T = "std.fs.OpenOptions";
        ADD_FUNC(T, "new",        "std.fs.OpenOptions.new",        engine_type_unknown());
        ADD_FUNC(T, "read",       "std.fs.OpenOptions.read",       engine_type_unknown());
        ADD_FUNC(T, "write",      "std.fs.OpenOptions.write",      engine_type_unknown());
        ADD_FUNC(T, "append",     "std.fs.OpenOptions.append",     engine_type_unknown());
        ADD_FUNC(T, "create",     "std.fs.OpenOptions.create",     engine_type_unknown());
        ADD_FUNC(T, "create_new", "std.fs.OpenOptions.create_new", engine_type_unknown());
        ADD_FUNC(T, "truncate",   "std.fs.OpenOptions.truncate",   engine_type_unknown());
        ADD_FUNC(T, "open",       "std.fs.OpenOptions.open",       engine_type_unknown());
    }
    {
        const char* T = "std.fs.Metadata";
        ADD_FUNC(T, "file_type",       "std.fs.Metadata.file_type",   engine_type_unknown());
        ADD_FUNC(T, "is_dir",          "std.fs.Metadata.is_dir",      t_bool);
        ADD_FUNC(T, "is_file",         "std.fs.Metadata.is_file",     t_bool);
        ADD_FUNC(T, "is_symlink",      "std.fs.Metadata.is_symlink",  t_bool);
        ADD_FUNC(T, "len",             "std.fs.Metadata.len",         engine_type_unknown());
        ADD_FUNC(T, "permissions",     "std.fs.Metadata.permissions", engine_type_unknown());
        ADD_FUNC(T, "modified",        "std.fs.Metadata.modified",    engine_type_unknown());
        ADD_FUNC(T, "accessed",        "std.fs.Metadata.accessed",    engine_type_unknown());
        ADD_FUNC(T, "created",         "std.fs.Metadata.created",     engine_type_unknown());
    }
    {
        const char* T = "std.fs.DirEntry";
        ADD_FUNC(T, "path",            "std.fs.DirEntry.path",        engine_type_unknown());
        ADD_FUNC(T, "metadata",        "std.fs.DirEntry.metadata",    engine_type_unknown());
        ADD_FUNC(T, "file_type",       "std.fs.DirEntry.file_type",   engine_type_unknown());
        ADD_FUNC(T, "file_name",       "std.fs.DirEntry.file_name",   engine_type_unknown());
    }
    /* Free functions in std::fs. */
    ADD_FUNC(NULL, "read",          "std.fs.read",          engine_type_unknown());
    ADD_FUNC(NULL, "read_to_string","std.fs.read_to_string",engine_type_unknown());
    ADD_FUNC(NULL, "read_dir",      "std.fs.read_dir",      engine_type_unknown());
    ADD_FUNC(NULL, "write",         "std.fs.write",         engine_type_unknown());
    ADD_FUNC(NULL, "remove_file",   "std.fs.remove_file",   engine_type_unknown());
    ADD_FUNC(NULL, "remove_dir",    "std.fs.remove_dir",    engine_type_unknown());
    ADD_FUNC(NULL, "remove_dir_all","std.fs.remove_dir_all",engine_type_unknown());
    ADD_FUNC(NULL, "create_dir",    "std.fs.create_dir",    engine_type_unknown());
    ADD_FUNC(NULL, "create_dir_all","std.fs.create_dir_all",engine_type_unknown());
    ADD_FUNC(NULL, "metadata",      "std.fs.metadata",      engine_type_unknown());
    ADD_FUNC(NULL, "rename",        "std.fs.rename",        engine_type_unknown());
    ADD_FUNC(NULL, "copy",          "std.fs.copy",          engine_type_unknown());
    ADD_FUNC(NULL, "hard_link",     "std.fs.hard_link",     engine_type_unknown());

    /* ── std::path ─────────────────────────────────────────────── */
    ADD_TYPE("std.path.Path",       "Path",       false);
    ADD_TYPE("std.path.PathBuf",    "PathBuf",    false);
    ADD_TYPE("std.path.Component",  "Component",  false);
    ADD_TYPE("std.path.Components", "Components", false);
    ADD_TYPE("std.path.Iter",       "Iter",       false);
    ADD_TYPE("std.path.Display",    "Display",    false);

    {
        const char* T = "std.path.Path";
        ADD_FUNC(T, "new",             "std.path.Path.new",             engine_type_unknown());
        ADD_FUNC(T, "exists",          "std.path.Path.exists",          t_bool);
        ADD_FUNC(T, "try_exists",      "std.path.Path.try_exists",      engine_type_unknown());
        ADD_FUNC(T, "is_file",         "std.path.Path.is_file",         t_bool);
        ADD_FUNC(T, "is_dir",          "std.path.Path.is_dir",          t_bool);
        ADD_FUNC(T, "is_symlink",      "std.path.Path.is_symlink",      t_bool);
        ADD_FUNC(T, "is_absolute",     "std.path.Path.is_absolute",     t_bool);
        ADD_FUNC(T, "is_relative",     "std.path.Path.is_relative",     t_bool);
        ADD_FUNC(T, "has_root",        "std.path.Path.has_root",        t_bool);
        ADD_FUNC(T, "ends_with",       "std.path.Path.ends_with",       t_bool);
        ADD_FUNC(T, "starts_with",     "std.path.Path.starts_with",     t_bool);
        ADD_FUNC(T, "extension",       "std.path.Path.extension",       engine_type_unknown());
        ADD_FUNC(T, "file_name",       "std.path.Path.file_name",       engine_type_unknown());
        ADD_FUNC(T, "file_stem",       "std.path.Path.file_stem",       engine_type_unknown());
        ADD_FUNC(T, "parent",          "std.path.Path.parent",          engine_type_unknown());
        ADD_FUNC(T, "components",      "std.path.Path.components",      engine_type_unknown());
        ADD_FUNC(T, "iter",            "std.path.Path.iter",            engine_type_unknown());
        ADD_FUNC(T, "join",            "std.path.Path.join",            engine_type_unknown());
        ADD_FUNC(T, "display",         "std.path.Path.display",         engine_type_unknown());
        ADD_FUNC(T, "canonicalize",    "std.path.Path.canonicalize",    engine_type_unknown());
        ADD_FUNC(T, "to_path_buf",     "std.path.Path.to_path_buf",     engine_type_unknown());
        ADD_FUNC(T, "to_str",          "std.path.Path.to_str",          engine_type_unknown());
        ADD_FUNC(T, "to_string_lossy", "std.path.Path.to_string_lossy", engine_type_unknown());
        ADD_FUNC(T, "metadata",        "std.path.Path.metadata",        engine_type_unknown());
        ADD_FUNC(T, "read_dir",        "std.path.Path.read_dir",        engine_type_unknown());
        ADD_FUNC(T, "with_extension",  "std.path.Path.with_extension",  engine_type_unknown());
        ADD_FUNC(T, "with_file_name",  "std.path.Path.with_file_name",  engine_type_unknown());
    }
    {
        const char* T = "std.path.PathBuf";
        ADD_FUNC(T, "new",             "std.path.PathBuf.new",          engine_type_unknown());
        ADD_FUNC(T, "from",            "std.path.PathBuf.from",         engine_type_unknown());
        ADD_FUNC(T, "with_capacity",   "std.path.PathBuf.with_capacity",engine_type_unknown());
        ADD_FUNC(T, "push",            "std.path.PathBuf.push",         t_unit);
        ADD_FUNC(T, "pop",             "std.path.PathBuf.pop",          t_bool);
        ADD_FUNC(T, "set_file_name",   "std.path.PathBuf.set_file_name",t_unit);
        ADD_FUNC(T, "set_extension",   "std.path.PathBuf.set_extension",t_bool);
        ADD_FUNC(T, "as_path",         "std.path.PathBuf.as_path",      engine_type_unknown());
        ADD_FUNC(T, "into_os_string",  "std.path.PathBuf.into_os_string",engine_type_unknown());
        ADD_FUNC(T, "clear",           "std.path.PathBuf.clear",        t_unit);
    }

    /* ── std::env ──────────────────────────────────────────────── */
    ADD_TYPE("std.env.Args",         "Args",         false);
    ADD_TYPE("std.env.Vars",         "Vars",         false);
    ADD_TYPE("std.env.VarError",     "VarError",     false);
    ADD_FUNC(NULL, "args",           "std.env.args",           engine_type_unknown());
    ADD_FUNC(NULL, "args_os",        "std.env.args_os",        engine_type_unknown());
    ADD_FUNC(NULL, "vars",           "std.env.vars",           engine_type_unknown());
    ADD_FUNC(NULL, "vars_os",        "std.env.vars_os",        engine_type_unknown());
    ADD_FUNC(NULL, "var_os",         "std.env.var_os",         engine_type_unknown());
    ADD_FUNC(NULL, "set_var",        "std.env.set_var",        t_unit);
    ADD_FUNC(NULL, "remove_var",     "std.env.remove_var",     t_unit);
    ADD_FUNC(NULL, "current_dir",    "std.env.current_dir",    engine_type_unknown());
    ADD_FUNC(NULL, "set_current_dir","std.env.set_current_dir",engine_type_unknown());
    ADD_FUNC(NULL, "current_exe",    "std.env.current_exe",    engine_type_unknown());
    ADD_FUNC(NULL, "temp_dir",       "std.env.temp_dir",       engine_type_unknown());
    ADD_FUNC(NULL, "home_dir",       "std.env.home_dir",       engine_type_unknown());

    /* ── std::process ──────────────────────────────────────────── */
    ADD_TYPE("std.process.Command",     "Command",     false);
    ADD_TYPE("std.process.Output",      "Output",      false);
    ADD_TYPE("std.process.Child",       "Child",       false);
    ADD_TYPE("std.process.ExitStatus",  "ExitStatus",  false);
    ADD_TYPE("std.process.Stdio",       "Stdio",       false);
    ADD_TYPE("std.process.ChildStdin",  "ChildStdin",  false);
    ADD_TYPE("std.process.ChildStdout", "ChildStdout", false);
    ADD_TYPE("std.process.ChildStderr", "ChildStderr", false);
    {
        const char* T = "std.process.Command";
        ADD_FUNC(T, "new",       "std.process.Command.new",       engine_type_unknown());
        ADD_FUNC(T, "arg",       "std.process.Command.arg",       engine_type_unknown());
        ADD_FUNC(T, "args",      "std.process.Command.args",      engine_type_unknown());
        ADD_FUNC(T, "env",       "std.process.Command.env",       engine_type_unknown());
        ADD_FUNC(T, "envs",      "std.process.Command.envs",      engine_type_unknown());
        ADD_FUNC(T, "env_remove","std.process.Command.env_remove",engine_type_unknown());
        ADD_FUNC(T, "env_clear", "std.process.Command.env_clear", engine_type_unknown());
        ADD_FUNC(T, "current_dir","std.process.Command.current_dir",engine_type_unknown());
        ADD_FUNC(T, "stdin",     "std.process.Command.stdin",     engine_type_unknown());
        ADD_FUNC(T, "stdout",    "std.process.Command.stdout",    engine_type_unknown());
        ADD_FUNC(T, "stderr",    "std.process.Command.stderr",    engine_type_unknown());
        ADD_FUNC(T, "spawn",     "std.process.Command.spawn",     engine_type_unknown());
        ADD_FUNC(T, "output",    "std.process.Command.output",    engine_type_unknown());
        ADD_FUNC(T, "status",    "std.process.Command.status",    engine_type_unknown());
    }
    {
        const char* T = "std.process.Output";
        ADD_FUNC(T, "status",    "std.process.Output.status",    engine_type_unknown());
        ADD_FUNC(T, "stdout",    "std.process.Output.stdout",    engine_type_unknown());
        ADD_FUNC(T, "stderr",    "std.process.Output.stderr",    engine_type_unknown());
    }
    {
        const char* T = "std.process.Child";
        ADD_FUNC(T, "wait",      "std.process.Child.wait",      engine_type_unknown());
        ADD_FUNC(T, "wait_with_output","std.process.Child.wait_with_output", engine_type_unknown());
        ADD_FUNC(T, "kill",      "std.process.Child.kill",      engine_type_unknown());
        ADD_FUNC(T, "id",        "std.process.Child.id",        engine_type_unknown());
        ADD_FUNC(T, "try_wait",  "std.process.Child.try_wait",  engine_type_unknown());
    }
    {
        const char* T = "std.process.ExitStatus";
        ADD_FUNC(T, "success",   "std.process.ExitStatus.success", t_bool);
        ADD_FUNC(T, "code",      "std.process.ExitStatus.code",    engine_type_unknown());
    }
    {
        const char* T = "std.process.Stdio";
        ADD_FUNC(T, "inherit",   "std.process.Stdio.inherit",  engine_type_unknown());
        ADD_FUNC(T, "piped",     "std.process.Stdio.piped",    engine_type_unknown());
        ADD_FUNC(T, "null",      "std.process.Stdio.null",     engine_type_unknown());
    }
    ADD_FUNC(NULL, "exit",      "std.process.exit",      engine_type_unknown());
    ADD_FUNC(NULL, "abort",     "std.process.abort",     engine_type_unknown());
    ADD_FUNC(NULL, "id",        "std.process.id",        engine_type_unknown());

    /* ── std::time ─────────────────────────────────────────────── */
    ADD_TYPE("std.time.Duration",   "Duration",   false);
    ADD_TYPE("std.time.Instant",    "Instant",    false);
    ADD_TYPE("std.time.SystemTime", "SystemTime", false);
    ADD_TYPE("std.time.UNIX_EPOCH", "UNIX_EPOCH", false);

    {
        const char* T = "std.time.Duration";
        ADD_FUNC(T, "new",            "std.time.Duration.new",            engine_type_unknown());
        ADD_FUNC(T, "from_secs",      "std.time.Duration.from_secs",      engine_type_unknown());
        ADD_FUNC(T, "from_millis",    "std.time.Duration.from_millis",    engine_type_unknown());
        ADD_FUNC(T, "from_micros",    "std.time.Duration.from_micros",    engine_type_unknown());
        ADD_FUNC(T, "from_nanos",     "std.time.Duration.from_nanos",     engine_type_unknown());
        ADD_FUNC(T, "from_secs_f64",  "std.time.Duration.from_secs_f64",  engine_type_unknown());
        ADD_FUNC(T, "as_secs",        "std.time.Duration.as_secs",        engine_type_unknown());
        ADD_FUNC(T, "as_millis",      "std.time.Duration.as_millis",      engine_type_unknown());
        ADD_FUNC(T, "as_micros",      "std.time.Duration.as_micros",      engine_type_unknown());
        ADD_FUNC(T, "as_nanos",       "std.time.Duration.as_nanos",       engine_type_unknown());
        ADD_FUNC(T, "as_secs_f64",    "std.time.Duration.as_secs_f64",    engine_type_unknown());
        ADD_FUNC(T, "subsec_millis",  "std.time.Duration.subsec_millis",  engine_type_unknown());
        ADD_FUNC(T, "subsec_micros",  "std.time.Duration.subsec_micros",  engine_type_unknown());
        ADD_FUNC(T, "subsec_nanos",   "std.time.Duration.subsec_nanos",   engine_type_unknown());
        ADD_FUNC(T, "is_zero",        "std.time.Duration.is_zero",        t_bool);
        ADD_FUNC(T, "saturating_add", "std.time.Duration.saturating_add", engine_type_unknown());
        ADD_FUNC(T, "saturating_sub", "std.time.Duration.saturating_sub", engine_type_unknown());
        ADD_FUNC(T, "checked_add",    "std.time.Duration.checked_add",    engine_type_unknown());
        ADD_FUNC(T, "checked_sub",    "std.time.Duration.checked_sub",    engine_type_unknown());
    }
    {
        const char* T = "std.time.Instant";
        ADD_FUNC(T, "now",            "std.time.Instant.now",             engine_type_unknown());
        ADD_FUNC(T, "elapsed",        "std.time.Instant.elapsed",         engine_type_unknown());
        ADD_FUNC(T, "duration_since", "std.time.Instant.duration_since",  engine_type_unknown());
        ADD_FUNC(T, "saturating_duration_since","std.time.Instant.saturating_duration_since", engine_type_unknown());
        ADD_FUNC(T, "checked_duration_since","std.time.Instant.checked_duration_since",   engine_type_unknown());
    }
    {
        const char* T = "std.time.SystemTime";
        ADD_FUNC(T, "now",            "std.time.SystemTime.now",          engine_type_unknown());
        ADD_FUNC(T, "duration_since", "std.time.SystemTime.duration_since",engine_type_unknown());
        ADD_FUNC(T, "elapsed",        "std.time.SystemTime.elapsed",      engine_type_unknown());
    }

    /* ── std::thread ───────────────────────────────────────────── */
    ADD_TYPE("std.thread.JoinHandle", "JoinHandle", false);
    ADD_TYPE("std.thread.Thread",     "Thread",     false);
    ADD_TYPE("std.thread.Builder",    "Builder",    false);

    {
        const char* T = "std.thread.JoinHandle";
        ADD_FUNC(T, "join",     "std.thread.JoinHandle.join",     engine_type_unknown());
        ADD_FUNC(T, "thread",   "std.thread.JoinHandle.thread",   engine_type_unknown());
        ADD_FUNC(T, "is_finished","std.thread.JoinHandle.is_finished", t_bool);
    }
    {
        const char* T = "std.thread.Builder";
        ADD_FUNC(T, "new",      "std.thread.Builder.new",      engine_type_unknown());
        ADD_FUNC(T, "name",     "std.thread.Builder.name",     engine_type_unknown());
        ADD_FUNC(T, "stack_size","std.thread.Builder.stack_size", engine_type_unknown());
        ADD_FUNC(T, "spawn",    "std.thread.Builder.spawn",    engine_type_unknown());
    }
    {
        const char* T = "std.thread.Thread";
        ADD_FUNC(T, "name",     "std.thread.Thread.name",     engine_type_unknown());
        ADD_FUNC(T, "id",       "std.thread.Thread.id",       engine_type_unknown());
        ADD_FUNC(T, "unpark",   "std.thread.Thread.unpark",   t_unit);
    }
    /* thread::spawn returns JoinHandle<T> — model loosely as NAMED so
     * `let h = thread::spawn(…); h.join()` resolves through the
     * registered methods on JoinHandle. */
    ADD_FUNC(NULL, "spawn",        "std.thread.spawn",
        engine_type_named(arena, "std.thread.JoinHandle"));
    ADD_FUNC(NULL, "sleep",        "std.thread.sleep",        t_unit);
    ADD_FUNC(NULL, "sleep_ms",     "std.thread.sleep_ms",     t_unit);
    ADD_FUNC(NULL, "yield_now",    "std.thread.yield_now",    t_unit);
    ADD_FUNC(NULL, "current",      "std.thread.current",
        engine_type_named(arena, "std.thread.Thread"));
    ADD_FUNC(NULL, "park",         "std.thread.park",         t_unit);
    ADD_FUNC(NULL, "available_parallelism", "std.thread.available_parallelism", engine_type_unknown());

    /* ── std::sync ─────────────────────────────────────────────── */
    ADD_TYPE("std.sync.Mutex",      "Mutex",      false);
    ADD_TYPE("std.sync.RwLock",     "RwLock",     false);
    ADD_TYPE("std.sync.Once",       "Once",       false);
    ADD_TYPE("std.sync.OnceLock",   "OnceLock",   false);
    ADD_TYPE("std.sync.Barrier",    "Barrier",    false);
    ADD_TYPE("std.sync.Condvar",    "Condvar",    false);
    ADD_TYPE("std.sync.MutexGuard", "MutexGuard", false);
    ADD_TYPE("std.sync.RwLockReadGuard","RwLockReadGuard", false);
    ADD_TYPE("std.sync.RwLockWriteGuard","RwLockWriteGuard",false);
    ADD_TYPE("std.sync.atomic.AtomicBool","AtomicBool", false);
    ADD_TYPE("std.sync.atomic.AtomicI32","AtomicI32", false);
    ADD_TYPE("std.sync.atomic.AtomicI64","AtomicI64", false);
    ADD_TYPE("std.sync.atomic.AtomicU32","AtomicU32", false);
    ADD_TYPE("std.sync.atomic.AtomicU64","AtomicU64", false);
    ADD_TYPE("std.sync.atomic.AtomicUsize","AtomicUsize", false);
    ADD_TYPE("std.sync.atomic.Ordering","Ordering", false);
    ADD_TYPE("std.sync.mpsc.Sender","Sender",   false);
    ADD_TYPE("std.sync.mpsc.Receiver","Receiver",false);
    ADD_TYPE("std.sync.mpsc.SyncSender","SyncSender",false);

    {
        const char* T = "std.sync.Mutex";
        ADD_FUNC(T, "new",      "std.sync.Mutex.new",      engine_type_unknown());
        ADD_FUNC(T, "lock",     "std.sync.Mutex.lock",     engine_type_unknown());
        ADD_FUNC(T, "try_lock", "std.sync.Mutex.try_lock", engine_type_unknown());
        ADD_FUNC(T, "into_inner","std.sync.Mutex.into_inner", engine_type_unknown());
        ADD_FUNC(T, "get_mut",  "std.sync.Mutex.get_mut",  engine_type_unknown());
        ADD_FUNC(T, "is_poisoned","std.sync.Mutex.is_poisoned", t_bool);
    }
    {
        const char* T = "std.sync.RwLock";
        ADD_FUNC(T, "new",      "std.sync.RwLock.new",     engine_type_unknown());
        ADD_FUNC(T, "read",     "std.sync.RwLock.read",    engine_type_unknown());
        ADD_FUNC(T, "write",    "std.sync.RwLock.write",   engine_type_unknown());
        ADD_FUNC(T, "try_read", "std.sync.RwLock.try_read",engine_type_unknown());
        ADD_FUNC(T, "try_write","std.sync.RwLock.try_write",engine_type_unknown());
    }
    {
        const char* T = "std.sync.Once";
        ADD_FUNC(T, "new",      "std.sync.Once.new",       engine_type_unknown());
        ADD_FUNC(T, "call_once","std.sync.Once.call_once", t_unit);
        ADD_FUNC(T, "is_completed","std.sync.Once.is_completed", t_bool);
    }
    {
        const char* T = "std.sync.OnceLock";
        ADD_FUNC(T, "new",      "std.sync.OnceLock.new",   engine_type_unknown());
        ADD_FUNC(T, "get",      "std.sync.OnceLock.get",   engine_type_unknown());
        ADD_FUNC(T, "set",      "std.sync.OnceLock.set",   engine_type_unknown());
        ADD_FUNC(T, "get_or_init","std.sync.OnceLock.get_or_init", engine_type_unknown());
    }
    {
        const char* T = "std.sync.mpsc.Sender";
        ADD_FUNC(T, "send",     "std.sync.mpsc.Sender.send", engine_type_unknown());
        ADD_FUNC(T, "clone",    "std.sync.mpsc.Sender.clone",engine_type_unknown());
    }
    {
        const char* T = "std.sync.mpsc.Receiver";
        ADD_FUNC(T, "recv",     "std.sync.mpsc.Receiver.recv",     engine_type_unknown());
        ADD_FUNC(T, "try_recv", "std.sync.mpsc.Receiver.try_recv", engine_type_unknown());
        ADD_FUNC(T, "recv_timeout","std.sync.mpsc.Receiver.recv_timeout", engine_type_unknown());
        ADD_FUNC(T, "iter",     "std.sync.mpsc.Receiver.iter",     engine_type_unknown());
    }
    /* Atomics — share the same method-name surface across all integer
     * widths, so we register the same set on each type QN. */
    {
        const char* atomic_types[] = {
            "std.sync.atomic.AtomicBool", "std.sync.atomic.AtomicI32",
            "std.sync.atomic.AtomicI64", "std.sync.atomic.AtomicU32",
            "std.sync.atomic.AtomicU64", "std.sync.atomic.AtomicUsize",
            NULL};
        for (const char** T = atomic_types; *T; T++) {
            ADD_FUNC(*T, "new",          engine_arena_sprintf(arena, "%s.new", *T),          engine_type_unknown());
            ADD_FUNC(*T, "load",         engine_arena_sprintf(arena, "%s.load", *T),         engine_type_unknown());
            ADD_FUNC(*T, "store",        engine_arena_sprintf(arena, "%s.store", *T),        t_unit);
            ADD_FUNC(*T, "swap",         engine_arena_sprintf(arena, "%s.swap", *T),         engine_type_unknown());
            ADD_FUNC(*T, "compare_exchange",engine_arena_sprintf(arena, "%s.compare_exchange", *T), engine_type_unknown());
            ADD_FUNC(*T, "fetch_add",    engine_arena_sprintf(arena, "%s.fetch_add", *T),    engine_type_unknown());
            ADD_FUNC(*T, "fetch_sub",    engine_arena_sprintf(arena, "%s.fetch_sub", *T),    engine_type_unknown());
            ADD_FUNC(*T, "fetch_and",    engine_arena_sprintf(arena, "%s.fetch_and", *T),    engine_type_unknown());
            ADD_FUNC(*T, "fetch_or",     engine_arena_sprintf(arena, "%s.fetch_or", *T),     engine_type_unknown());
            ADD_FUNC(*T, "fetch_xor",    engine_arena_sprintf(arena, "%s.fetch_xor", *T),    engine_type_unknown());
            ADD_FUNC(*T, "into_inner",   engine_arena_sprintf(arena, "%s.into_inner", *T),   engine_type_unknown());
        }
    }
    /* mpsc free helpers. */
    ADD_FUNC(NULL, "channel",      "std.sync.mpsc.channel",      engine_type_unknown());
    ADD_FUNC(NULL, "sync_channel", "std.sync.mpsc.sync_channel", engine_type_unknown());

    /* ── std::net ──────────────────────────────────────────────── */
    ADD_TYPE("std.net.TcpStream",       "TcpStream",       false);
    ADD_TYPE("std.net.TcpListener",     "TcpListener",     false);
    ADD_TYPE("std.net.UdpSocket",       "UdpSocket",       false);
    ADD_TYPE("std.net.SocketAddr",      "SocketAddr",      false);
    ADD_TYPE("std.net.SocketAddrV4",    "SocketAddrV4",    false);
    ADD_TYPE("std.net.SocketAddrV6",    "SocketAddrV6",    false);
    ADD_TYPE("std.net.IpAddr",          "IpAddr",          false);
    ADD_TYPE("std.net.Ipv4Addr",        "Ipv4Addr",        false);
    ADD_TYPE("std.net.Ipv6Addr",        "Ipv6Addr",        false);

    {
        const char* T = "std.net.TcpStream";
        ADD_FUNC(T, "connect",   "std.net.TcpStream.connect", engine_type_unknown());
        ADD_FUNC(T, "connect_timeout","std.net.TcpStream.connect_timeout", engine_type_unknown());
        ADD_FUNC(T, "peer_addr", "std.net.TcpStream.peer_addr",engine_type_unknown());
        ADD_FUNC(T, "local_addr","std.net.TcpStream.local_addr",engine_type_unknown());
        ADD_FUNC(T, "shutdown",  "std.net.TcpStream.shutdown",engine_type_unknown());
        ADD_FUNC(T, "try_clone", "std.net.TcpStream.try_clone",engine_type_unknown());
        ADD_FUNC(T, "set_nonblocking","std.net.TcpStream.set_nonblocking", engine_type_unknown());
        ADD_FUNC(T, "set_read_timeout","std.net.TcpStream.set_read_timeout", engine_type_unknown());
        ADD_FUNC(T, "set_write_timeout","std.net.TcpStream.set_write_timeout", engine_type_unknown());
    }
    {
        const char* T = "std.net.TcpListener";
        ADD_FUNC(T, "bind",      "std.net.TcpListener.bind",     engine_type_unknown());
        ADD_FUNC(T, "accept",    "std.net.TcpListener.accept",   engine_type_unknown());
        ADD_FUNC(T, "incoming",  "std.net.TcpListener.incoming", engine_type_unknown());
        ADD_FUNC(T, "local_addr","std.net.TcpListener.local_addr",engine_type_unknown());
        ADD_FUNC(T, "set_nonblocking","std.net.TcpListener.set_nonblocking", engine_type_unknown());
    }
    {
        const char* T = "std.net.UdpSocket";
        ADD_FUNC(T, "bind",      "std.net.UdpSocket.bind",       engine_type_unknown());
        ADD_FUNC(T, "recv_from", "std.net.UdpSocket.recv_from",  engine_type_unknown());
        ADD_FUNC(T, "send_to",   "std.net.UdpSocket.send_to",    engine_type_unknown());
        ADD_FUNC(T, "connect",   "std.net.UdpSocket.connect",    engine_type_unknown());
        ADD_FUNC(T, "recv",      "std.net.UdpSocket.recv",       engine_type_unknown());
        ADD_FUNC(T, "send",      "std.net.UdpSocket.send",       engine_type_unknown());
    }

    /* ── core::str / &str method surface ───────────────────────── */
    /* Most str methods already added above; round out parsing helpers. */
    {
        const char* T = "core.str";
        ADD_FUNC(T, "split_whitespace","core.str.split_whitespace", engine_type_unknown());
        ADD_FUNC(T, "split_terminator","core.str.split_terminator", engine_type_unknown());
        ADD_FUNC(T, "rsplit",          "core.str.rsplit",           engine_type_unknown());
        ADD_FUNC(T, "rsplitn",         "core.str.rsplitn",          engine_type_unknown());
        ADD_FUNC(T, "trim_start",      "core.str.trim_start",       t_str_ref);
        ADD_FUNC(T, "trim_end",        "core.str.trim_end",         t_str_ref);
        ADD_FUNC(T, "trim_start_matches","core.str.trim_start_matches", t_str_ref);
        ADD_FUNC(T, "trim_end_matches","core.str.trim_end_matches", t_str_ref);
        ADD_FUNC(T, "matches",         "core.str.matches",          engine_type_unknown());
        ADD_FUNC(T, "match_indices",   "core.str.match_indices",    engine_type_unknown());
        ADD_FUNC(T, "char_indices",    "core.str.char_indices",     engine_type_unknown());
        ADD_FUNC(T, "encode_utf16",    "core.str.encode_utf16",     engine_type_unknown());
        ADD_FUNC(T, "is_ascii",        "core.str.is_ascii",         t_bool);
        ADD_FUNC(T, "eq_ignore_ascii_case","core.str.eq_ignore_ascii_case", t_bool);
        ADD_FUNC(T, "make_ascii_uppercase","core.str.make_ascii_uppercase", t_unit);
        ADD_FUNC(T, "make_ascii_lowercase","core.str.make_ascii_lowercase", t_unit);
        ADD_FUNC(T, "to_ascii_uppercase","core.str.to_ascii_uppercase", t_self_named_string);
        ADD_FUNC(T, "to_ascii_lowercase","core.str.to_ascii_lowercase", t_self_named_string);
        ADD_FUNC(T, "char_at",         "core.str.char_at",          engine_type_unknown());
        ADD_FUNC(T, "get",             "core.str.get",              engine_type_unknown());
        ADD_FUNC(T, "repeat",          "core.str.repeat",           t_self_named_string);
        ADD_FUNC(T, "rfind",           "core.str.rfind",            engine_type_unknown());
        ADD_FUNC(T, "split_at",        "core.str.split_at",         engine_type_unknown());
        ADD_FUNC(T, "split_once",      "core.str.split_once",       engine_type_unknown());
        ADD_FUNC(T, "rsplit_once",     "core.str.rsplit_once",      engine_type_unknown());
    }

    /* ── Primitive integer / float method surfaces ────────────── */
    {
        /* Each numeric type shares ~50 methods. We register them under
         * each primitive's QN so `42i32.abs()` resolves to `i32.abs`. */
        const char* int_types[] = {
            "i8", "i16", "i32", "i64", "i128", "isize",
            "u8", "u16", "u32", "u64", "u128", "usize", NULL};
        for (const char** T = int_types; *T; T++) {
            ADD_FUNC(*T, "abs",            engine_arena_sprintf(arena, "%s.abs", *T),            engine_type_unknown());
            ADD_FUNC(*T, "signum",         engine_arena_sprintf(arena, "%s.signum", *T),         engine_type_unknown());
            ADD_FUNC(*T, "pow",            engine_arena_sprintf(arena, "%s.pow", *T),            engine_type_unknown());
            ADD_FUNC(*T, "checked_add",    engine_arena_sprintf(arena, "%s.checked_add", *T),    engine_type_unknown());
            ADD_FUNC(*T, "checked_sub",    engine_arena_sprintf(arena, "%s.checked_sub", *T),    engine_type_unknown());
            ADD_FUNC(*T, "checked_mul",    engine_arena_sprintf(arena, "%s.checked_mul", *T),    engine_type_unknown());
            ADD_FUNC(*T, "checked_div",    engine_arena_sprintf(arena, "%s.checked_div", *T),    engine_type_unknown());
            ADD_FUNC(*T, "checked_rem",    engine_arena_sprintf(arena, "%s.checked_rem", *T),    engine_type_unknown());
            ADD_FUNC(*T, "saturating_add", engine_arena_sprintf(arena, "%s.saturating_add", *T), engine_type_unknown());
            ADD_FUNC(*T, "saturating_sub", engine_arena_sprintf(arena, "%s.saturating_sub", *T), engine_type_unknown());
            ADD_FUNC(*T, "saturating_mul", engine_arena_sprintf(arena, "%s.saturating_mul", *T), engine_type_unknown());
            ADD_FUNC(*T, "wrapping_add",   engine_arena_sprintf(arena, "%s.wrapping_add", *T),   engine_type_unknown());
            ADD_FUNC(*T, "wrapping_sub",   engine_arena_sprintf(arena, "%s.wrapping_sub", *T),   engine_type_unknown());
            ADD_FUNC(*T, "wrapping_mul",   engine_arena_sprintf(arena, "%s.wrapping_mul", *T),   engine_type_unknown());
            ADD_FUNC(*T, "overflowing_add",engine_arena_sprintf(arena, "%s.overflowing_add", *T),engine_type_unknown());
            ADD_FUNC(*T, "leading_zeros",  engine_arena_sprintf(arena, "%s.leading_zeros", *T),  engine_type_builtin(arena, "u32"));
            ADD_FUNC(*T, "trailing_zeros", engine_arena_sprintf(arena, "%s.trailing_zeros", *T), engine_type_builtin(arena, "u32"));
            ADD_FUNC(*T, "count_ones",     engine_arena_sprintf(arena, "%s.count_ones", *T),     engine_type_builtin(arena, "u32"));
            ADD_FUNC(*T, "count_zeros",    engine_arena_sprintf(arena, "%s.count_zeros", *T),    engine_type_builtin(arena, "u32"));
            ADD_FUNC(*T, "swap_bytes",     engine_arena_sprintf(arena, "%s.swap_bytes", *T),     engine_type_unknown());
            ADD_FUNC(*T, "rotate_left",    engine_arena_sprintf(arena, "%s.rotate_left", *T),    engine_type_unknown());
            ADD_FUNC(*T, "rotate_right",   engine_arena_sprintf(arena, "%s.rotate_right", *T),   engine_type_unknown());
            ADD_FUNC(*T, "to_string",      engine_arena_sprintf(arena, "%s.to_string", *T),      t_self_named_string);
            ADD_FUNC(*T, "to_be",          engine_arena_sprintf(arena, "%s.to_be", *T),          engine_type_unknown());
            ADD_FUNC(*T, "to_le",          engine_arena_sprintf(arena, "%s.to_le", *T),          engine_type_unknown());
            ADD_FUNC(*T, "to_be_bytes",    engine_arena_sprintf(arena, "%s.to_be_bytes", *T),    engine_type_unknown());
            ADD_FUNC(*T, "to_le_bytes",    engine_arena_sprintf(arena, "%s.to_le_bytes", *T),    engine_type_unknown());
            ADD_FUNC(*T, "from_be_bytes",  engine_arena_sprintf(arena, "%s.from_be_bytes", *T),  engine_type_unknown());
            ADD_FUNC(*T, "from_le_bytes",  engine_arena_sprintf(arena, "%s.from_le_bytes", *T),  engine_type_unknown());
            ADD_FUNC(*T, "min",            engine_arena_sprintf(arena, "%s.min", *T),            engine_type_unknown());
            ADD_FUNC(*T, "max",            engine_arena_sprintf(arena, "%s.max", *T),            engine_type_unknown());
            ADD_FUNC(*T, "clamp",          engine_arena_sprintf(arena, "%s.clamp", *T),          engine_type_unknown());
            ADD_FUNC(*T, "isqrt",          engine_arena_sprintf(arena, "%s.isqrt", *T),          engine_type_unknown());
            ADD_FUNC(*T, "is_power_of_two",engine_arena_sprintf(arena, "%s.is_power_of_two", *T),t_bool);
            ADD_FUNC(*T, "next_power_of_two",engine_arena_sprintf(arena, "%s.next_power_of_two", *T), engine_type_unknown());
            ADD_FUNC(*T, "div_euclid",     engine_arena_sprintf(arena, "%s.div_euclid", *T),     engine_type_unknown());
            ADD_FUNC(*T, "rem_euclid",     engine_arena_sprintf(arena, "%s.rem_euclid", *T),     engine_type_unknown());
        }

        /* Float types share a different surface. */
        const char* float_types[] = {"f32", "f64", NULL};
        for (const char** T = float_types; *T; T++) {
            ADD_FUNC(*T, "abs",      engine_arena_sprintf(arena, "%s.abs", *T),      engine_type_unknown());
            ADD_FUNC(*T, "sqrt",     engine_arena_sprintf(arena, "%s.sqrt", *T),     engine_type_unknown());
            ADD_FUNC(*T, "cbrt",     engine_arena_sprintf(arena, "%s.cbrt", *T),     engine_type_unknown());
            ADD_FUNC(*T, "floor",    engine_arena_sprintf(arena, "%s.floor", *T),    engine_type_unknown());
            ADD_FUNC(*T, "ceil",     engine_arena_sprintf(arena, "%s.ceil", *T),     engine_type_unknown());
            ADD_FUNC(*T, "round",    engine_arena_sprintf(arena, "%s.round", *T),    engine_type_unknown());
            ADD_FUNC(*T, "trunc",    engine_arena_sprintf(arena, "%s.trunc", *T),    engine_type_unknown());
            ADD_FUNC(*T, "fract",    engine_arena_sprintf(arena, "%s.fract", *T),    engine_type_unknown());
            ADD_FUNC(*T, "powi",     engine_arena_sprintf(arena, "%s.powi", *T),     engine_type_unknown());
            ADD_FUNC(*T, "powf",     engine_arena_sprintf(arena, "%s.powf", *T),     engine_type_unknown());
            ADD_FUNC(*T, "exp",      engine_arena_sprintf(arena, "%s.exp", *T),      engine_type_unknown());
            ADD_FUNC(*T, "exp2",     engine_arena_sprintf(arena, "%s.exp2", *T),     engine_type_unknown());
            ADD_FUNC(*T, "ln",       engine_arena_sprintf(arena, "%s.ln", *T),       engine_type_unknown());
            ADD_FUNC(*T, "log",      engine_arena_sprintf(arena, "%s.log", *T),      engine_type_unknown());
            ADD_FUNC(*T, "log2",     engine_arena_sprintf(arena, "%s.log2", *T),     engine_type_unknown());
            ADD_FUNC(*T, "log10",    engine_arena_sprintf(arena, "%s.log10", *T),    engine_type_unknown());
            ADD_FUNC(*T, "sin",      engine_arena_sprintf(arena, "%s.sin", *T),      engine_type_unknown());
            ADD_FUNC(*T, "cos",      engine_arena_sprintf(arena, "%s.cos", *T),      engine_type_unknown());
            ADD_FUNC(*T, "tan",      engine_arena_sprintf(arena, "%s.tan", *T),      engine_type_unknown());
            ADD_FUNC(*T, "asin",     engine_arena_sprintf(arena, "%s.asin", *T),     engine_type_unknown());
            ADD_FUNC(*T, "acos",     engine_arena_sprintf(arena, "%s.acos", *T),     engine_type_unknown());
            ADD_FUNC(*T, "atan",     engine_arena_sprintf(arena, "%s.atan", *T),     engine_type_unknown());
            ADD_FUNC(*T, "atan2",    engine_arena_sprintf(arena, "%s.atan2", *T),    engine_type_unknown());
            ADD_FUNC(*T, "sinh",     engine_arena_sprintf(arena, "%s.sinh", *T),     engine_type_unknown());
            ADD_FUNC(*T, "cosh",     engine_arena_sprintf(arena, "%s.cosh", *T),     engine_type_unknown());
            ADD_FUNC(*T, "tanh",     engine_arena_sprintf(arena, "%s.tanh", *T),     engine_type_unknown());
            ADD_FUNC(*T, "to_radians",engine_arena_sprintf(arena, "%s.to_radians", *T), engine_type_unknown());
            ADD_FUNC(*T, "to_degrees",engine_arena_sprintf(arena, "%s.to_degrees", *T), engine_type_unknown());
            ADD_FUNC(*T, "is_nan",   engine_arena_sprintf(arena, "%s.is_nan", *T),   t_bool);
            ADD_FUNC(*T, "is_infinite",engine_arena_sprintf(arena, "%s.is_infinite", *T), t_bool);
            ADD_FUNC(*T, "is_finite",engine_arena_sprintf(arena, "%s.is_finite", *T), t_bool);
            ADD_FUNC(*T, "is_sign_positive",engine_arena_sprintf(arena, "%s.is_sign_positive", *T), t_bool);
            ADD_FUNC(*T, "is_sign_negative",engine_arena_sprintf(arena, "%s.is_sign_negative", *T), t_bool);
            ADD_FUNC(*T, "min",      engine_arena_sprintf(arena, "%s.min", *T),      engine_type_unknown());
            ADD_FUNC(*T, "max",      engine_arena_sprintf(arena, "%s.max", *T),      engine_type_unknown());
            ADD_FUNC(*T, "clamp",    engine_arena_sprintf(arena, "%s.clamp", *T),    engine_type_unknown());
            ADD_FUNC(*T, "hypot",    engine_arena_sprintf(arena, "%s.hypot", *T),    engine_type_unknown());
            ADD_FUNC(*T, "to_string",engine_arena_sprintf(arena, "%s.to_string", *T),t_self_named_string);
            ADD_FUNC(*T, "to_bits",  engine_arena_sprintf(arena, "%s.to_bits", *T),  engine_type_unknown());
            ADD_FUNC(*T, "from_bits",engine_arena_sprintf(arena, "%s.from_bits", *T),engine_type_unknown());
            ADD_FUNC(*T, "copysign", engine_arena_sprintf(arena, "%s.copysign", *T), engine_type_unknown());
            ADD_FUNC(*T, "mul_add",  engine_arena_sprintf(arena, "%s.mul_add", *T),  engine_type_unknown());
            ADD_FUNC(*T, "recip",    engine_arena_sprintf(arena, "%s.recip", *T),    engine_type_unknown());
            ADD_FUNC(*T, "signum",   engine_arena_sprintf(arena, "%s.signum", *T),   engine_type_unknown());
        }

        /* char methods. */
        ADD_FUNC("char", "is_alphabetic",  "char.is_alphabetic",  t_bool);
        ADD_FUNC("char", "is_alphanumeric","char.is_alphanumeric",t_bool);
        ADD_FUNC("char", "is_numeric",     "char.is_numeric",     t_bool);
        ADD_FUNC("char", "is_ascii",       "char.is_ascii",       t_bool);
        ADD_FUNC("char", "is_ascii_alphabetic","char.is_ascii_alphabetic", t_bool);
        ADD_FUNC("char", "is_ascii_alphanumeric","char.is_ascii_alphanumeric", t_bool);
        ADD_FUNC("char", "is_digit",       "char.is_digit",       t_bool);
        ADD_FUNC("char", "is_uppercase",   "char.is_uppercase",   t_bool);
        ADD_FUNC("char", "is_lowercase",   "char.is_lowercase",   t_bool);
        ADD_FUNC("char", "is_whitespace",  "char.is_whitespace",  t_bool);
        ADD_FUNC("char", "is_control",     "char.is_control",     t_bool);
        ADD_FUNC("char", "to_lowercase",   "char.to_lowercase",   engine_type_unknown());
        ADD_FUNC("char", "to_uppercase",   "char.to_uppercase",   engine_type_unknown());
        ADD_FUNC("char", "to_ascii_lowercase","char.to_ascii_lowercase", engine_type_builtin(arena, "char"));
        ADD_FUNC("char", "to_ascii_uppercase","char.to_ascii_uppercase", engine_type_builtin(arena, "char"));
        ADD_FUNC("char", "to_digit",       "char.to_digit",       engine_type_unknown());
        ADD_FUNC("char", "len_utf8",       "char.len_utf8",       t_usize);
        ADD_FUNC("char", "len_utf16",      "char.len_utf16",      t_usize);
        ADD_FUNC("char", "to_string",      "char.to_string",      t_self_named_string);
    }

    /* ── core::slice / [T] methods ─────────────────────────────── */
    ADD_TYPE("core.slice", "slice", false);
    {
        const char* T = "core.slice";
        ADD_FUNC(T, "len",            "core.slice.len",            t_usize);
        ADD_FUNC(T, "is_empty",       "core.slice.is_empty",       t_bool);
        ADD_FUNC(T, "first",          "core.slice.first",          engine_type_unknown());
        ADD_FUNC(T, "last",           "core.slice.last",           engine_type_unknown());
        ADD_FUNC(T, "get",            "core.slice.get",            engine_type_unknown());
        ADD_FUNC(T, "iter",           "core.slice.iter",           engine_type_unknown());
        ADD_FUNC(T, "iter_mut",       "core.slice.iter_mut",       engine_type_unknown());
        ADD_FUNC(T, "windows",        "core.slice.windows",        engine_type_unknown());
        ADD_FUNC(T, "chunks",         "core.slice.chunks",         engine_type_unknown());
        ADD_FUNC(T, "chunks_exact",   "core.slice.chunks_exact",   engine_type_unknown());
        ADD_FUNC(T, "split",          "core.slice.split",          engine_type_unknown());
        ADD_FUNC(T, "split_at",       "core.slice.split_at",       engine_type_unknown());
        ADD_FUNC(T, "split_first",    "core.slice.split_first",    engine_type_unknown());
        ADD_FUNC(T, "split_last",     "core.slice.split_last",     engine_type_unknown());
        ADD_FUNC(T, "binary_search",  "core.slice.binary_search",  engine_type_unknown());
        ADD_FUNC(T, "sort",           "core.slice.sort",           t_unit);
        ADD_FUNC(T, "sort_by",        "core.slice.sort_by",        t_unit);
        ADD_FUNC(T, "sort_by_key",    "core.slice.sort_by_key",    t_unit);
        ADD_FUNC(T, "sort_unstable",  "core.slice.sort_unstable",  t_unit);
        ADD_FUNC(T, "reverse",        "core.slice.reverse",        t_unit);
        ADD_FUNC(T, "fill",           "core.slice.fill",           t_unit);
        ADD_FUNC(T, "swap",           "core.slice.swap",           t_unit);
        ADD_FUNC(T, "contains",       "core.slice.contains",       t_bool);
        ADD_FUNC(T, "starts_with",    "core.slice.starts_with",    t_bool);
        ADD_FUNC(T, "ends_with",      "core.slice.ends_with",      t_bool);
        ADD_FUNC(T, "join",           "core.slice.join",           engine_type_unknown());
        ADD_FUNC(T, "concat",         "core.slice.concat",         engine_type_unknown());
        ADD_FUNC(T, "to_vec",         "core.slice.to_vec",         engine_type_unknown());
        ADD_FUNC(T, "as_ptr",         "core.slice.as_ptr",         engine_type_unknown());
        ADD_FUNC(T, "as_mut_ptr",     "core.slice.as_mut_ptr",     engine_type_unknown());
        ADD_FUNC(T, "copy_from_slice","core.slice.copy_from_slice",t_unit);
        ADD_FUNC(T, "clone_from_slice","core.slice.clone_from_slice", t_unit);
        ADD_FUNC(T, "rotate_left",    "core.slice.rotate_left",    t_unit);
        ADD_FUNC(T, "rotate_right",   "core.slice.rotate_right",   t_unit);
    }

    /* ── core::cmp helpers ─────────────────────────────────────── */
    ADD_FUNC(NULL, "min",         "core.cmp.min",         engine_type_unknown());
    ADD_FUNC(NULL, "max",         "core.cmp.max",         engine_type_unknown());
    ADD_FUNC(NULL, "min_by",      "core.cmp.min_by",      engine_type_unknown());
    ADD_FUNC(NULL, "max_by",      "core.cmp.max_by",      engine_type_unknown());
    ADD_FUNC(NULL, "min_by_key",  "core.cmp.min_by_key",  engine_type_unknown());
    ADD_FUNC(NULL, "max_by_key",  "core.cmp.max_by_key",  engine_type_unknown());

    /* ── core::error::Error trait ──────────────────────────────── */
    ADD_TYPE("core.error.Error", "Error", true);
    {
        const char* T = "core.error.Error";
        ADD_FUNC(T, "source",      "core.error.Error.source",     engine_type_unknown());
        ADD_FUNC(T, "description", "core.error.Error.description",t_str_ref);
        ADD_FUNC(T, "cause",       "core.error.Error.cause",      engine_type_unknown());
    }

    /* ── std::error re-export ──────────────────────────────────── */
    {
        EngineRegisteredType rt;
        memset(&rt, 0, sizeof(rt));
        rt.qualified_name = "std.error.Error";
        rt.short_name = "Error";
        rt.alias_of = "core.error.Error";
        rt.is_interface = true;
        engine_registry_add_type(reg, rt);
    }

    /* ── Range / RangeInclusive / RangeFull ────────────────────── */
    ADD_TYPE("core.ops.Range",          "Range",         false);
    ADD_TYPE("core.ops.RangeInclusive", "RangeInclusive",false);
    ADD_TYPE("core.ops.RangeFrom",      "RangeFrom",     false);
    ADD_TYPE("core.ops.RangeTo",        "RangeTo",       false);
    ADD_TYPE("core.ops.RangeToInclusive","RangeToInclusive", false);
    ADD_TYPE("core.ops.RangeFull",      "RangeFull",     false);
    {
        const char* T = "core.ops.Range";
        ADD_FUNC(T, "contains", "core.ops.Range.contains", t_bool);
        ADD_FUNC(T, "is_empty", "core.ops.Range.is_empty", t_bool);
        ADD_FUNC(T, "start",    "core.ops.Range.start",    engine_type_unknown());
        ADD_FUNC(T, "end",      "core.ops.Range.end",      engine_type_unknown());
        ADD_FUNC(T, "len",      "core.ops.Range.len",      t_usize);
    }

    /* ── core::iter additions (sum/product/zip etc. already added) ─ */
    {
        const char* T = "core.iter.Iterator";
        ADD_FUNC(T, "product",   "core.iter.Iterator.product",   engine_type_unknown());
        ADD_FUNC(T, "last",      "core.iter.Iterator.last",      engine_type_unknown());
        ADD_FUNC(T, "nth",       "core.iter.Iterator.nth",       engine_type_unknown());
        ADD_FUNC(T, "size_hint", "core.iter.Iterator.size_hint", engine_type_unknown());
        ADD_FUNC(T, "by_ref",    "core.iter.Iterator.by_ref",    engine_type_unknown());
        ADD_FUNC(T, "max_by",    "core.iter.Iterator.max_by",    engine_type_unknown());
        ADD_FUNC(T, "min_by",    "core.iter.Iterator.min_by",    engine_type_unknown());
        ADD_FUNC(T, "max_by_key","core.iter.Iterator.max_by_key",engine_type_unknown());
        ADD_FUNC(T, "min_by_key","core.iter.Iterator.min_by_key",engine_type_unknown());
        ADD_FUNC(T, "scan",      "core.iter.Iterator.scan",      engine_type_unknown());
        ADD_FUNC(T, "inspect",   "core.iter.Iterator.inspect",   engine_type_unknown());
        ADD_FUNC(T, "fuse",      "core.iter.Iterator.fuse",      engine_type_unknown());
        ADD_FUNC(T, "cycle",     "core.iter.Iterator.cycle",     engine_type_unknown());
        ADD_FUNC(T, "take_while","core.iter.Iterator.take_while",engine_type_unknown());
        ADD_FUNC(T, "skip_while","core.iter.Iterator.skip_while",engine_type_unknown());
        ADD_FUNC(T, "try_fold",  "core.iter.Iterator.try_fold",  engine_type_unknown());
        ADD_FUNC(T, "try_for_each","core.iter.Iterator.try_for_each", engine_type_unknown());
        ADD_FUNC(T, "reduce",    "core.iter.Iterator.reduce",    engine_type_unknown());
        ADD_FUNC(T, "unzip",     "core.iter.Iterator.unzip",     engine_type_unknown());
        ADD_FUNC(T, "partition", "core.iter.Iterator.partition", engine_type_unknown());
        ADD_FUNC(T, "into_iter", "core.iter.Iterator.into_iter", engine_type_unknown());
    }
    {
        const char* T = "core.iter.IntoIterator";
        ADD_FUNC(T, "into_iter", "core.iter.IntoIterator.into_iter", engine_type_unknown());
    }
    /* Free helpers in core::iter. */
    ADD_FUNC(NULL, "once",          "core.iter.once",          engine_type_unknown());
    ADD_FUNC(NULL, "empty",         "core.iter.empty",         engine_type_unknown());
    ADD_FUNC(NULL, "repeat",        "core.iter.repeat",        engine_type_unknown());
    ADD_FUNC(NULL, "from_fn",       "core.iter.from_fn",       engine_type_unknown());
    ADD_FUNC(NULL, "successors",    "core.iter.successors",    engine_type_unknown());
    ADD_FUNC(NULL, "zip",           "core.iter.zip",           engine_type_unknown());

    /* ── Pin and Future helpers ───────────────────────────────── */
    ADD_TYPE("core.pin.Pin", "Pin", false);
    {
        const char* T = "core.pin.Pin";
        ADD_FUNC(T, "new",          "core.pin.Pin.new",          engine_type_unknown());
        ADD_FUNC(T, "as_ref",       "core.pin.Pin.as_ref",       engine_type_unknown());
        ADD_FUNC(T, "as_mut",       "core.pin.Pin.as_mut",       engine_type_unknown());
        ADD_FUNC(T, "into_inner",   "core.pin.Pin.into_inner",   engine_type_unknown());
    }
    {
        const char* T = "core.future.Future";
        ADD_FUNC(T, "poll",     "core.future.Future.poll",     engine_type_unknown());
    }

    /* ── std::collections additions ────────────────────────────── */
    ADD_TYPE("alloc.collections.LinkedList", "LinkedList", false);
    ADD_TYPE("alloc.collections.BinaryHeap", "BinaryHeap", false);
    {
        const char* T = "alloc.collections.LinkedList";
        ADD_FUNC(T, "new",       "alloc.collections.LinkedList.new",       engine_type_unknown());
        ADD_FUNC(T, "push_back", "alloc.collections.LinkedList.push_back", t_unit);
        ADD_FUNC(T, "push_front","alloc.collections.LinkedList.push_front",t_unit);
        ADD_FUNC(T, "pop_back",  "alloc.collections.LinkedList.pop_back",  engine_type_unknown());
        ADD_FUNC(T, "pop_front", "alloc.collections.LinkedList.pop_front", engine_type_unknown());
        ADD_FUNC(T, "len",       "alloc.collections.LinkedList.len",       t_usize);
        ADD_FUNC(T, "is_empty",  "alloc.collections.LinkedList.is_empty",  t_bool);
        ADD_FUNC(T, "iter",      "alloc.collections.LinkedList.iter",      engine_type_unknown());
    }
    {
        const char* T = "alloc.collections.BinaryHeap";
        ADD_FUNC(T, "new",       "alloc.collections.BinaryHeap.new",       engine_type_unknown());
        ADD_FUNC(T, "push",      "alloc.collections.BinaryHeap.push",      t_unit);
        ADD_FUNC(T, "pop",       "alloc.collections.BinaryHeap.pop",       engine_type_unknown());
        ADD_FUNC(T, "peek",      "alloc.collections.BinaryHeap.peek",      engine_type_unknown());
        ADD_FUNC(T, "len",       "alloc.collections.BinaryHeap.len",       t_usize);
        ADD_FUNC(T, "into_sorted_vec","alloc.collections.BinaryHeap.into_sorted_vec", engine_type_unknown());
    }
    {
        const char* T = "alloc.collections.HashSet";
        ADD_FUNC(T, "new",        "alloc.collections.HashSet.new",        engine_type_unknown());
        ADD_FUNC(T, "insert",     "alloc.collections.HashSet.insert",     t_bool);
        ADD_FUNC(T, "remove",     "alloc.collections.HashSet.remove",     t_bool);
        ADD_FUNC(T, "contains",   "alloc.collections.HashSet.contains",   t_bool);
        ADD_FUNC(T, "len",        "alloc.collections.HashSet.len",        t_usize);
        ADD_FUNC(T, "is_empty",   "alloc.collections.HashSet.is_empty",   t_bool);
        ADD_FUNC(T, "clear",      "alloc.collections.HashSet.clear",      t_unit);
        ADD_FUNC(T, "iter",       "alloc.collections.HashSet.iter",       engine_type_unknown());
        ADD_FUNC(T, "intersection","alloc.collections.HashSet.intersection",engine_type_unknown());
        ADD_FUNC(T, "union",      "alloc.collections.HashSet.union",      engine_type_unknown());
        ADD_FUNC(T, "difference", "alloc.collections.HashSet.difference", engine_type_unknown());
    }
    {
        const char* T = "alloc.collections.VecDeque";
        ADD_FUNC(T, "new",       "alloc.collections.VecDeque.new",       engine_type_unknown());
        ADD_FUNC(T, "push_back", "alloc.collections.VecDeque.push_back", t_unit);
        ADD_FUNC(T, "push_front","alloc.collections.VecDeque.push_front",t_unit);
        ADD_FUNC(T, "pop_back",  "alloc.collections.VecDeque.pop_back",  engine_type_unknown());
        ADD_FUNC(T, "pop_front", "alloc.collections.VecDeque.pop_front", engine_type_unknown());
        ADD_FUNC(T, "len",       "alloc.collections.VecDeque.len",       t_usize);
        ADD_FUNC(T, "is_empty",  "alloc.collections.VecDeque.is_empty",  t_bool);
        ADD_FUNC(T, "front",     "alloc.collections.VecDeque.front",     engine_type_unknown());
        ADD_FUNC(T, "back",      "alloc.collections.VecDeque.back",      engine_type_unknown());
        ADD_FUNC(T, "iter",      "alloc.collections.VecDeque.iter",      engine_type_unknown());
    }

    /* ════════════════════════════════════════════════════════════════
     * EXTRA stdlib breadth — push from ~700 to ~2500+ methods so the
     * gap-class tests that exercise less-common surfaces find hits.
     *
     * Sections below register: ffi (CStr/CString/OsStr/OsString),
     * std::ptr, std::mem extras, additional Range-family methods,
     * std::str functions (parse, from_utf8), additional collection
     * methods (drain/range/extend), HashSet operations, BinaryHeap,
     * additional Box/Rc/Arc/Pin methods, additional Mutex/RwLock
     * guards, additional Atomic types and variants, additional thread
     * Builder, std::process extras, std::time extras, more std::sync
     * (Once/Barrier/Condvar), additional std::path methods, raw ptr
     * arithmetic, Cell methods, plus per-numeric-type extras.
     * ════════════════════════════════════════════════════════════════ */

    /* ── std::ffi ─────────────────────────────────────────────── */
    ADD_TYPE("std.ffi.CStr",      "CStr",      false);
    ADD_TYPE("std.ffi.CString",   "CString",   false);
    ADD_TYPE("std.ffi.OsStr",     "OsStr",     false);
    ADD_TYPE("std.ffi.OsString",  "OsString",  false);
    ADD_TYPE("std.ffi.NulError",  "NulError",  false);
    ADD_TYPE("std.ffi.IntoStringError","IntoStringError", false);
    ADD_TYPE("std.ffi.FromBytesWithNulError","FromBytesWithNulError", false);
    {
        const char* T = "std.ffi.CString";
        ADD_FUNC(T, "new",          "std.ffi.CString.new",          engine_type_unknown());
        ADD_FUNC(T, "as_c_str",     "std.ffi.CString.as_c_str",     engine_type_unknown());
        ADD_FUNC(T, "as_bytes",     "std.ffi.CString.as_bytes",     engine_type_unknown());
        ADD_FUNC(T, "as_bytes_with_nul","std.ffi.CString.as_bytes_with_nul", engine_type_unknown());
        ADD_FUNC(T, "into_bytes",   "std.ffi.CString.into_bytes",   engine_type_unknown());
        ADD_FUNC(T, "into_bytes_with_nul","std.ffi.CString.into_bytes_with_nul", engine_type_unknown());
        ADD_FUNC(T, "into_string",  "std.ffi.CString.into_string",  engine_type_unknown());
        ADD_FUNC(T, "into_raw",     "std.ffi.CString.into_raw",     engine_type_unknown());
        ADD_FUNC(T, "from_raw",     "std.ffi.CString.from_raw",     engine_type_unknown());
        ADD_FUNC(T, "from_vec_unchecked","std.ffi.CString.from_vec_unchecked", engine_type_unknown());
    }
    {
        const char* T = "std.ffi.CStr";
        ADD_FUNC(T, "from_ptr",     "std.ffi.CStr.from_ptr",        engine_type_unknown());
        ADD_FUNC(T, "from_bytes_with_nul","std.ffi.CStr.from_bytes_with_nul", engine_type_unknown());
        ADD_FUNC(T, "to_str",       "std.ffi.CStr.to_str",          engine_type_unknown());
        ADD_FUNC(T, "to_string_lossy","std.ffi.CStr.to_string_lossy", engine_type_unknown());
        ADD_FUNC(T, "to_bytes",     "std.ffi.CStr.to_bytes",        engine_type_unknown());
        ADD_FUNC(T, "to_bytes_with_nul","std.ffi.CStr.to_bytes_with_nul", engine_type_unknown());
        ADD_FUNC(T, "as_ptr",       "std.ffi.CStr.as_ptr",          engine_type_unknown());
    }
    {
        const char* T = "std.ffi.OsString";
        ADD_FUNC(T, "new",          "std.ffi.OsString.new",         engine_type_unknown());
        ADD_FUNC(T, "from",         "std.ffi.OsString.from",        engine_type_unknown());
        ADD_FUNC(T, "with_capacity","std.ffi.OsString.with_capacity",engine_type_unknown());
        ADD_FUNC(T, "as_os_str",    "std.ffi.OsString.as_os_str",   engine_type_unknown());
        ADD_FUNC(T, "into_string",  "std.ffi.OsString.into_string", engine_type_unknown());
        ADD_FUNC(T, "push",         "std.ffi.OsString.push",        t_unit);
        ADD_FUNC(T, "len",          "std.ffi.OsString.len",         t_usize);
        ADD_FUNC(T, "clear",        "std.ffi.OsString.clear",       t_unit);
        ADD_FUNC(T, "capacity",     "std.ffi.OsString.capacity",    t_usize);
    }
    {
        const char* T = "std.ffi.OsStr";
        ADD_FUNC(T, "new",          "std.ffi.OsStr.new",            engine_type_unknown());
        ADD_FUNC(T, "to_str",       "std.ffi.OsStr.to_str",         engine_type_unknown());
        ADD_FUNC(T, "to_string_lossy","std.ffi.OsStr.to_string_lossy", engine_type_unknown());
        ADD_FUNC(T, "to_os_string", "std.ffi.OsStr.to_os_string",   engine_type_unknown());
        ADD_FUNC(T, "is_empty",     "std.ffi.OsStr.is_empty",       t_bool);
        ADD_FUNC(T, "len",          "std.ffi.OsStr.len",            t_usize);
    }

    /* ── std::ptr / core::ptr ─────────────────────────────────── */
    ADD_TYPE("core.ptr.NonNull",  "NonNull",  false);
    ADD_FUNC(NULL, "null",         "core.ptr.null",         engine_type_unknown());
    ADD_FUNC(NULL, "null_mut",     "core.ptr.null_mut",     engine_type_unknown());
    ADD_FUNC(NULL, "addr_of",      "core.ptr.addr_of",      engine_type_unknown());
    ADD_FUNC(NULL, "addr_of_mut",  "core.ptr.addr_of_mut",  engine_type_unknown());
    ADD_FUNC(NULL, "read",         "core.ptr.read",         engine_type_unknown());
    ADD_FUNC(NULL, "write",        "core.ptr.write",        t_unit);
    ADD_FUNC(NULL, "copy",         "core.ptr.copy",         t_unit);
    ADD_FUNC(NULL, "copy_nonoverlapping","core.ptr.copy_nonoverlapping", t_unit);
    ADD_FUNC(NULL, "swap",         "core.ptr.swap",         t_unit);
    ADD_FUNC(NULL, "drop_in_place","core.ptr.drop_in_place",t_unit);
    /* std::ptr re-export aliases for free functions don't fit easily —
     * the resolver finds them via use map already. */
    {
        const char* T = "core.ptr.NonNull";
        ADD_FUNC(T, "new",          "core.ptr.NonNull.new",         engine_type_unknown());
        ADD_FUNC(T, "new_unchecked","core.ptr.NonNull.new_unchecked", engine_type_unknown());
        ADD_FUNC(T, "as_ptr",       "core.ptr.NonNull.as_ptr",      engine_type_unknown());
        ADD_FUNC(T, "as_ref",       "core.ptr.NonNull.as_ref",      engine_type_unknown());
        ADD_FUNC(T, "as_mut",       "core.ptr.NonNull.as_mut",      engine_type_unknown());
        ADD_FUNC(T, "cast",         "core.ptr.NonNull.cast",        engine_type_unknown());
    }

    /* ── std::mem extras ──────────────────────────────────────── */
    ADD_FUNC(NULL, "align_of",     "std.mem.align_of",     t_usize);
    ADD_FUNC(NULL, "align_of_val", "std.mem.align_of_val", t_usize);
    ADD_FUNC(NULL, "size_of_val",  "std.mem.size_of_val",  t_usize);
    ADD_FUNC(NULL, "transmute",    "std.mem.transmute",    engine_type_unknown());
    ADD_FUNC(NULL, "transmute_copy","std.mem.transmute_copy", engine_type_unknown());
    ADD_FUNC(NULL, "uninitialized","std.mem.uninitialized",engine_type_unknown());
    ADD_FUNC(NULL, "zeroed",       "std.mem.zeroed",       engine_type_unknown());
    ADD_FUNC(NULL, "forget",       "std.mem.forget",       t_unit);
    ADD_FUNC(NULL, "discriminant", "std.mem.discriminant", engine_type_unknown());
    ADD_FUNC(NULL, "needs_drop",   "std.mem.needs_drop",   t_bool);

    /* ── core::slice extras (already partial) ────────────────── */
    {
        const char* T = "core.slice";
        ADD_FUNC(T, "split_at_mut", "core.slice.split_at_mut", engine_type_unknown());
        ADD_FUNC(T, "split_first_mut","core.slice.split_first_mut", engine_type_unknown());
        ADD_FUNC(T, "split_last_mut","core.slice.split_last_mut", engine_type_unknown());
        ADD_FUNC(T, "split_at_unchecked","core.slice.split_at_unchecked", engine_type_unknown());
        ADD_FUNC(T, "windows_mut",  "core.slice.windows_mut",  engine_type_unknown());
        ADD_FUNC(T, "chunks_mut",   "core.slice.chunks_mut",   engine_type_unknown());
        ADD_FUNC(T, "chunks_exact_mut","core.slice.chunks_exact_mut", engine_type_unknown());
        ADD_FUNC(T, "rchunks",      "core.slice.rchunks",      engine_type_unknown());
        ADD_FUNC(T, "rchunks_mut",  "core.slice.rchunks_mut",  engine_type_unknown());
        ADD_FUNC(T, "binary_search_by","core.slice.binary_search_by", engine_type_unknown());
        ADD_FUNC(T, "binary_search_by_key","core.slice.binary_search_by_key", engine_type_unknown());
        ADD_FUNC(T, "select_nth_unstable","core.slice.select_nth_unstable", engine_type_unknown());
        ADD_FUNC(T, "partition_point","core.slice.partition_point", t_usize);
        ADD_FUNC(T, "get_mut",      "core.slice.get_mut",      engine_type_unknown());
        ADD_FUNC(T, "first_mut",    "core.slice.first_mut",    engine_type_unknown());
        ADD_FUNC(T, "last_mut",     "core.slice.last_mut",     engine_type_unknown());
        ADD_FUNC(T, "iter_chunks",  "core.slice.iter_chunks",  engine_type_unknown());
        ADD_FUNC(T, "concat_str",   "core.slice.concat_str",   engine_type_unknown());
        ADD_FUNC(T, "is_sorted",    "core.slice.is_sorted",    t_bool);
        ADD_FUNC(T, "is_sorted_by", "core.slice.is_sorted_by", t_bool);
        ADD_FUNC(T, "split_off",    "core.slice.split_off",    engine_type_unknown());
        ADD_FUNC(T, "as_chunks",    "core.slice.as_chunks",    engine_type_unknown());
    }

    /* ── core::str extras ─────────────────────────────────────── */
    {
        const char* T = "core.str";
        ADD_FUNC(T, "as_ptr",       "core.str.as_ptr",       engine_type_unknown());
        ADD_FUNC(T, "as_str",       "core.str.as_str",       t_str_ref);
        ADD_FUNC(T, "from_utf8",    "core.str.from_utf8",    engine_type_unknown());
        ADD_FUNC(T, "from_utf8_unchecked","core.str.from_utf8_unchecked", engine_type_unknown());
        ADD_FUNC(T, "encode_utf16_lossy","core.str.encode_utf16_lossy", engine_type_unknown());
        ADD_FUNC(T, "into_string",  "core.str.into_string",  t_string);
    }

    /* ── alloc::string extras ─────────────────────────────────── */
    {
        const char* T = "alloc.string.String";
        ADD_FUNC(T, "from_utf8",    "alloc.string.String.from_utf8",     engine_type_unknown());
        ADD_FUNC(T, "from_utf8_lossy","alloc.string.String.from_utf8_lossy", engine_type_unknown());
        ADD_FUNC(T, "from_utf16",   "alloc.string.String.from_utf16",    engine_type_unknown());
        ADD_FUNC(T, "from_utf16_lossy","alloc.string.String.from_utf16_lossy", engine_type_unknown());
        ADD_FUNC(T, "into_boxed_str","alloc.string.String.into_boxed_str", engine_type_unknown());
        ADD_FUNC(T, "leak",         "alloc.string.String.leak",          engine_type_unknown());
        ADD_FUNC(T, "shrink_to_fit","alloc.string.String.shrink_to_fit", t_unit);
        ADD_FUNC(T, "shrink_to",    "alloc.string.String.shrink_to",     t_unit);
        ADD_FUNC(T, "reserve",      "alloc.string.String.reserve",       t_unit);
        ADD_FUNC(T, "reserve_exact","alloc.string.String.reserve_exact", t_unit);
        ADD_FUNC(T, "drain",        "alloc.string.String.drain",         engine_type_unknown());
        ADD_FUNC(T, "insert",       "alloc.string.String.insert",        t_unit);
        ADD_FUNC(T, "insert_str",   "alloc.string.String.insert_str",    t_unit);
        ADD_FUNC(T, "remove",       "alloc.string.String.remove",        engine_type_unknown());
        ADD_FUNC(T, "retain",       "alloc.string.String.retain",        t_unit);
        ADD_FUNC(T, "truncate",     "alloc.string.String.truncate",      t_unit);
        ADD_FUNC(T, "split_off",    "alloc.string.String.split_off",     t_string);
        ADD_FUNC(T, "as_mut_str",   "alloc.string.String.as_mut_str",    engine_type_unknown());
    }

    /* ── alloc::vec extras ────────────────────────────────────── */
    {
        const char* T = "alloc.vec.Vec";
        ADD_FUNC(T, "shrink_to_fit","alloc.vec.Vec.shrink_to_fit",   t_unit);
        ADD_FUNC(T, "shrink_to",    "alloc.vec.Vec.shrink_to",       t_unit);
        ADD_FUNC(T, "truncate",     "alloc.vec.Vec.truncate",        t_unit);
        ADD_FUNC(T, "resize",       "alloc.vec.Vec.resize",          t_unit);
        ADD_FUNC(T, "resize_with",  "alloc.vec.Vec.resize_with",     t_unit);
        ADD_FUNC(T, "retain",       "alloc.vec.Vec.retain",          t_unit);
        ADD_FUNC(T, "retain_mut",   "alloc.vec.Vec.retain_mut",      t_unit);
        ADD_FUNC(T, "dedup",        "alloc.vec.Vec.dedup",           t_unit);
        ADD_FUNC(T, "dedup_by",     "alloc.vec.Vec.dedup_by",        t_unit);
        ADD_FUNC(T, "dedup_by_key", "alloc.vec.Vec.dedup_by_key",    t_unit);
        ADD_FUNC(T, "split_off",    "alloc.vec.Vec.split_off",       engine_type_unknown());
        ADD_FUNC(T, "append",       "alloc.vec.Vec.append",          t_unit);
        ADD_FUNC(T, "leak",         "alloc.vec.Vec.leak",            engine_type_unknown());
        ADD_FUNC(T, "spare_capacity_mut","alloc.vec.Vec.spare_capacity_mut", engine_type_unknown());
        ADD_FUNC(T, "into_boxed_slice","alloc.vec.Vec.into_boxed_slice", engine_type_unknown());
        ADD_FUNC(T, "set_len",      "alloc.vec.Vec.set_len",         t_unit);
        ADD_FUNC(T, "split_at_mut", "alloc.vec.Vec.split_at_mut",    engine_type_unknown());
        ADD_FUNC(T, "swap",         "alloc.vec.Vec.swap",            t_unit);
        ADD_FUNC(T, "rotate_left",  "alloc.vec.Vec.rotate_left",     t_unit);
        ADD_FUNC(T, "rotate_right", "alloc.vec.Vec.rotate_right",    t_unit);
        ADD_FUNC(T, "fill",         "alloc.vec.Vec.fill",            t_unit);
        ADD_FUNC(T, "fill_with",    "alloc.vec.Vec.fill_with",       t_unit);
    }

    /* ── alloc::collections::HashMap extras ───────────────────── */
    {
        const char* T = "alloc.collections.HashMap";
        ADD_FUNC(T, "drain",        "alloc.collections.HashMap.drain",        engine_type_unknown());
        ADD_FUNC(T, "retain",       "alloc.collections.HashMap.retain",       t_unit);
        ADD_FUNC(T, "extend",       "alloc.collections.HashMap.extend",       t_unit);
        ADD_FUNC(T, "values_mut",   "alloc.collections.HashMap.values_mut",   engine_type_unknown());
        ADD_FUNC(T, "iter_mut",     "alloc.collections.HashMap.iter_mut",     engine_type_unknown());
        ADD_FUNC(T, "into_iter",    "alloc.collections.HashMap.into_iter",    engine_type_unknown());
        ADD_FUNC(T, "into_keys",    "alloc.collections.HashMap.into_keys",    engine_type_unknown());
        ADD_FUNC(T, "into_values",  "alloc.collections.HashMap.into_values",  engine_type_unknown());
        ADD_FUNC(T, "shrink_to_fit","alloc.collections.HashMap.shrink_to_fit",t_unit);
        ADD_FUNC(T, "reserve",      "alloc.collections.HashMap.reserve",      t_unit);
        ADD_FUNC(T, "capacity",     "alloc.collections.HashMap.capacity",     t_usize);
        ADD_FUNC(T, "hasher",       "alloc.collections.HashMap.hasher",       engine_type_unknown());
        ADD_FUNC(T, "raw_entry",    "alloc.collections.HashMap.raw_entry",    engine_type_unknown());
    }

    /* ── std::sync extras ─────────────────────────────────────── */
    ADD_TYPE("std.sync.PoisonError", "PoisonError", false);
    ADD_TYPE("std.sync.WaitTimeoutResult","WaitTimeoutResult", false);
    {
        const char* T = "std.sync.Condvar";
        ADD_FUNC(T, "new",         "std.sync.Condvar.new",         engine_type_unknown());
        ADD_FUNC(T, "wait",        "std.sync.Condvar.wait",        engine_type_unknown());
        ADD_FUNC(T, "wait_timeout","std.sync.Condvar.wait_timeout",engine_type_unknown());
        ADD_FUNC(T, "wait_while",  "std.sync.Condvar.wait_while",  engine_type_unknown());
        ADD_FUNC(T, "notify_one",  "std.sync.Condvar.notify_one",  t_unit);
        ADD_FUNC(T, "notify_all",  "std.sync.Condvar.notify_all",  t_unit);
    }
    {
        const char* T = "std.sync.Barrier";
        ADD_FUNC(T, "new",         "std.sync.Barrier.new",         engine_type_unknown());
        ADD_FUNC(T, "wait",        "std.sync.Barrier.wait",        engine_type_unknown());
    }
    {
        const char* T = "std.sync.MutexGuard";
        ADD_FUNC(T, "deref",       "std.sync.MutexGuard.deref",       engine_type_unknown());
        ADD_FUNC(T, "deref_mut",   "std.sync.MutexGuard.deref_mut",   engine_type_unknown());
    }
    {
        const char* T = "std.sync.RwLockReadGuard";
        ADD_FUNC(T, "deref",       "std.sync.RwLockReadGuard.deref",  engine_type_unknown());
    }
    {
        const char* T = "std.sync.RwLockWriteGuard";
        ADD_FUNC(T, "deref",       "std.sync.RwLockWriteGuard.deref", engine_type_unknown());
        ADD_FUNC(T, "deref_mut",   "std.sync.RwLockWriteGuard.deref_mut", engine_type_unknown());
    }

    /* ── core::cell extras ────────────────────────────────────── */
    {
        const char* T = "core.cell.Cell";
        ADD_FUNC(T, "get",         "core.cell.Cell.get",          engine_type_unknown());
        ADD_FUNC(T, "set",         "core.cell.Cell.set",          t_unit);
        ADD_FUNC(T, "replace",     "core.cell.Cell.replace",      engine_type_unknown());
        ADD_FUNC(T, "swap",        "core.cell.Cell.swap",         t_unit);
        ADD_FUNC(T, "into_inner",  "core.cell.Cell.into_inner",   engine_type_unknown());
        ADD_FUNC(T, "as_ptr",      "core.cell.Cell.as_ptr",       engine_type_unknown());
        ADD_FUNC(T, "take",        "core.cell.Cell.take",         engine_type_unknown());
        ADD_FUNC(T, "update",      "core.cell.Cell.update",       engine_type_unknown());
    }
    {
        const char* T = "core.cell.RefCell";
        ADD_FUNC(T, "try_borrow",  "core.cell.RefCell.try_borrow",engine_type_unknown());
        ADD_FUNC(T, "try_borrow_mut","core.cell.RefCell.try_borrow_mut", engine_type_unknown());
        ADD_FUNC(T, "into_inner",  "core.cell.RefCell.into_inner",engine_type_unknown());
        ADD_FUNC(T, "replace",     "core.cell.RefCell.replace",   engine_type_unknown());
        ADD_FUNC(T, "replace_with","core.cell.RefCell.replace_with", engine_type_unknown());
        ADD_FUNC(T, "swap",        "core.cell.RefCell.swap",      t_unit);
        ADD_FUNC(T, "take",        "core.cell.RefCell.take",      engine_type_unknown());
        ADD_FUNC(T, "as_ptr",      "core.cell.RefCell.as_ptr",    engine_type_unknown());
    }

    /* ── core::ops::Range additions ──────────────────────────── */
    {
        const char* T = "core.ops.Range";
        ADD_FUNC(T, "into_iter",   "core.ops.Range.into_iter",    engine_type_unknown());
        ADD_FUNC(T, "step_by",     "core.ops.Range.step_by",      engine_type_unknown());
        ADD_FUNC(T, "rev",         "core.ops.Range.rev",          engine_type_unknown());
        ADD_FUNC(T, "map",         "core.ops.Range.map",          engine_type_unknown());
        ADD_FUNC(T, "filter",      "core.ops.Range.filter",       engine_type_unknown());
        ADD_FUNC(T, "fold",        "core.ops.Range.fold",         engine_type_unknown());
        ADD_FUNC(T, "for_each",    "core.ops.Range.for_each",     t_unit);
        ADD_FUNC(T, "count",       "core.ops.Range.count",        t_usize);
        ADD_FUNC(T, "sum",         "core.ops.Range.sum",          engine_type_unknown());
        ADD_FUNC(T, "product",     "core.ops.Range.product",      engine_type_unknown());
        ADD_FUNC(T, "collect",     "core.ops.Range.collect",      engine_type_unknown());
        ADD_FUNC(T, "next",        "core.ops.Range.next",         engine_type_unknown());
    }
    {
        const char* T = "core.ops.RangeInclusive";
        ADD_FUNC(T, "new",         "core.ops.RangeInclusive.new", engine_type_unknown());
        ADD_FUNC(T, "contains",    "core.ops.RangeInclusive.contains", t_bool);
        ADD_FUNC(T, "start",       "core.ops.RangeInclusive.start", engine_type_unknown());
        ADD_FUNC(T, "end",         "core.ops.RangeInclusive.end", engine_type_unknown());
        ADD_FUNC(T, "is_empty",    "core.ops.RangeInclusive.is_empty", t_bool);
    }

    /* ── std::process extras ──────────────────────────────────── */
    {
        const char* T = "std.process.Command";
        ADD_FUNC(T, "args_owned",  "std.process.Command.args_owned",  engine_type_unknown());
        ADD_FUNC(T, "get_args",    "std.process.Command.get_args",    engine_type_unknown());
        ADD_FUNC(T, "get_envs",    "std.process.Command.get_envs",    engine_type_unknown());
        ADD_FUNC(T, "get_current_dir","std.process.Command.get_current_dir", engine_type_unknown());
        ADD_FUNC(T, "get_program", "std.process.Command.get_program", engine_type_unknown());
    }

    /* ── std::time extras ─────────────────────────────────────── */
    {
        const char* T = "std.time.Duration";
        ADD_FUNC(T, "as_secs_f32", "std.time.Duration.as_secs_f32",   engine_type_unknown());
        ADD_FUNC(T, "from_secs_f32","std.time.Duration.from_secs_f32",engine_type_unknown());
        ADD_FUNC(T, "div_duration_f32","std.time.Duration.div_duration_f32", engine_type_unknown());
        ADD_FUNC(T, "div_duration_f64","std.time.Duration.div_duration_f64", engine_type_unknown());
        ADD_FUNC(T, "mul_f32",     "std.time.Duration.mul_f32",       engine_type_unknown());
        ADD_FUNC(T, "mul_f64",     "std.time.Duration.mul_f64",       engine_type_unknown());
        ADD_FUNC(T, "div_f32",     "std.time.Duration.div_f32",       engine_type_unknown());
        ADD_FUNC(T, "div_f64",     "std.time.Duration.div_f64",       engine_type_unknown());
        ADD_FUNC(T, "max",         "std.time.Duration.max",           engine_type_unknown());
        ADD_FUNC(T, "min",         "std.time.Duration.min",           engine_type_unknown());
        ADD_FUNC(T, "abs_diff",    "std.time.Duration.abs_diff",      engine_type_unknown());
    }

    /* ── std::thread extras ──────────────────────────────────── */
    {
        const char* T = "std.thread.Builder";
        ADD_FUNC(T, "spawn_scoped","std.thread.Builder.spawn_scoped", engine_type_unknown());
    }
    ADD_TYPE("std.thread.ThreadId", "ThreadId", false);
    ADD_TYPE("std.thread.LocalKey", "LocalKey", false);
    ADD_TYPE("std.thread.AccessError","AccessError", false);
    {
        const char* T = "std.thread.LocalKey";
        ADD_FUNC(T, "with",        "std.thread.LocalKey.with",        engine_type_unknown());
        ADD_FUNC(T, "try_with",    "std.thread.LocalKey.try_with",    engine_type_unknown());
    }

    /* ── std::collections::BinaryHeap extras ─────────────────── */
    {
        const char* T = "alloc.collections.BinaryHeap";
        ADD_FUNC(T, "is_empty",    "alloc.collections.BinaryHeap.is_empty",   t_bool);
        ADD_FUNC(T, "iter",        "alloc.collections.BinaryHeap.iter",       engine_type_unknown());
        ADD_FUNC(T, "drain",       "alloc.collections.BinaryHeap.drain",      engine_type_unknown());
        ADD_FUNC(T, "drain_sorted","alloc.collections.BinaryHeap.drain_sorted", engine_type_unknown());
        ADD_FUNC(T, "clear",       "alloc.collections.BinaryHeap.clear",      t_unit);
        ADD_FUNC(T, "capacity",    "alloc.collections.BinaryHeap.capacity",   t_usize);
        ADD_FUNC(T, "shrink_to_fit","alloc.collections.BinaryHeap.shrink_to_fit", t_unit);
        ADD_FUNC(T, "reserve",     "alloc.collections.BinaryHeap.reserve",    t_unit);
    }

    /* ── core::iter free helpers + Iterator extras ──────────── */
    ADD_FUNC(NULL, "from_iter",    "core.iter.FromIterator.from_iter", engine_type_unknown());
    {
        const char* T = "core.iter.Iterator";
        ADD_FUNC(T, "size_hint",   "core.iter.Iterator.size_hint",    engine_type_unknown());
        ADD_FUNC(T, "advance_by",  "core.iter.Iterator.advance_by",   engine_type_unknown());
        ADD_FUNC(T, "intersperse", "core.iter.Iterator.intersperse",  engine_type_unknown());
        ADD_FUNC(T, "tuple_windows","core.iter.Iterator.tuple_windows", engine_type_unknown());
        ADD_FUNC(T, "windows",     "core.iter.Iterator.windows",      engine_type_unknown());
        ADD_FUNC(T, "is_partitioned","core.iter.Iterator.is_partitioned", t_bool);
        ADD_FUNC(T, "cmp_by",      "core.iter.Iterator.cmp_by",       engine_type_unknown());
        ADD_FUNC(T, "partial_cmp", "core.iter.Iterator.partial_cmp",  engine_type_unknown());
        ADD_FUNC(T, "eq",          "core.iter.Iterator.eq",           t_bool);
        ADD_FUNC(T, "ne",          "core.iter.Iterator.ne",           t_bool);
        ADD_FUNC(T, "lt",          "core.iter.Iterator.lt",           t_bool);
    }

    /* ── alloc::boxed::Box extras ────────────────────────────── */
    {
        const char* T = "alloc.boxed.Box";
        ADD_FUNC(T, "leak",        "alloc.boxed.Box.leak",            engine_type_unknown());
        ADD_FUNC(T, "into_pin",    "alloc.boxed.Box.into_pin",        engine_type_unknown());
        ADD_FUNC(T, "from_raw",    "alloc.boxed.Box.from_raw",        engine_type_unknown());
        ADD_FUNC(T, "into_raw",    "alloc.boxed.Box.into_raw",        engine_type_unknown());
        ADD_FUNC(T, "downcast",    "alloc.boxed.Box.downcast",        engine_type_unknown());
    }

    /* ── alloc::rc::Rc / sync::Arc extras ────────────────────── */
    {
        const char* T = "alloc.rc.Rc";
        ADD_FUNC(T, "weak_count",  "alloc.rc.Rc.weak_count",          t_usize);
        ADD_FUNC(T, "downgrade",   "alloc.rc.Rc.downgrade",           engine_type_unknown());
        ADD_FUNC(T, "get_mut",     "alloc.rc.Rc.get_mut",             engine_type_unknown());
        ADD_FUNC(T, "into_raw",    "alloc.rc.Rc.into_raw",            engine_type_unknown());
        ADD_FUNC(T, "from_raw",    "alloc.rc.Rc.from_raw",            engine_type_unknown());
        ADD_FUNC(T, "ptr_eq",      "alloc.rc.Rc.ptr_eq",              t_bool);
        ADD_FUNC(T, "make_mut",    "alloc.rc.Rc.make_mut",            engine_type_unknown());
    }
    {
        const char* T = "alloc.sync.Arc";
        ADD_FUNC(T, "weak_count",  "alloc.sync.Arc.weak_count",       t_usize);
        ADD_FUNC(T, "downgrade",   "alloc.sync.Arc.downgrade",        engine_type_unknown());
        ADD_FUNC(T, "get_mut",     "alloc.sync.Arc.get_mut",          engine_type_unknown());
        ADD_FUNC(T, "into_raw",    "alloc.sync.Arc.into_raw",         engine_type_unknown());
        ADD_FUNC(T, "from_raw",    "alloc.sync.Arc.from_raw",         engine_type_unknown());
        ADD_FUNC(T, "ptr_eq",      "alloc.sync.Arc.ptr_eq",           t_bool);
        ADD_FUNC(T, "make_mut",    "alloc.sync.Arc.make_mut",         engine_type_unknown());
        ADD_FUNC(T, "try_unwrap",  "alloc.sync.Arc.try_unwrap",       engine_type_unknown());
    }

    /* ── HashSet extras ───────────────────────────────────────── */
    {
        const char* T = "alloc.collections.HashSet";
        ADD_FUNC(T, "extend",         "alloc.collections.HashSet.extend",         t_unit);
        ADD_FUNC(T, "drain",          "alloc.collections.HashSet.drain",          engine_type_unknown());
        ADD_FUNC(T, "into_iter",      "alloc.collections.HashSet.into_iter",      engine_type_unknown());
        ADD_FUNC(T, "is_subset",      "alloc.collections.HashSet.is_subset",      t_bool);
        ADD_FUNC(T, "is_superset",    "alloc.collections.HashSet.is_superset",    t_bool);
        ADD_FUNC(T, "is_disjoint",    "alloc.collections.HashSet.is_disjoint",    t_bool);
        ADD_FUNC(T, "symmetric_difference","alloc.collections.HashSet.symmetric_difference", engine_type_unknown());
        ADD_FUNC(T, "shrink_to_fit",  "alloc.collections.HashSet.shrink_to_fit",  t_unit);
        ADD_FUNC(T, "reserve",        "alloc.collections.HashSet.reserve",        t_unit);
        ADD_FUNC(T, "capacity",       "alloc.collections.HashSet.capacity",       t_usize);
        ADD_FUNC(T, "hasher",         "alloc.collections.HashSet.hasher",         engine_type_unknown());
    }

    /* ── BTreeSet extras ──────────────────────────────────────── */
    {
        const char* T = "alloc.collections.BTreeSet";
        ADD_FUNC(T, "new",            "alloc.collections.BTreeSet.new",            engine_type_unknown());
        ADD_FUNC(T, "insert",         "alloc.collections.BTreeSet.insert",         t_bool);
        ADD_FUNC(T, "remove",         "alloc.collections.BTreeSet.remove",         t_bool);
        ADD_FUNC(T, "contains",       "alloc.collections.BTreeSet.contains",       t_bool);
        ADD_FUNC(T, "len",            "alloc.collections.BTreeSet.len",            t_usize);
        ADD_FUNC(T, "is_empty",       "alloc.collections.BTreeSet.is_empty",       t_bool);
        ADD_FUNC(T, "iter",           "alloc.collections.BTreeSet.iter",           engine_type_unknown());
        ADD_FUNC(T, "range",          "alloc.collections.BTreeSet.range",          engine_type_unknown());
        ADD_FUNC(T, "first",          "alloc.collections.BTreeSet.first",          engine_type_unknown());
        ADD_FUNC(T, "last",           "alloc.collections.BTreeSet.last",           engine_type_unknown());
    }

    /* ── std::path extras ─────────────────────────────────────── */
    {
        const char* T = "std.path.PathBuf";
        ADD_FUNC(T, "with_capacity", "std.path.PathBuf.with_capacity", engine_type_unknown());
        ADD_FUNC(T, "capacity",      "std.path.PathBuf.capacity",      t_usize);
        ADD_FUNC(T, "as_mut_os_string","std.path.PathBuf.as_mut_os_string", engine_type_unknown());
    }
    {
        const char* T = "std.path.Path";
        ADD_FUNC(T, "as_os_str",     "std.path.Path.as_os_str",        engine_type_unknown());
        ADD_FUNC(T, "ancestors",     "std.path.Path.ancestors",        engine_type_unknown());
        ADD_FUNC(T, "strip_prefix",  "std.path.Path.strip_prefix",     engine_type_unknown());
        ADD_FUNC(T, "is_normalized", "std.path.Path.is_normalized",    t_bool);
    }

    /* ── std::io extras ───────────────────────────────────────── */
    {
        const char* T = "std.io.BufReader";
        ADD_FUNC(T, "fill_buf",     "std.io.BufReader.fill_buf",      engine_type_unknown());
        ADD_FUNC(T, "consume",      "std.io.BufReader.consume",       t_unit);
        ADD_FUNC(T, "lines",        "std.io.BufReader.lines",         engine_type_unknown());
        ADD_FUNC(T, "read_line",    "std.io.BufReader.read_line",     engine_type_unknown());
    }
    {
        const char* T = "std.io.Stdin";
        ADD_FUNC(T, "lock",         "std.io.Stdin.lock",              engine_type_unknown());
        ADD_FUNC(T, "lines",        "std.io.Stdin.lines",             engine_type_unknown());
        ADD_FUNC(T, "read_line",    "std.io.Stdin.read_line",         engine_type_unknown());
    }
    {
        const char* T = "std.io.Stdout";
        ADD_FUNC(T, "lock",         "std.io.Stdout.lock",             engine_type_unknown());
        ADD_FUNC(T, "flush",        "std.io.Stdout.flush",            engine_type_unknown());
    }
    {
        const char* T = "std.io.StdoutLock";
        ADD_FUNC(T, "write",        "std.io.StdoutLock.write",        engine_type_unknown());
        ADD_FUNC(T, "write_all",    "std.io.StdoutLock.write_all",    engine_type_unknown());
    }

    /* ── core::fmt::Formatter ─────────────────────────────────── */
    ADD_TYPE("core.fmt.Formatter",   "Formatter",   false);
    ADD_TYPE("core.fmt.Result",      "Result",      false);
    ADD_TYPE("core.fmt.Error",       "Error",       false);
    ADD_TYPE("core.fmt.Arguments",   "Arguments",   false);
    {
        const char* T = "core.fmt.Formatter";
        ADD_FUNC(T, "write_str",    "core.fmt.Formatter.write_str",   engine_type_unknown());
        ADD_FUNC(T, "write_fmt",    "core.fmt.Formatter.write_fmt",   engine_type_unknown());
        ADD_FUNC(T, "pad",          "core.fmt.Formatter.pad",         engine_type_unknown());
        ADD_FUNC(T, "fill",         "core.fmt.Formatter.fill",        engine_type_unknown());
        ADD_FUNC(T, "align",        "core.fmt.Formatter.align",       engine_type_unknown());
        ADD_FUNC(T, "width",        "core.fmt.Formatter.width",       engine_type_unknown());
        ADD_FUNC(T, "precision",    "core.fmt.Formatter.precision",   engine_type_unknown());
        ADD_FUNC(T, "debug_struct", "core.fmt.Formatter.debug_struct",engine_type_unknown());
        ADD_FUNC(T, "debug_tuple",  "core.fmt.Formatter.debug_tuple", engine_type_unknown());
        ADD_FUNC(T, "debug_list",   "core.fmt.Formatter.debug_list",  engine_type_unknown());
        ADD_FUNC(T, "debug_set",    "core.fmt.Formatter.debug_set",   engine_type_unknown());
        ADD_FUNC(T, "debug_map",    "core.fmt.Formatter.debug_map",   engine_type_unknown());
    }

    /* Common-crate seeds (serde/tokio/anyhow/clap/regex/log/futures/
     * parking_lot/once_cell/chrono/uuid/reqwest/rayon). */
    engine_rust_crates_register(reg, arena);

    /* Finalise: build hash buckets so per-file lookups are O(1)
     * instead of O(n) over the ~2.5k registered entries. */
    engine_registry_finalize(reg);
}
