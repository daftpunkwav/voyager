/*
 * java_stdlib_data.c — Curated Java standard-library type/method registry.
 *
 * Strategy:
 *   - java.lang.* — fully covered (the implicit-import package).
 *     Object, String, StringBuilder, StringBuffer, CharSequence, Class,
 *     Throwable + the common subclass tree, Number + boxed primitives,
 *     Math, System, Thread, Iterable, Comparable, Cloneable, Enum, Record,
 *     AutoCloseable, the common Exception types.
 *   - java.util.* — collections + iterators + Optional + Date/Calendar +
 *     Arrays/Collections + Scanner/Random/UUID + Map.Entry.
 *   - java.io.* — streams, readers, writers, File, IOException family.
 *   - java.nio.file.* — Path, Paths, Files (often-used helpers).
 *   - java.util.function — the 21 functional interfaces.
 *   - java.util.stream  — Stream + Collectors entry points.
 *   - java.util.concurrent — ExecutorService, Future, CompletableFuture,
 *     ConcurrentHashMap, the concurrent collection set.
 *   - java.time — LocalDate/LocalTime/LocalDateTime/Duration/Instant.
 *
 * Method signatures use registry-level fidelity: receiver, short name,
 * return type. Param types are intentionally unmodeled (the resolver
 * chooses overloads by arity, with type compatibility scoring breaking
 * ties — see engine_registry_lookup_method_by_args).
 *
 * This is the JLS-spec-aligned slice of the stdlib that 90%+ of real-world
 * Java code touches.
 */

#include "../type_rep.h"
#include "../type_registry.h"
#include "../../arena.h"
#include "../java_lsp.h"
#include <string.h>

#define REG_TYPE(qn_, short_, is_iface_, parents_)            \
    do {                                                      \
        memset(&rt, 0, sizeof(rt));                           \
        rt.qualified_name = (qn_);                            \
        rt.short_name = (short_);                             \
        rt.is_interface = (is_iface_);                        \
        rt.embedded_types = (parents_);                       \
        engine_registry_add_type(reg, rt);                       \
    } while (0)

#define REG_METHOD(class_qn_, method_name_, ret_type_)                                          \
    do {                                                                                        \
        memset(&rf, 0, sizeof(rf));                                                             \
        rf.min_params = -1;                                                                     \
        rf.qualified_name =                                                                     \
            engine_arena_sprintf(arena, "%s.%s", (class_qn_), (method_name_));                     \
        rf.short_name = (method_name_);                                                         \
        rf.receiver_type = (class_qn_);                                                         \
        {                                                                                       \
            const EngineType **rets =                                                              \
                (const EngineType **)engine_arena_alloc(arena, 2 * sizeof(*rets));                    \
            rets[0] = (ret_type_);                                                              \
            rets[1] = NULL;                                                                     \
            rf.signature = engine_type_func(arena, NULL, NULL, rets);                              \
        }                                                                                       \
        engine_registry_add_func(reg, rf);                                                         \
    } while (0)

#define REG_CTOR(class_qn_, short_name_)                                              \
    do {                                                                              \
        memset(&rf, 0, sizeof(rf));                                                   \
        rf.min_params = -1;                                                           \
        rf.qualified_name =                                                           \
            engine_arena_sprintf(arena, "%s.%s", (class_qn_), (short_name_));            \
        rf.short_name = (short_name_);                                                \
        rf.receiver_type = (class_qn_);                                               \
        {                                                                             \
            const EngineType **rets =                                                    \
                (const EngineType **)engine_arena_alloc(arena, 2 * sizeof(*rets));          \
            rets[0] = engine_type_named(arena, (class_qn_));                             \
            rets[1] = NULL;                                                           \
            rf.signature = engine_type_func(arena, NULL, NULL, rets);                    \
        }                                                                             \
        engine_registry_add_func(reg, rf);                                               \
    } while (0)

#define REG_FIELD(class_qn_, name_, type_)                                            \
    do {                                                                              \
        const EngineRegisteredType *_existing =                                          \
            engine_registry_lookup_type(reg, (class_qn_));                               \
        (void)_existing;                                                              \
        /* Field append handled by REG_TYPE_FIELDS below. */                          \
        /* Placeholder for future per-field appends. */                               \
    } while (0)

