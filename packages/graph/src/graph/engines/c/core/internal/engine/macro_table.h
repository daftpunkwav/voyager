#pragma once
#include <stddef.h>
#include "arena.h"

#define ENGINE_MACRO_MAX_PARAMS 4
#define ENGINE_MACRO_TABLE_CAP 4096

typedef struct {
    const char *name;
    int param_count;
    const char *param_names[ENGINE_MACRO_MAX_PARAMS];
    const char *expansion;
    const char *resolved_callee;
} EngineMacroEntry;

typedef struct EngineMacroTable {
    EngineMacroEntry entries[ENGINE_MACRO_TABLE_CAP];
    int count;
    EngineArena arena;
} EngineMacroTable;

// Add an entry. Silently drops on overflow.
void engine_macro_table_add(EngineMacroTable *t, EngineArena *arena, const char *name, int param_count,
                         const char **param_names, const char *expansion,
                         const char *resolved_callee);

// Look up by name. Returns NULL if not found.
const EngineMacroEntry *engine_macro_table_find(const EngineMacroTable *t, const char *name);

// Parse a single .inc file content into the table (arena-allocated strings).
void engine_parse_inc_file(EngineMacroTable *t, EngineArena *arena, const char *content);

// Expand a macro call: substitute args into expansion text.
// Returns arena-allocated expanded text, or NULL if no expansion.
char *engine_macro_expand(EngineArena *arena, const EngineMacroEntry *entry, const char **args,
                       int arg_count);

// Extract a callee name from expanded text (looks for ##class(X).Method or $$Label^Routine).
// Returns arena-allocated "X.Method" or "Label^Routine", or NULL.
char *engine_macro_extract_callee(EngineArena *arena, const char *expansion);

// Allocate and populate a new table with the hardcoded system macros.
// Caller owns the table (stack or heap).
void engine_macro_table_init_system(EngineMacroTable *t);

// Destroy the arena inside t and free t itself. NULL-safe.
void engine_macro_table_free(EngineMacroTable *t);
