#include "scope.h"
#include <string.h>

EngineScope* engine_scope_push(EngineArena* a, EngineScope* current) {
    EngineScope* scope = (EngineScope*)engine_arena_alloc(a, sizeof(EngineScope));
    if (!scope) {
        return current;
    }
    memset(scope, 0, sizeof(EngineScope));
    scope->parent = current;
    scope->arena = a;
    return scope;
}

EngineScope* engine_scope_pop(EngineScope* scope) {
    if (!scope) {
        return NULL;
    }
    return scope->parent;
}

static EngineScopeChunk* alloc_chunk(EngineScope* scope) {
    if (!scope->arena) {
        return NULL;
    }
    EngineScopeChunk* c = (EngineScopeChunk*)engine_arena_alloc(scope->arena, sizeof(EngineScopeChunk));
    if (!c) {
        return NULL;
    }
    memset(c, 0, sizeof(EngineScopeChunk));
    c->next = scope->chunks;
    scope->chunks = c;
    return c;
}

/* Returns false when the binding could NOT be recorded in THIS frame.
 *
 * The failure that matters is arena exhaustion in alloc_chunk: the old void
 * form returned silently, so a caller that then consulted the scope CHAIN saw
 * the parent's binding for the same name and concluded the child had been
 * bound. For callable-value proof that is a fabricated identity -- the shadow
 * never took effect, yet the parent's callable looks like the child's. Callers
 * needing that distinction must use the checked form and consult the LOCAL
 * result, not a chain lookup. */
static bool engine_scope_bind_value(EngineScope *scope, const char *name, const EngineType *type,
                                 const char *callable_qn) {
    if (!scope || !name) {
        return false;
    }
    for (EngineScopeChunk* c = scope->chunks; c != NULL; c = c->next) {
        for (int i = 0; i < c->used; i++) {
            if (c->bindings[i].name && strcmp(c->bindings[i].name, name) == 0) {
                c->bindings[i].type = type;
                c->bindings[i].callable_qn = callable_qn;
                return true;
            }
        }
    }
    EngineScopeChunk* head = scope->chunks;
    if (!head || head->used >= ENGINE_SCOPE_CHUNK_BINDINGS) {
        head = alloc_chunk(scope);
        if (!head) {
            return false; /* arena exhausted: the shadow did NOT take effect */
        }
    }
    head->bindings[head->used].name = name;
    head->bindings[head->used].type = type;
    head->bindings[head->used].callable_qn = callable_qn;
    head->used++;
    return true;
}

void engine_scope_bind(EngineScope *scope, const char *name, const EngineType *type) {
    (void)engine_scope_bind_value(scope, name, type, NULL);
}

bool engine_scope_bind_checked(EngineScope *scope, const char *name, const EngineType *type) {
    return engine_scope_bind_value(scope, name, type, NULL);
}

void engine_scope_bind_callable(EngineScope *scope, const char *name, const EngineType *type,
                             const char *callable_qn) {
    (void)engine_scope_bind_value(scope, name, type, callable_qn);
}

bool engine_scope_bind_callable_checked(EngineScope *scope, const char *name, const EngineType *type,
                                     const char *callable_qn) {
    return engine_scope_bind_value(scope, name, type, callable_qn);
}

const EngineType* engine_scope_lookup(const EngineScope* scope, const char* name) {
    if (!name) {
        return engine_type_unknown();
    }
    for (const EngineScope* s = scope; s != NULL; s = s->parent) {
        for (EngineScopeChunk* c = s->chunks; c != NULL; c = c->next) {
            for (int i = 0; i < c->used; i++) {
                if (c->bindings[i].name && strcmp(c->bindings[i].name, name) == 0) {
                    return c->bindings[i].type;
                }
            }
        }
    }
    return engine_type_unknown();
}

bool engine_scope_contains(const EngineScope *scope, const char *name) {
    if (!name) {
        return false;
    }
    for (const EngineScope *s = scope; s != NULL; s = s->parent) {
        for (const EngineScopeChunk *c = s->chunks; c != NULL; c = c->next) {
            for (int i = 0; i < c->used; i++) {
                if (c->bindings[i].name && strcmp(c->bindings[i].name, name) == 0) {
                    return true;
                }
            }
        }
    }
    return false;
}

const char *engine_scope_lookup_callable(const EngineScope *scope, const char *name) {
    if (!name) {
        return NULL;
    }
    for (const EngineScope *s = scope; s != NULL; s = s->parent) {
        for (const EngineScopeChunk *c = s->chunks; c != NULL; c = c->next) {
            for (int i = 0; i < c->used; i++) {
                if (c->bindings[i].name && strcmp(c->bindings[i].name, name) == 0) {
                    return c->bindings[i].callable_qn;
                }
            }
        }
    }
    return NULL;
}

bool engine_scope_update_callable(EngineScope *scope, const char *name, const char *callable_qn) {
    if (!name) {
        return false;
    }
    for (EngineScope *s = scope; s != NULL; s = s->parent) {
        for (EngineScopeChunk *c = s->chunks; c != NULL; c = c->next) {
            for (int i = 0; i < c->used; i++) {
                if (c->bindings[i].name && strcmp(c->bindings[i].name, name) == 0) {
                    c->bindings[i].callable_qn = callable_qn;
                    return true;
                }
            }
        }
    }
    return false;
}