void engine_java_stdlib_register(EngineTypeRegistry *reg, EngineArena *arena) {
    EngineRegisteredType rt;
    EngineRegisteredFunc rf;

    /* ── Type-parent lists (must be static so addresses outlive the call) ── */
    static const char *no_parents[] = {NULL};
    static const char *parents_object[] = {"java.lang.Object", NULL};
    static const char *parents_throwable[] = {"java.lang.Object", NULL};
    static const char *parents_exception[] = {"java.lang.Throwable", NULL};
    static const char *parents_error[] = {"java.lang.Throwable", NULL};
    static const char *parents_runtime_exc[] = {"java.lang.Exception", NULL};
    static const char *parents_io_exc[] = {"java.lang.Exception", NULL};
    static const char *parents_number[] = {"java.lang.Object", NULL};
    static const char *parents_integer[] = {"java.lang.Number", NULL};
    static const char *parents_long[] = {"java.lang.Number", NULL};
    static const char *parents_double[] = {"java.lang.Number", NULL};
    static const char *parents_float[] = {"java.lang.Number", NULL};
    static const char *parents_short[] = {"java.lang.Number", NULL};
    static const char *parents_byte[] = {"java.lang.Number", NULL};
    static const char *parents_string[] = {"java.lang.Object", NULL};
    static const char *parents_charseq[] = {NULL};
    static const char *parents_iterable[] = {NULL};
    static const char *parents_collection[] = {"java.lang.Iterable", NULL};
    static const char *parents_list[] = {"java.util.Collection", NULL};
    static const char *parents_set[] = {"java.util.Collection", NULL};
    static const char *parents_queue[] = {"java.util.Collection", NULL};
    static const char *parents_deque[] = {"java.util.Queue", NULL};
    static const char *parents_map[] = {NULL};
    static const char *parents_map_entry[] = {NULL};
    static const char *parents_iterator[] = {NULL};
    static const char *parents_arraylist[] = {"java.util.List", NULL};
    static const char *parents_linkedlist[] = {"java.util.List", NULL};
    static const char *parents_hashset[] = {"java.util.Set", NULL};
    static const char *parents_treeset[] = {"java.util.Set", NULL};
    static const char *parents_linkedhashset[] = {"java.util.Set", NULL};
    static const char *parents_hashmap[] = {"java.util.Map", NULL};
    static const char *parents_treemap[] = {"java.util.Map", NULL};
    static const char *parents_linkedhashmap[] = {"java.util.Map", NULL};
    static const char *parents_concurrent_hashmap[] = {"java.util.Map", NULL};

    static const char *parents_inputstream[] = {"java.lang.AutoCloseable", NULL};
    static const char *parents_outputstream[] = {"java.lang.AutoCloseable", NULL};
    static const char *parents_reader[] = {"java.lang.AutoCloseable", NULL};
    static const char *parents_writer[] = {"java.lang.AutoCloseable", NULL};
    static const char *parents_buffered_reader[] = {"java.io.Reader", NULL};
    static const char *parents_buffered_writer[] = {"java.io.Writer", NULL};
    static const char *parents_print_stream[] = {"java.io.OutputStream", NULL};
    static const char *parents_print_writer[] = {"java.io.Writer", NULL};
    static const char *parents_file_input_stream[] = {"java.io.InputStream", NULL};
    static const char *parents_file_output_stream[] = {"java.io.OutputStream", NULL};
    static const char *parents_file_reader[] = {"java.io.Reader", NULL};
    static const char *parents_file_writer[] = {"java.io.Writer", NULL};
    static const char *parents_io_exception[] = {"java.lang.Exception", NULL};
    static const char *parents_runtime_exc_chain[] = {"java.lang.RuntimeException", NULL};
    /* Parent lists for types previously registered with inline compound
     * literals. A compound literal has automatic (block) storage duration,
     * so storing its address into the registry left a dangling stack pointer
     * once the REG_TYPE statement's block ended — an AddressSanitizer
     * stack-use-after-scope when the inheritance walk later read
     * rt->embedded_types[0]. These must be static so their addresses outlive
     * the call, exactly like the parent lists above. */
    static const char *parents_gregorian_calendar[] = {"java.util.Calendar", NULL};
    static const char *parents_file_not_found_exc[] = {"java.io.IOException", NULL};
    static const char *parents_closeable[] = {"java.lang.AutoCloseable", NULL};
    static const char *parents_unary_operator[] = {"java.util.function.Function", NULL};
    static const char *parents_binary_operator[] = {"java.util.function.BiFunction", NULL};
    static const char *parents_completable_future[] = {"java.util.concurrent.Future", NULL};
    static const char *parents_reentrant_lock[] = {"java.util.concurrent.locks.Lock", NULL};

    /* ── java.lang ─────────────────────────────────────────────── */
    REG_TYPE("java.lang.Object", "Object", false, no_parents);
    REG_TYPE("java.lang.Class", "Class", false, parents_object);
    REG_TYPE("java.lang.ClassLoader", "ClassLoader", false, parents_object);
    REG_TYPE("java.lang.CharSequence", "CharSequence", true, parents_charseq);
    REG_TYPE("java.lang.String", "String", false, parents_string);
    REG_TYPE("java.lang.StringBuilder", "StringBuilder", false, parents_object);
    REG_TYPE("java.lang.StringBuffer", "StringBuffer", false, parents_object);
    REG_TYPE("java.lang.Number", "Number", false, parents_number);
    REG_TYPE("java.lang.Integer", "Integer", false, parents_integer);
    REG_TYPE("java.lang.Long", "Long", false, parents_long);
    REG_TYPE("java.lang.Short", "Short", false, parents_short);
    REG_TYPE("java.lang.Byte", "Byte", false, parents_byte);
    REG_TYPE("java.lang.Float", "Float", false, parents_float);
    REG_TYPE("java.lang.Double", "Double", false, parents_double);
    REG_TYPE("java.lang.Boolean", "Boolean", false, parents_object);
    REG_TYPE("java.lang.Character", "Character", false, parents_object);
    REG_TYPE("java.lang.Void", "Void", false, parents_object);
    REG_TYPE("java.lang.Iterable", "Iterable", true, parents_iterable);
    REG_TYPE("java.lang.Comparable", "Comparable", true, no_parents);
    REG_TYPE("java.lang.Cloneable", "Cloneable", true, no_parents);
    REG_TYPE("java.lang.Runnable", "Runnable", true, no_parents);
    REG_TYPE("java.lang.AutoCloseable", "AutoCloseable", true, no_parents);
    REG_TYPE("java.lang.Math", "Math", false, parents_object);
    REG_TYPE("java.lang.System", "System", false, parents_object);
    REG_TYPE("java.lang.Thread", "Thread", false, parents_object);
    REG_TYPE("java.lang.Process", "Process", false, parents_object);
    REG_TYPE("java.lang.ProcessBuilder", "ProcessBuilder", false, parents_object);
    REG_TYPE("java.lang.StackTraceElement", "StackTraceElement", false, parents_object);
    REG_TYPE("java.lang.Enum", "Enum", false, parents_object);
    REG_TYPE("java.lang.Record", "Record", false, parents_object);
    REG_TYPE("java.lang.Throwable", "Throwable", false, parents_throwable);
    REG_TYPE("java.lang.Exception", "Exception", false, parents_exception);
    REG_TYPE("java.lang.Error", "Error", false, parents_error);
    REG_TYPE("java.lang.RuntimeException", "RuntimeException", false, parents_runtime_exc);
    REG_TYPE("java.lang.NullPointerException", "NullPointerException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.IllegalArgumentException", "IllegalArgumentException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.IllegalStateException", "IllegalStateException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.IndexOutOfBoundsException", "IndexOutOfBoundsException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.ArrayIndexOutOfBoundsException", "ArrayIndexOutOfBoundsException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.ArithmeticException", "ArithmeticException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.ClassCastException", "ClassCastException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.ClassNotFoundException", "ClassNotFoundException", false,
             parents_exception);
    REG_TYPE("java.lang.NumberFormatException", "NumberFormatException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.UnsupportedOperationException", "UnsupportedOperationException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.InterruptedException", "InterruptedException", false, parents_exception);
    REG_TYPE("java.lang.SecurityException", "SecurityException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.lang.NoSuchMethodException", "NoSuchMethodException", false, parents_exception);
    REG_TYPE("java.lang.NoSuchFieldException", "NoSuchFieldException", false, parents_exception);

    /* Annotation-marker types. */
    REG_TYPE("java.lang.Override", "Override", true, no_parents);
    REG_TYPE("java.lang.Deprecated", "Deprecated", true, no_parents);
    REG_TYPE("java.lang.SuppressWarnings", "SuppressWarnings", true, no_parents);
    REG_TYPE("java.lang.FunctionalInterface", "FunctionalInterface", true, no_parents);

    /* ── Object methods ───────────────────────────────────────── */
    REG_METHOD("java.lang.Object", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Object", "hashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Object", "equals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Object", "getClass", engine_type_named(arena, "java.lang.Class"));
    REG_METHOD("java.lang.Object", "wait", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Object", "notify", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Object", "notifyAll", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Object", "clone", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.lang.Object", "finalize", engine_type_builtin(arena, "void"));

    /* ── String methods ───────────────────────────────────────── */
    REG_METHOD("java.lang.String", "length", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "isBlank", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "charAt", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.String", "codePointAt", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "equals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "equalsIgnoreCase", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "compareTo", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "compareToIgnoreCase", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "indexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "lastIndexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "contains", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "startsWith", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "endsWith", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "matches", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.String", "concat", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "substring", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "trim", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "strip", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "stripLeading", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "stripTrailing", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "toLowerCase", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "toUpperCase", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "replace", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "replaceAll", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "replaceFirst", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "split",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.String")));
    REG_METHOD("java.lang.String", "toCharArray", engine_type_slice(arena, engine_type_builtin(arena, "char")));
    REG_METHOD("java.lang.String", "getBytes", engine_type_slice(arena, engine_type_builtin(arena, "byte")));
    REG_METHOD("java.lang.String", "intern", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "format", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "valueOf", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "join", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "repeat", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "lines", engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.lang.String", "chars", engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.lang.String", "codePoints",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.lang.String", "hashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.String", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.String", "toCharArray", engine_type_slice(arena, engine_type_builtin(arena, "char")));
    REG_CTOR("java.lang.String", "String");

    /* ── StringBuilder / StringBuffer ─────────────────────────── */
    REG_METHOD("java.lang.StringBuilder", "append",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "insert",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "delete",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "deleteCharAt",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "replace",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "reverse",
               engine_type_named(arena, "java.lang.StringBuilder"));
    REG_METHOD("java.lang.StringBuilder", "toString",
               engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.StringBuilder", "length", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.StringBuilder", "charAt", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.StringBuilder", "setLength", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.StringBuilder", "indexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.StringBuilder", "substring",
               engine_type_named(arena, "java.lang.String"));
    REG_CTOR("java.lang.StringBuilder", "StringBuilder");

    REG_METHOD("java.lang.StringBuffer", "append",
               engine_type_named(arena, "java.lang.StringBuffer"));
    REG_METHOD("java.lang.StringBuffer", "toString",
               engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.StringBuffer", "length", engine_type_builtin(arena, "int"));
    REG_CTOR("java.lang.StringBuffer", "StringBuffer");

    /* ── CharSequence ─────────────────────────────────────────── */
    REG_METHOD("java.lang.CharSequence", "length", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.CharSequence", "charAt", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.CharSequence", "subSequence",
               engine_type_named(arena, "java.lang.CharSequence"));
    REG_METHOD("java.lang.CharSequence", "toString",
               engine_type_named(arena, "java.lang.String"));

    /* ── Number + boxed types ─────────────────────────────────── */
    REG_METHOD("java.lang.Number", "intValue", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Number", "longValue", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Number", "doubleValue", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Number", "floatValue", engine_type_builtin(arena, "float"));
    REG_METHOD("java.lang.Number", "shortValue", engine_type_builtin(arena, "short"));
    REG_METHOD("java.lang.Number", "byteValue", engine_type_builtin(arena, "byte"));

    REG_METHOD("java.lang.Integer", "intValue", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "parseInt", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "valueOf", engine_type_named(arena, "java.lang.Integer"));
    REG_METHOD("java.lang.Integer", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Integer", "compare", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "compareTo", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "equals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Integer", "hashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "max", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "min", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "sum", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "bitCount", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Integer", "toBinaryString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Integer", "toHexString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Integer", "toOctalString", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.lang.Long", "longValue", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Long", "parseLong", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Long", "valueOf", engine_type_named(arena, "java.lang.Long"));
    REG_METHOD("java.lang.Long", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Long", "compareTo", engine_type_builtin(arena, "int"));

    REG_METHOD("java.lang.Double", "doubleValue", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Double", "parseDouble", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Double", "valueOf", engine_type_named(arena, "java.lang.Double"));
    REG_METHOD("java.lang.Double", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Double", "isNaN", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Double", "isInfinite", engine_type_builtin(arena, "boolean"));

    REG_METHOD("java.lang.Float", "floatValue", engine_type_builtin(arena, "float"));
    REG_METHOD("java.lang.Float", "parseFloat", engine_type_builtin(arena, "float"));
    REG_METHOD("java.lang.Float", "valueOf", engine_type_named(arena, "java.lang.Float"));

    REG_METHOD("java.lang.Boolean", "booleanValue", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Boolean", "parseBoolean", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Boolean", "valueOf", engine_type_named(arena, "java.lang.Boolean"));
    REG_METHOD("java.lang.Boolean", "toString", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.lang.Character", "charValue", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.Character", "isDigit", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "isLetter", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "isLetterOrDigit", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "isWhitespace", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "isUpperCase", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "isLowerCase", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Character", "toUpperCase", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.Character", "toLowerCase", engine_type_builtin(arena, "char"));
    REG_METHOD("java.lang.Character", "getNumericValue", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.Character", "valueOf", engine_type_named(arena, "java.lang.Character"));

    REG_METHOD("java.lang.Byte", "byteValue", engine_type_builtin(arena, "byte"));
    REG_METHOD("java.lang.Byte", "parseByte", engine_type_builtin(arena, "byte"));
    REG_METHOD("java.lang.Byte", "valueOf", engine_type_named(arena, "java.lang.Byte"));

    REG_METHOD("java.lang.Short", "shortValue", engine_type_builtin(arena, "short"));
    REG_METHOD("java.lang.Short", "parseShort", engine_type_builtin(arena, "short"));
    REG_METHOD("java.lang.Short", "valueOf", engine_type_named(arena, "java.lang.Short"));

    /* ── Math ─────────────────────────────────────────────────── */
    REG_METHOD("java.lang.Math", "abs", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "min", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "max", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "sqrt", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "cbrt", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "pow", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "exp", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "log", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "log10", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "sin", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "cos", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "tan", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "asin", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "acos", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "atan", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "atan2", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "floor", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "ceil", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "round", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "random", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "signum", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "hypot", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "floorDiv", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "floorMod", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "addExact", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "subtractExact", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "multiplyExact", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Math", "toRadians", engine_type_builtin(arena, "double"));
    REG_METHOD("java.lang.Math", "toDegrees", engine_type_builtin(arena, "double"));

    /* ── System ───────────────────────────────────────────────── */
    REG_METHOD("java.lang.System", "currentTimeMillis", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.System", "nanoTime", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.System", "exit", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.System", "getenv", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.System", "getProperty", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.System", "setProperty", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.System", "lineSeparator", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.System", "arraycopy", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.System", "identityHashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.lang.System", "gc", engine_type_builtin(arena, "void"));

    /* ── Thread ───────────────────────────────────────────────── */
    REG_METHOD("java.lang.Thread", "start", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "run", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "join", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "interrupt", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "isAlive", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Thread", "sleep", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "currentThread", engine_type_named(arena, "java.lang.Thread"));
    REG_METHOD("java.lang.Thread", "yield", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "getName", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Thread", "setName", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Thread", "getId", engine_type_builtin(arena, "long"));
    REG_METHOD("java.lang.Thread", "isInterrupted", engine_type_builtin(arena, "boolean"));

    /* ── Class ────────────────────────────────────────────────── */
    REG_METHOD("java.lang.Class", "getName", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Class", "getSimpleName", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Class", "getCanonicalName", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Class", "isInterface", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Class", "isArray", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Class", "isAssignableFrom", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Class", "isInstance", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.lang.Class", "newInstance", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.lang.Class", "forName", engine_type_named(arena, "java.lang.Class"));
    REG_METHOD("java.lang.Class", "getSuperclass", engine_type_named(arena, "java.lang.Class"));
    REG_METHOD("java.lang.Class", "getInterfaces",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Class")));

    /* ── Iterable / Iterator ──────────────────────────────────── */
    REG_METHOD("java.lang.Iterable", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.lang.Iterable", "forEach", engine_type_builtin(arena, "void"));

    /* ── Throwable methods ────────────────────────────────────── */
    REG_METHOD("java.lang.Throwable", "getMessage", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Throwable", "getLocalizedMessage",
               engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Throwable", "getCause", engine_type_named(arena, "java.lang.Throwable"));
    REG_METHOD("java.lang.Throwable", "initCause",
               engine_type_named(arena, "java.lang.Throwable"));
    REG_METHOD("java.lang.Throwable", "printStackTrace", engine_type_builtin(arena, "void"));
    REG_METHOD("java.lang.Throwable", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.lang.Throwable", "getStackTrace",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.StackTraceElement")));

    /* ── AutoCloseable ────────────────────────────────────────── */
    REG_METHOD("java.lang.AutoCloseable", "close", engine_type_builtin(arena, "void"));

    /* ── Comparable ───────────────────────────────────────────── */
    REG_METHOD("java.lang.Comparable", "compareTo", engine_type_builtin(arena, "int"));

    /* ── Runnable ─────────────────────────────────────────────── */
    REG_METHOD("java.lang.Runnable", "run", engine_type_builtin(arena, "void"));

    /* ── java.util ────────────────────────────────────────────── */
    REG_TYPE("java.util.Collection", "Collection", true, parents_collection);
    REG_TYPE("java.util.List", "List", true, parents_list);
    REG_TYPE("java.util.Set", "Set", true, parents_set);
    REG_TYPE("java.util.Queue", "Queue", true, parents_queue);
    REG_TYPE("java.util.Deque", "Deque", true, parents_deque);
    REG_TYPE("java.util.Map", "Map", true, parents_map);
    REG_TYPE("java.util.Map.Entry", "Entry", true, parents_map_entry);
    REG_TYPE("java.util.Iterator", "Iterator", true, parents_iterator);
    REG_TYPE("java.util.ListIterator", "ListIterator", true, parents_iterator);
    REG_TYPE("java.util.Spliterator", "Spliterator", true, no_parents);
    REG_TYPE("java.util.Comparator", "Comparator", true, no_parents);

    REG_TYPE("java.util.ArrayList", "ArrayList", false, parents_arraylist);
    REG_TYPE("java.util.LinkedList", "LinkedList", false, parents_linkedlist);
    REG_TYPE("java.util.Vector", "Vector", false, parents_arraylist);
    REG_TYPE("java.util.Stack", "Stack", false, parents_arraylist);
    REG_TYPE("java.util.HashSet", "HashSet", false, parents_hashset);
    REG_TYPE("java.util.TreeSet", "TreeSet", false, parents_treeset);
    REG_TYPE("java.util.LinkedHashSet", "LinkedHashSet", false, parents_linkedhashset);
    REG_TYPE("java.util.HashMap", "HashMap", false, parents_hashmap);
    REG_TYPE("java.util.TreeMap", "TreeMap", false, parents_treemap);
    REG_TYPE("java.util.LinkedHashMap", "LinkedHashMap", false, parents_linkedhashmap);
    REG_TYPE("java.util.ArrayDeque", "ArrayDeque", false, parents_deque);
    REG_TYPE("java.util.PriorityQueue", "PriorityQueue", false, parents_queue);

    REG_TYPE("java.util.Optional", "Optional", false, parents_object);
    REG_TYPE("java.util.OptionalInt", "OptionalInt", false, parents_object);
    REG_TYPE("java.util.OptionalLong", "OptionalLong", false, parents_object);
    REG_TYPE("java.util.OptionalDouble", "OptionalDouble", false, parents_object);
    REG_TYPE("java.util.Date", "Date", false, parents_object);
    REG_TYPE("java.util.Calendar", "Calendar", false, parents_object);
    REG_TYPE("java.util.GregorianCalendar", "GregorianCalendar", false,
             parents_gregorian_calendar);
    REG_TYPE("java.util.TimeZone", "TimeZone", false, parents_object);
    REG_TYPE("java.util.Locale", "Locale", false, parents_object);
    REG_TYPE("java.util.UUID", "UUID", false, parents_object);
    REG_TYPE("java.util.Random", "Random", false, parents_object);
    REG_TYPE("java.util.Scanner", "Scanner", false, parents_object);
    REG_TYPE("java.util.Arrays", "Arrays", false, parents_object);
    REG_TYPE("java.util.Collections", "Collections", false, parents_object);
    REG_TYPE("java.util.Objects", "Objects", false, parents_object);
    REG_TYPE("java.util.Properties", "Properties", false, parents_hashmap);
    REG_TYPE("java.util.regex.Pattern", "Pattern", false, parents_object);
    REG_TYPE("java.util.regex.Matcher", "Matcher", false, parents_object);

    /* ── Collection methods ───────────────────────────────────── */
    REG_METHOD("java.util.Collection", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Collection", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "contains", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "containsAll", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.util.Collection", "toArray",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Object")));
    REG_METHOD("java.util.Collection", "add", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "addAll", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "remove", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "removeAll", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "retainAll", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Collection", "clear", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Collection", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.Collection", "parallelStream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.Collection", "forEach", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Collection", "removeIf", engine_type_builtin(arena, "boolean"));

    /* ── List methods ─────────────────────────────────────────── */
    REG_METHOD("java.util.List", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.List", "set", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.List", "add", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.List", "remove", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.List", "indexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.List", "lastIndexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.List", "subList", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.List", "of", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.List", "copyOf", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.List", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.List", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.List", "contains", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.List", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.util.List", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.List", "forEach", engine_type_builtin(arena, "void"));

    /* ── ArrayList ────────────────────────────────────────────── */
    REG_METHOD("java.util.ArrayList", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.ArrayList", "set", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.ArrayList", "add", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.ArrayList", "remove", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.ArrayList", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.ArrayList", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.ArrayList", "indexOf", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.ArrayList", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.util.ArrayList", "clear", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.ArrayList", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.ArrayList", "toArray",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Object")));
    REG_METHOD("java.util.ArrayList", "subList", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.ArrayList", "trimToSize", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.ArrayList", "ensureCapacity", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.ArrayList", "forEach", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.ArrayList", "removeIf", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.List", "removeIf", engine_type_builtin(arena, "boolean"));
    REG_CTOR("java.util.ArrayList", "ArrayList");

    REG_METHOD("java.util.LinkedList", "addFirst", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.LinkedList", "addLast", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.LinkedList", "removeFirst", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "removeLast", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "getFirst", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "getLast", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "peek", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "poll", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.LinkedList", "offer", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.LinkedList", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.LinkedList", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_CTOR("java.util.LinkedList", "LinkedList");

    /* ── Set methods ──────────────────────────────────────────── */
    REG_METHOD("java.util.Set", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Set", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Set", "contains", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Set", "add", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Set", "remove", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Set", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.util.Set", "of", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Set", "copyOf", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Set", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.Set", "forEach", engine_type_builtin(arena, "void"));

    REG_METHOD("java.util.HashSet", "add", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashSet", "remove", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashSet", "contains", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashSet", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.HashSet", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashSet", "iterator", engine_type_named(arena, "java.util.Iterator"));
    REG_METHOD("java.util.HashSet", "clear", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.HashSet", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_CTOR("java.util.HashSet", "HashSet");

    REG_METHOD("java.util.TreeSet", "first", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.TreeSet", "last", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.TreeSet", "headSet", engine_type_named(arena, "java.util.SortedSet"));
    REG_METHOD("java.util.TreeSet", "tailSet", engine_type_named(arena, "java.util.SortedSet"));
    REG_CTOR("java.util.TreeSet", "TreeSet");

    REG_CTOR("java.util.LinkedHashSet", "LinkedHashSet");

    /* ── Map methods ──────────────────────────────────────────── */
    REG_METHOD("java.util.Map", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "put", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "remove", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "containsKey", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Map", "containsValue", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Map", "keySet", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Map", "values", engine_type_named(arena, "java.util.Collection"));
    REG_METHOD("java.util.Map", "entrySet", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Map", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Map", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Map", "putAll", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Map", "clear", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Map", "getOrDefault", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "putIfAbsent", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "computeIfAbsent", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "compute", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "merge", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map", "of", engine_type_named(arena, "java.util.Map"));
    REG_METHOD("java.util.Map", "copyOf", engine_type_named(arena, "java.util.Map"));
    REG_METHOD("java.util.Map", "ofEntries", engine_type_named(arena, "java.util.Map"));
    REG_METHOD("java.util.Map", "entry", engine_type_named(arena, "java.util.Map.Entry"));
    REG_METHOD("java.util.Map", "forEach", engine_type_builtin(arena, "void"));

    REG_METHOD("java.util.Map.Entry", "getKey", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map.Entry", "getValue", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Map.Entry", "setValue", engine_type_named(arena, "java.lang.Object"));

    REG_METHOD("java.util.HashMap", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.HashMap", "put", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.HashMap", "remove", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.HashMap", "containsKey", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashMap", "containsValue", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashMap", "size", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.HashMap", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.HashMap", "keySet", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.HashMap", "values", engine_type_named(arena, "java.util.Collection"));
    REG_METHOD("java.util.HashMap", "entrySet", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.HashMap", "clear", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.HashMap", "getOrDefault", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.HashMap", "putIfAbsent", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.HashMap", "forEach", engine_type_builtin(arena, "void"));
    REG_CTOR("java.util.HashMap", "HashMap");

    REG_METHOD("java.util.TreeMap", "firstKey", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.TreeMap", "lastKey", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.TreeMap", "headMap", engine_type_named(arena, "java.util.SortedMap"));
    REG_METHOD("java.util.TreeMap", "tailMap", engine_type_named(arena, "java.util.SortedMap"));
    REG_CTOR("java.util.TreeMap", "TreeMap");

    REG_CTOR("java.util.LinkedHashMap", "LinkedHashMap");

    /* ── Iterator methods ─────────────────────────────────────── */
    REG_METHOD("java.util.Iterator", "hasNext", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Iterator", "next", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Iterator", "remove", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Iterator", "forEachRemaining", engine_type_builtin(arena, "void"));

    /* ── Optional ─────────────────────────────────────────────── */
    REG_METHOD("java.util.Optional", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Optional", "isPresent", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Optional", "isEmpty", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Optional", "orElse", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Optional", "orElseGet", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Optional", "orElseThrow", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Optional", "ifPresent", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Optional", "ifPresentOrElse", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Optional", "map", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "flatMap", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "filter", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "of", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "ofNullable", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "empty", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.Optional", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));

    /* ── Arrays / Collections / Objects helpers ───────────────── */
    REG_METHOD("java.util.Arrays", "asList", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.Arrays", "stream",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.Arrays", "sort", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Arrays", "binarySearch", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Arrays", "fill", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Arrays", "copyOf",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Object")));
    REG_METHOD("java.util.Arrays", "copyOfRange",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Object")));
    REG_METHOD("java.util.Arrays", "equals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Arrays", "hashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Arrays", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Arrays", "deepEquals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Arrays", "deepToString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Arrays", "deepHashCode", engine_type_builtin(arena, "int"));

    REG_METHOD("java.util.Collections", "sort", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Collections", "reverse", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Collections", "shuffle", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Collections", "min", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Collections", "max", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Collections", "emptyList", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.Collections", "emptySet", engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Collections", "emptyMap", engine_type_named(arena, "java.util.Map"));
    REG_METHOD("java.util.Collections", "singletonList",
               engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.Collections", "singleton",
               engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Collections", "unmodifiableList",
               engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.Collections", "unmodifiableSet",
               engine_type_named(arena, "java.util.Set"));
    REG_METHOD("java.util.Collections", "unmodifiableMap",
               engine_type_named(arena, "java.util.Map"));
    REG_METHOD("java.util.Collections", "frequency", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Collections", "binarySearch", engine_type_builtin(arena, "int"));

    REG_METHOD("java.util.Objects", "equals", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Objects", "hashCode", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Objects", "hash", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Objects", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Objects", "isNull", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Objects", "nonNull", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Objects", "requireNonNull", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.Objects", "requireNonNullElse",
               engine_type_named(arena, "java.lang.Object"));

    /* ── UUID, Random, Scanner ────────────────────────────────── */
    REG_METHOD("java.util.UUID", "randomUUID", engine_type_named(arena, "java.util.UUID"));
    REG_METHOD("java.util.UUID", "fromString", engine_type_named(arena, "java.util.UUID"));
    REG_METHOD("java.util.UUID", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.UUID", "getMostSignificantBits", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.UUID", "getLeastSignificantBits", engine_type_builtin(arena, "long"));
    REG_CTOR("java.util.UUID", "UUID");

    REG_METHOD("java.util.Random", "nextInt", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Random", "nextLong", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.Random", "nextDouble", engine_type_builtin(arena, "double"));
    REG_METHOD("java.util.Random", "nextFloat", engine_type_builtin(arena, "float"));
    REG_METHOD("java.util.Random", "nextBoolean", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Random", "nextGaussian", engine_type_builtin(arena, "double"));
    REG_METHOD("java.util.Random", "setSeed", engine_type_builtin(arena, "void"));
    REG_CTOR("java.util.Random", "Random");

    REG_METHOD("java.util.Scanner", "next", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Scanner", "nextLine", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Scanner", "nextInt", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Scanner", "nextLong", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.Scanner", "nextDouble", engine_type_builtin(arena, "double"));
    REG_METHOD("java.util.Scanner", "hasNext", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Scanner", "hasNextLine", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Scanner", "hasNextInt", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Scanner", "close", engine_type_builtin(arena, "void"));
    REG_CTOR("java.util.Scanner", "Scanner");

    /* ── Locale / Date / Calendar / TimeZone ──────────────────── */
    REG_METHOD("java.util.Locale", "getLanguage", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Locale", "getCountry", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Locale", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.Locale", "getDefault", engine_type_named(arena, "java.util.Locale"));
    REG_CTOR("java.util.Locale", "Locale");

    REG_METHOD("java.util.Date", "getTime", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.Date", "setTime", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Date", "before", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Date", "after", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.Date", "compareTo", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Date", "toString", engine_type_named(arena, "java.lang.String"));
    REG_CTOR("java.util.Date", "Date");

    REG_METHOD("java.util.Calendar", "getInstance", engine_type_named(arena, "java.util.Calendar"));
    REG_METHOD("java.util.Calendar", "getTime", engine_type_named(arena, "java.util.Date"));
    REG_METHOD("java.util.Calendar", "set", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.Calendar", "get", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.Calendar", "add", engine_type_builtin(arena, "void"));

    REG_METHOD("java.util.TimeZone", "getDefault", engine_type_named(arena, "java.util.TimeZone"));
    REG_METHOD("java.util.TimeZone", "getID", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.TimeZone", "getTimeZone", engine_type_named(arena, "java.util.TimeZone"));

    /* ── regex ────────────────────────────────────────────────── */
    REG_METHOD("java.util.regex.Pattern", "compile",
               engine_type_named(arena, "java.util.regex.Pattern"));
    REG_METHOD("java.util.regex.Pattern", "matcher",
               engine_type_named(arena, "java.util.regex.Matcher"));
    REG_METHOD("java.util.regex.Pattern", "matches", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.regex.Pattern", "split",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.String")));
    REG_METHOD("java.util.regex.Pattern", "pattern", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.util.regex.Matcher", "matches", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.regex.Matcher", "find", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.regex.Matcher", "group", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.regex.Matcher", "groupCount", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.regex.Matcher", "start", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.regex.Matcher", "end", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.regex.Matcher", "replaceAll", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.util.regex.Matcher", "replaceFirst",
               engine_type_named(arena, "java.lang.String"));

    /* ── java.io ──────────────────────────────────────────────── */
    REG_TYPE("java.io.InputStream", "InputStream", false, parents_inputstream);
    REG_TYPE("java.io.OutputStream", "OutputStream", false, parents_outputstream);
    REG_TYPE("java.io.Reader", "Reader", false, parents_reader);
    REG_TYPE("java.io.Writer", "Writer", false, parents_writer);
    REG_TYPE("java.io.BufferedReader", "BufferedReader", false, parents_buffered_reader);
    REG_TYPE("java.io.BufferedWriter", "BufferedWriter", false, parents_buffered_writer);
    REG_TYPE("java.io.PrintStream", "PrintStream", false, parents_print_stream);
    REG_TYPE("java.io.PrintWriter", "PrintWriter", false, parents_print_writer);
    REG_TYPE("java.io.FileInputStream", "FileInputStream", false, parents_file_input_stream);
    REG_TYPE("java.io.FileOutputStream", "FileOutputStream", false, parents_file_output_stream);
    REG_TYPE("java.io.FileReader", "FileReader", false, parents_file_reader);
    REG_TYPE("java.io.FileWriter", "FileWriter", false, parents_file_writer);
    REG_TYPE("java.io.File", "File", false, parents_object);
    REG_TYPE("java.io.IOException", "IOException", false, parents_io_exception);
    REG_TYPE("java.io.FileNotFoundException", "FileNotFoundException", false,
             parents_file_not_found_exc);
    REG_TYPE("java.io.UncheckedIOException", "UncheckedIOException", false,
             parents_runtime_exc_chain);
    REG_TYPE("java.io.Serializable", "Serializable", true, no_parents);
    REG_TYPE("java.io.Closeable", "Closeable", true,
             parents_closeable);
    REG_TYPE("java.io.Flushable", "Flushable", true, no_parents);

    REG_METHOD("java.io.PrintStream", "println", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintStream", "print", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintStream", "printf", engine_type_named(arena, "java.io.PrintStream"));
    REG_METHOD("java.io.PrintStream", "format", engine_type_named(arena, "java.io.PrintStream"));
    REG_METHOD("java.io.PrintStream", "write", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintStream", "flush", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintStream", "close", engine_type_builtin(arena, "void"));

    REG_METHOD("java.io.PrintWriter", "println", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintWriter", "print", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintWriter", "printf", engine_type_named(arena, "java.io.PrintWriter"));
    REG_METHOD("java.io.PrintWriter", "flush", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.PrintWriter", "close", engine_type_builtin(arena, "void"));
    REG_CTOR("java.io.PrintWriter", "PrintWriter");

    REG_METHOD("java.io.InputStream", "read", engine_type_builtin(arena, "int"));
    REG_METHOD("java.io.InputStream", "close", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.InputStream", "available", engine_type_builtin(arena, "int"));
    REG_METHOD("java.io.InputStream", "skip", engine_type_builtin(arena, "long"));
    REG_METHOD("java.io.InputStream", "readAllBytes",
               engine_type_slice(arena, engine_type_builtin(arena, "byte")));

    REG_METHOD("java.io.OutputStream", "write", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.OutputStream", "flush", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.OutputStream", "close", engine_type_builtin(arena, "void"));

    REG_METHOD("java.io.Reader", "read", engine_type_builtin(arena, "int"));
    REG_METHOD("java.io.Reader", "close", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.Reader", "ready", engine_type_builtin(arena, "boolean"));

    REG_METHOD("java.io.Writer", "write", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.Writer", "flush", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.Writer", "close", engine_type_builtin(arena, "void"));

    REG_METHOD("java.io.BufferedReader", "readLine", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.BufferedReader", "lines",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.io.BufferedReader", "close", engine_type_builtin(arena, "void"));
    REG_CTOR("java.io.BufferedReader", "BufferedReader");

    REG_METHOD("java.io.BufferedWriter", "write", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.BufferedWriter", "newLine", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.BufferedWriter", "flush", engine_type_builtin(arena, "void"));
    REG_METHOD("java.io.BufferedWriter", "close", engine_type_builtin(arena, "void"));
    REG_CTOR("java.io.BufferedWriter", "BufferedWriter");

    REG_METHOD("java.io.File", "exists", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "isFile", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "isDirectory", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "canRead", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "canWrite", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "getName", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.File", "getPath", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.File", "getAbsolutePath", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.File", "getCanonicalPath", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.File", "getParent", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.io.File", "getParentFile", engine_type_named(arena, "java.io.File"));
    REG_METHOD("java.io.File", "length", engine_type_builtin(arena, "long"));
    REG_METHOD("java.io.File", "lastModified", engine_type_builtin(arena, "long"));
    REG_METHOD("java.io.File", "mkdir", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "mkdirs", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "delete", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "renameTo", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.io.File", "list",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.String")));
    REG_METHOD("java.io.File", "listFiles",
               engine_type_slice(arena, engine_type_named(arena, "java.io.File")));
    REG_METHOD("java.io.File", "toPath", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.io.File", "toURI", engine_type_named(arena, "java.net.URI"));
    REG_CTOR("java.io.File", "File");

    /* ── java.nio.file ───────────────────────────────────────── */
    REG_TYPE("java.nio.file.Path", "Path", true, no_parents);
    REG_TYPE("java.nio.file.Paths", "Paths", false, parents_object);
    REG_TYPE("java.nio.file.Files", "Files", false, parents_object);

    REG_METHOD("java.nio.file.Path", "getFileName", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "getParent", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "getRoot", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "resolve", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "resolveSibling",
               engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "relativize", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "normalize", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "toAbsolutePath",
               engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Path", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.nio.file.Path", "toFile", engine_type_named(arena, "java.io.File"));
    REG_METHOD("java.nio.file.Path", "of", engine_type_named(arena, "java.nio.file.Path"));

    REG_METHOD("java.nio.file.Paths", "get", engine_type_named(arena, "java.nio.file.Path"));

    REG_METHOD("java.nio.file.Files", "exists", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.nio.file.Files", "isDirectory", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.nio.file.Files", "isRegularFile", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.nio.file.Files", "readString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.nio.file.Files", "writeString", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "readAllLines", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.nio.file.Files", "readAllBytes",
               engine_type_slice(arena, engine_type_builtin(arena, "byte")));
    REG_METHOD("java.nio.file.Files", "lines",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.nio.file.Files", "list",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.nio.file.Files", "walk",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.nio.file.Files", "createDirectory",
               engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "createDirectories",
               engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "createFile",
               engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "delete", engine_type_builtin(arena, "void"));
    REG_METHOD("java.nio.file.Files", "deleteIfExists", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.nio.file.Files", "copy", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "move", engine_type_named(arena, "java.nio.file.Path"));
    REG_METHOD("java.nio.file.Files", "size", engine_type_builtin(arena, "long"));

    /* ── java.util.function (the 21 functional interfaces) ──── */
    REG_TYPE("java.util.function.Function", "Function", true, no_parents);
    REG_TYPE("java.util.function.BiFunction", "BiFunction", true, no_parents);
    REG_TYPE("java.util.function.Predicate", "Predicate", true, no_parents);
    REG_TYPE("java.util.function.BiPredicate", "BiPredicate", true, no_parents);
    REG_TYPE("java.util.function.Consumer", "Consumer", true, no_parents);
    REG_TYPE("java.util.function.BiConsumer", "BiConsumer", true, no_parents);
    REG_TYPE("java.util.function.Supplier", "Supplier", true, no_parents);
    REG_TYPE("java.util.function.UnaryOperator", "UnaryOperator", true,
             parents_unary_operator);
    REG_TYPE("java.util.function.BinaryOperator", "BinaryOperator", true,
             parents_binary_operator);
    REG_TYPE("java.util.function.IntFunction", "IntFunction", true, no_parents);
    REG_TYPE("java.util.function.LongFunction", "LongFunction", true, no_parents);
    REG_TYPE("java.util.function.DoubleFunction", "DoubleFunction", true, no_parents);
    REG_TYPE("java.util.function.IntPredicate", "IntPredicate", true, no_parents);
    REG_TYPE("java.util.function.LongPredicate", "LongPredicate", true, no_parents);
    REG_TYPE("java.util.function.DoublePredicate", "DoublePredicate", true, no_parents);
    REG_TYPE("java.util.function.IntConsumer", "IntConsumer", true, no_parents);
    REG_TYPE("java.util.function.LongConsumer", "LongConsumer", true, no_parents);
    REG_TYPE("java.util.function.DoubleConsumer", "DoubleConsumer", true, no_parents);
    REG_TYPE("java.util.function.IntSupplier", "IntSupplier", true, no_parents);
    REG_TYPE("java.util.function.LongSupplier", "LongSupplier", true, no_parents);
    REG_TYPE("java.util.function.DoubleSupplier", "DoubleSupplier", true, no_parents);
    REG_TYPE("java.util.function.BooleanSupplier", "BooleanSupplier", true, no_parents);
    REG_TYPE("java.util.function.ToIntFunction", "ToIntFunction", true, no_parents);
    REG_TYPE("java.util.function.ToLongFunction", "ToLongFunction", true, no_parents);
    REG_TYPE("java.util.function.ToDoubleFunction", "ToDoubleFunction", true, no_parents);

    REG_METHOD("java.util.function.Function", "apply", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.function.Function", "compose",
               engine_type_named(arena, "java.util.function.Function"));
    REG_METHOD("java.util.function.Function", "andThen",
               engine_type_named(arena, "java.util.function.Function"));
    REG_METHOD("java.util.function.Function", "identity",
               engine_type_named(arena, "java.util.function.Function"));

    REG_METHOD("java.util.function.BiFunction", "apply",
               engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.function.BiFunction", "andThen",
               engine_type_named(arena, "java.util.function.BiFunction"));

    REG_METHOD("java.util.function.Predicate", "test", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.function.Predicate", "and",
               engine_type_named(arena, "java.util.function.Predicate"));
    REG_METHOD("java.util.function.Predicate", "or",
               engine_type_named(arena, "java.util.function.Predicate"));
    REG_METHOD("java.util.function.Predicate", "negate",
               engine_type_named(arena, "java.util.function.Predicate"));
    REG_METHOD("java.util.function.Predicate", "isEqual",
               engine_type_named(arena, "java.util.function.Predicate"));

    REG_METHOD("java.util.function.Consumer", "accept", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.function.Consumer", "andThen",
               engine_type_named(arena, "java.util.function.Consumer"));

    REG_METHOD("java.util.function.Supplier", "get", engine_type_named(arena, "java.lang.Object"));

    REG_METHOD("java.util.function.UnaryOperator", "identity",
               engine_type_named(arena, "java.util.function.UnaryOperator"));
    REG_METHOD("java.util.function.UnaryOperator", "apply",
               engine_type_named(arena, "java.lang.Object"));

    /* ── java.util.stream ────────────────────────────────────── */
    REG_TYPE("java.util.stream.Stream", "Stream", true, no_parents);
    REG_TYPE("java.util.stream.IntStream", "IntStream", true, no_parents);
    REG_TYPE("java.util.stream.LongStream", "LongStream", true, no_parents);
    REG_TYPE("java.util.stream.DoubleStream", "DoubleStream", true, no_parents);
    REG_TYPE("java.util.stream.Collectors", "Collectors", false, parents_object);
    REG_TYPE("java.util.stream.Collector", "Collector", true, no_parents);

    REG_METHOD("java.util.stream.Stream", "filter",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "map",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "flatMap",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "mapToInt",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.util.stream.Stream", "mapToLong",
               engine_type_named(arena, "java.util.stream.LongStream"));
    REG_METHOD("java.util.stream.Stream", "mapToDouble",
               engine_type_named(arena, "java.util.stream.DoubleStream"));
    REG_METHOD("java.util.stream.Stream", "sorted",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "distinct",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "limit",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "skip",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "peek",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "forEach", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.stream.Stream", "forEachOrdered", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.stream.Stream", "toArray",
               engine_type_slice(arena, engine_type_named(arena, "java.lang.Object")));
    REG_METHOD("java.util.stream.Stream", "toList", engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.stream.Stream", "reduce", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.stream.Stream", "collect", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.stream.Stream", "count", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.stream.Stream", "anyMatch", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.stream.Stream", "allMatch", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.stream.Stream", "noneMatch", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.stream.Stream", "findFirst",
               engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.stream.Stream", "findAny",
               engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.stream.Stream", "min", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.stream.Stream", "max", engine_type_named(arena, "java.util.Optional"));
    REG_METHOD("java.util.stream.Stream", "of",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "empty",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "concat",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "iterate",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.Stream", "generate",
               engine_type_named(arena, "java.util.stream.Stream"));

    REG_METHOD("java.util.stream.IntStream", "sum", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.stream.IntStream", "average",
               engine_type_named(arena, "java.util.OptionalDouble"));
    REG_METHOD("java.util.stream.IntStream", "max",
               engine_type_named(arena, "java.util.OptionalInt"));
    REG_METHOD("java.util.stream.IntStream", "min",
               engine_type_named(arena, "java.util.OptionalInt"));
    REG_METHOD("java.util.stream.IntStream", "count", engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.stream.IntStream", "boxed",
               engine_type_named(arena, "java.util.stream.Stream"));
    REG_METHOD("java.util.stream.IntStream", "filter",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.util.stream.IntStream", "map",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.util.stream.IntStream", "range",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.util.stream.IntStream", "rangeClosed",
               engine_type_named(arena, "java.util.stream.IntStream"));
    REG_METHOD("java.util.stream.IntStream", "of",
               engine_type_named(arena, "java.util.stream.IntStream"));

    REG_METHOD("java.util.stream.Collectors", "toList",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "toSet",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "toMap",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "joining",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "groupingBy",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "partitioningBy",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "counting",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "summingInt",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "averagingDouble",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "mapping",
               engine_type_named(arena, "java.util.stream.Collector"));
    REG_METHOD("java.util.stream.Collectors", "reducing",
               engine_type_named(arena, "java.util.stream.Collector"));

    /* ── java.util.concurrent ────────────────────────────────── */
    REG_TYPE("java.util.concurrent.ExecutorService", "ExecutorService", true, no_parents);
    REG_TYPE("java.util.concurrent.Executors", "Executors", false, parents_object);
    REG_TYPE("java.util.concurrent.Future", "Future", true, no_parents);
    REG_TYPE("java.util.concurrent.CompletableFuture", "CompletableFuture", false,
             parents_completable_future);
    REG_TYPE("java.util.concurrent.ConcurrentHashMap", "ConcurrentHashMap", false,
             parents_concurrent_hashmap);
    REG_TYPE("java.util.concurrent.ConcurrentMap", "ConcurrentMap", true, parents_map);
    REG_TYPE("java.util.concurrent.TimeUnit", "TimeUnit", false, parents_object);
    REG_TYPE("java.util.concurrent.atomic.AtomicInteger", "AtomicInteger", false, parents_object);
    REG_TYPE("java.util.concurrent.atomic.AtomicLong", "AtomicLong", false, parents_object);
    REG_TYPE("java.util.concurrent.atomic.AtomicBoolean", "AtomicBoolean", false, parents_object);
    REG_TYPE("java.util.concurrent.atomic.AtomicReference", "AtomicReference", false,
             parents_object);
    REG_TYPE("java.util.concurrent.locks.Lock", "Lock", true, no_parents);
    REG_TYPE("java.util.concurrent.locks.ReentrantLock", "ReentrantLock", false,
             parents_reentrant_lock);
    REG_TYPE("java.util.concurrent.locks.ReadWriteLock", "ReadWriteLock", true, no_parents);

    REG_METHOD("java.util.concurrent.ExecutorService", "submit",
               engine_type_named(arena, "java.util.concurrent.Future"));
    REG_METHOD("java.util.concurrent.ExecutorService", "execute", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.ExecutorService", "shutdown", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.ExecutorService", "shutdownNow",
               engine_type_named(arena, "java.util.List"));
    REG_METHOD("java.util.concurrent.ExecutorService", "awaitTermination",
               engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.concurrent.ExecutorService", "isShutdown",
               engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.concurrent.ExecutorService", "isTerminated",
               engine_type_builtin(arena, "boolean"));

    REG_METHOD("java.util.concurrent.Executors", "newFixedThreadPool",
               engine_type_named(arena, "java.util.concurrent.ExecutorService"));
    REG_METHOD("java.util.concurrent.Executors", "newSingleThreadExecutor",
               engine_type_named(arena, "java.util.concurrent.ExecutorService"));
    REG_METHOD("java.util.concurrent.Executors", "newCachedThreadPool",
               engine_type_named(arena, "java.util.concurrent.ExecutorService"));
    REG_METHOD("java.util.concurrent.Executors", "newScheduledThreadPool",
               engine_type_named(arena, "java.util.concurrent.ExecutorService"));

    REG_METHOD("java.util.concurrent.Future", "get", engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.concurrent.Future", "isDone", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.concurrent.Future", "cancel", engine_type_builtin(arena, "boolean"));

    REG_METHOD("java.util.concurrent.CompletableFuture", "thenApply",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "thenAccept",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "thenCompose",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "thenCombine",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "exceptionally",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "join",
               engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "supplyAsync",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "runAsync",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "completedFuture",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "allOf",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));
    REG_METHOD("java.util.concurrent.CompletableFuture", "anyOf",
               engine_type_named(arena, "java.util.concurrent.CompletableFuture"));

    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "get", engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "set", engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "incrementAndGet",
               engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "decrementAndGet",
               engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "getAndIncrement",
               engine_type_builtin(arena, "int"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "compareAndSet",
               engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.util.concurrent.atomic.AtomicInteger", "addAndGet",
               engine_type_builtin(arena, "int"));
    REG_CTOR("java.util.concurrent.atomic.AtomicInteger", "AtomicInteger");

    REG_METHOD("java.util.concurrent.atomic.AtomicLong", "get",
               engine_type_builtin(arena, "long"));
    REG_METHOD("java.util.concurrent.atomic.AtomicLong", "incrementAndGet",
               engine_type_builtin(arena, "long"));
    REG_CTOR("java.util.concurrent.atomic.AtomicLong", "AtomicLong");

    REG_METHOD("java.util.concurrent.atomic.AtomicReference", "get",
               engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.concurrent.atomic.AtomicReference", "set",
               engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.atomic.AtomicReference", "compareAndSet",
               engine_type_builtin(arena, "boolean"));
    REG_CTOR("java.util.concurrent.atomic.AtomicReference", "AtomicReference");

    REG_METHOD("java.util.concurrent.locks.ReentrantLock", "lock",
               engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.locks.ReentrantLock", "unlock",
               engine_type_builtin(arena, "void"));
    REG_METHOD("java.util.concurrent.locks.ReentrantLock", "tryLock",
               engine_type_builtin(arena, "boolean"));
    REG_CTOR("java.util.concurrent.locks.ReentrantLock", "ReentrantLock");

    REG_METHOD("java.util.concurrent.ConcurrentHashMap", "put",
               engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.concurrent.ConcurrentHashMap", "get",
               engine_type_named(arena, "java.lang.Object"));
    REG_METHOD("java.util.concurrent.ConcurrentHashMap", "putIfAbsent",
               engine_type_named(arena, "java.lang.Object"));
    REG_CTOR("java.util.concurrent.ConcurrentHashMap", "ConcurrentHashMap");

    /* ── java.time ───────────────────────────────────────────── */
    REG_TYPE("java.time.LocalDate", "LocalDate", false, parents_object);
    REG_TYPE("java.time.LocalTime", "LocalTime", false, parents_object);
    REG_TYPE("java.time.LocalDateTime", "LocalDateTime", false, parents_object);
    REG_TYPE("java.time.ZonedDateTime", "ZonedDateTime", false, parents_object);
    REG_TYPE("java.time.OffsetDateTime", "OffsetDateTime", false, parents_object);
    REG_TYPE("java.time.Instant", "Instant", false, parents_object);
    REG_TYPE("java.time.Duration", "Duration", false, parents_object);
    REG_TYPE("java.time.Period", "Period", false, parents_object);
    REG_TYPE("java.time.ZoneId", "ZoneId", false, parents_object);
    REG_TYPE("java.time.format.DateTimeFormatter", "DateTimeFormatter", false, parents_object);

    REG_METHOD("java.time.LocalDate", "now", engine_type_named(arena, "java.time.LocalDate"));
    REG_METHOD("java.time.LocalDate", "of", engine_type_named(arena, "java.time.LocalDate"));
    REG_METHOD("java.time.LocalDate", "parse", engine_type_named(arena, "java.time.LocalDate"));
    REG_METHOD("java.time.LocalDate", "plusDays", engine_type_named(arena, "java.time.LocalDate"));
    REG_METHOD("java.time.LocalDate", "minusDays", engine_type_named(arena, "java.time.LocalDate"));
    REG_METHOD("java.time.LocalDate", "getYear", engine_type_builtin(arena, "int"));
    REG_METHOD("java.time.LocalDate", "getMonth", engine_type_named(arena, "java.time.Month"));
    REG_METHOD("java.time.LocalDate", "getDayOfMonth", engine_type_builtin(arena, "int"));
    REG_METHOD("java.time.LocalDate", "getDayOfWeek",
               engine_type_named(arena, "java.time.DayOfWeek"));
    REG_METHOD("java.time.LocalDate", "isAfter", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.time.LocalDate", "isBefore", engine_type_builtin(arena, "boolean"));
    REG_METHOD("java.time.LocalDate", "format", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.time.LocalDate", "toString", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.time.LocalDateTime", "now",
               engine_type_named(arena, "java.time.LocalDateTime"));
    REG_METHOD("java.time.LocalDateTime", "of",
               engine_type_named(arena, "java.time.LocalDateTime"));
    REG_METHOD("java.time.LocalDateTime", "parse",
               engine_type_named(arena, "java.time.LocalDateTime"));
    REG_METHOD("java.time.LocalDateTime", "plusHours",
               engine_type_named(arena, "java.time.LocalDateTime"));
    REG_METHOD("java.time.LocalDateTime", "minusHours",
               engine_type_named(arena, "java.time.LocalDateTime"));
    REG_METHOD("java.time.LocalDateTime", "format", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.time.LocalDateTime", "toString", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.time.Instant", "now", engine_type_named(arena, "java.time.Instant"));
    REG_METHOD("java.time.Instant", "ofEpochMilli", engine_type_named(arena, "java.time.Instant"));
    REG_METHOD("java.time.Instant", "ofEpochSecond", engine_type_named(arena, "java.time.Instant"));
    REG_METHOD("java.time.Instant", "toEpochMilli", engine_type_builtin(arena, "long"));
    REG_METHOD("java.time.Instant", "getEpochSecond", engine_type_builtin(arena, "long"));
    REG_METHOD("java.time.Instant", "plus", engine_type_named(arena, "java.time.Instant"));
    REG_METHOD("java.time.Instant", "minus", engine_type_named(arena, "java.time.Instant"));

    REG_METHOD("java.time.Duration", "ofSeconds", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "ofMillis", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "ofMinutes", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "ofHours", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "ofDays", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "between", engine_type_named(arena, "java.time.Duration"));
    REG_METHOD("java.time.Duration", "toMillis", engine_type_builtin(arena, "long"));
    REG_METHOD("java.time.Duration", "toSeconds", engine_type_builtin(arena, "long"));
    REG_METHOD("java.time.Duration", "toMinutes", engine_type_builtin(arena, "long"));

    REG_METHOD("java.time.ZoneId", "of", engine_type_named(arena, "java.time.ZoneId"));
    REG_METHOD("java.time.ZoneId", "systemDefault", engine_type_named(arena, "java.time.ZoneId"));
    REG_METHOD("java.time.ZoneId", "getId", engine_type_named(arena, "java.lang.String"));

    REG_METHOD("java.time.format.DateTimeFormatter", "ofPattern",
               engine_type_named(arena, "java.time.format.DateTimeFormatter"));
    REG_METHOD("java.time.format.DateTimeFormatter", "format",
               engine_type_named(arena, "java.lang.String"));

    /* ── java.net (minimal) ──────────────────────────────────── */
    REG_TYPE("java.net.URI", "URI", false, parents_object);
    REG_TYPE("java.net.URL", "URL", false, parents_object);
    REG_METHOD("java.net.URI", "create", engine_type_named(arena, "java.net.URI"));
    REG_METHOD("java.net.URI", "toString", engine_type_named(arena, "java.lang.String"));
    REG_METHOD("java.net.URI", "toURL", engine_type_named(arena, "java.net.URL"));
    REG_METHOD("java.net.URL", "openStream", engine_type_named(arena, "java.io.InputStream"));
    REG_METHOD("java.net.URL", "toString", engine_type_named(arena, "java.lang.String"));
    REG_CTOR("java.net.URL", "URL");
    REG_CTOR("java.net.URI", "URI");
}
