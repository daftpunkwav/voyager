#ifndef ENGINE_GIT_CONTEXT_H
#define ENGINE_GIT_CONTEXT_H

#include <stdbool.h>

typedef struct {
    bool is_git;
    bool is_worktree;
    bool is_detached;
    bool root_exists;
    char *input_path;
    char *worktree_root;
    char *git_dir;
    char *git_common_dir;
    char *canonical_root;
    char *branch;
    char *branch_slug;
    char *head_sha;
    char *base_sha;
} engine_git_context_t;

int engine_git_context_resolve(const char *path, engine_git_context_t *out);
void engine_git_context_free(engine_git_context_t *ctx);
char *engine_git_context_branch_qn(const char *project_name, const engine_git_context_t *ctx);
int engine_git_context_props_json(const engine_git_context_t *ctx, char *buf, int buf_size);

#endif
