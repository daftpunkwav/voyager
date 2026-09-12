/*
 * http_server.c — embedded HTTP for the graph engine: routes and the
 * /api, /rpc handlers.
 * (Voyager uses this service as a sidecar; the visual UI lives in apps/web.)
 *
 * Transport (sockets, parsing, limits) lives in httpd.c; this file owns
 * the routes and their handlers:
 *   GET /             → verified external index.html
 *   GET /assets/...   → verified external JS/CSS
 *   POST /rpc         → JSON-RPC dispatch via own engine_mcp_server_t
 *   OPTIONS /rpc      → CORS preflight (for vite dev on :5173)
 *   GET/POST /api/... → UI support endpoints (layout, index, browse, …)
 *   *                 → 404
 *
 * Runs in a background pthread. Binds to 127.0.0.1 only (see httpd.c).
 * Has its own engine_mcp_server_t with a separate SQLite connection (WAL reader).
 */
#include "ui/http_server.h"
#include "ui/httpd.h"
#include "ui/asset_pack.h"
#include "mcp/mcp.h"
#include "store/store.h"
#include "watcher/watcher.h"
#include "cli/cli.h"
#include "git/git_context.h"

#if defined(HAVE_LIBGIT2)
#include <git2.h> /* git_repository_open, git_remote_lookup, git_remote_url */
#endif
/* pipeline.h no longer needed — indexing runs as subprocess */
#include "foundation/log.h"
#include "foundation/platform.h"
#include "foundation/secure_random.h"
#include "foundation/sha256.h"
#include "foundation/compat.h"
#include "foundation/compat_fs.h"
#include "foundation/str_util.h"
#include "foundation/compat_thread.h"
#include "foundation/subprocess.h" /* engine_build_win_cmdline — shared MS-CRT arg quoting */
#include "foundation/win_utf8.h"   /* engine_utf8_to_wide — CreateProcessW wide cmdline (#423/#20) */
#include "foundation/workspace.h"

#include <sqlite3/sqlite3.h>
#include <yyjson/yyjson.h>

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <process.h>
#include <psapi.h> /* GetProcessMemoryInfo */
#else
#include <sys/stat.h>
#include <unistd.h>
#include <sys/wait.h>
#endif
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

/* ── Constants ────────────────────────────────────────────────── */

/* Max JSON-RPC request body size (1 MB) — transport enforces the same cap. */
#define MAX_BODY_SIZE ENGINE_HTTP_MAX_BODY

/* ── CORS: only allow localhost origins (blocks remote website attacks) ────── */

/* Per-request CORS header buffers. Updated at the start of each dispatch.
 * The server handles requests sequentially on one thread (see httpd.h),
 * which makes these statics safe. */
static char g_cors[256];      /* CORS headers only */
static char g_cors_json[512]; /* CORS + Content-Type: application/json */

static bool origin_is_same_server(const char *origin, int port) {
    char expected[128];
    int length = snprintf(expected, sizeof(expected), "http://127.0.0.1:%d", port);
    if (length > 0 && (size_t)length < sizeof(expected) && strcmp(origin, expected) == 0)
        return true;
    length = snprintf(expected, sizeof(expected), "http://localhost:%d", port);
    return length > 0 && (size_t)length < sizeof(expected) && strcmp(origin, expected) == 0;
}

static bool origin_matches_host(const char *origin, const char *host, int port) {
    /* Two literal loopback forms only — spelled out so the static URL audit
     * sees the complete URL each branch can produce. */
    char expected[128];
    int length = strncmp(host, "localhost", 9) == 0
                     ? snprintf(expected, sizeof(expected), "http://localhost:%d", port)
                     : snprintf(expected, sizeof(expected), "http://127.0.0.1:%d", port);
    return length > 0 && (size_t)length < sizeof(expected) && strcmp(origin, expected) == 0;
}

/* Foreign origins are rejected before this runs. Reflect only the exact
 * same-server origin; a different localhost port is a different principal. */
static void update_cors(const engine_http_req_t *req, int port) {
    if (req->origin[0] != '\0' && origin_is_same_server(req->origin, port)) {
        snprintf(g_cors, sizeof(g_cors),
                 "Access-Control-Allow-Origin: %s\r\n"
                 "Access-Control-Allow-Methods: POST, GET, DELETE, OPTIONS\r\n"
                 "Access-Control-Allow-Headers: Content-Type\r\n",
                 req->origin);
    } else {
        /* No Access-Control-Allow-Origin → browser blocks cross-origin access */
        snprintf(g_cors, sizeof(g_cors),
                 "Access-Control-Allow-Methods: POST, GET, DELETE, OPTIONS\r\n"
                 "Access-Control-Allow-Headers: Content-Type\r\n");
    }
    snprintf(g_cors_json, sizeof(g_cors_json), "%sContent-Type: application/json\r\n", g_cors);
}

static const char *detect_ui_lang(const char *accept_language) {
    if (accept_language && (strstr(accept_language, "zh-CN") || strstr(accept_language, "zh"))) {
        return "zh";
    }
    return "en";
}


/* ── Server state ─────────────────────────────────────────────── */

#define MAX_INDEX_JOBS 4

enum {
    HTTP_RUN_IDLE = 0,
    HTTP_RUN_SCHEDULED = 1,
    HTTP_RUN_RUNNING = 2,
    HTTP_RUN_COMPLETED = 3,
};

typedef struct {
    engine_http_server_t *server;
    char root_path[1024];
    char project_name[256];
    atomic_int status; /* 0=idle, 1=running, 2=done, 3=error */
    char error_msg[256];
    engine_thread_t thread;
    bool thread_started;
    atomic_int completed;
} index_job_t;

struct engine_http_server {
    engine_httpd_t *listener;
    engine_mcp_server_t *mcp;       /* own MCP server instance (read-only) */
    struct engine_watcher *watcher; /* external watcher ref (not owned) */
    engine_http_index_executor_fn index_executor;
    void *index_executor_context;
    engine_http_project_mutation_begin_fn mutation_begin;
    engine_http_project_mutation_end_fn mutation_end;
    void *mutation_context;
    index_job_t index_jobs[MAX_INDEX_JOBS];
    atomic_int stop_flag;
    atomic_int run_state;
    int port;
    bool listener_ok;
    uint8_t readiness_secret[ENGINE_SHA256_DIGEST_LEN];
    bool readiness_secret_set;
};

/* ── Serve verified frontend asset ───────────────────────────── */

/* Content-Security-Policy for the served UI. No external host appears in any
 * directive, so the browser cannot load or connect to anything off-origin —
 * this ENFORCES the airgap (the code makes no external calls; this stops a
 * future dependency or injected content from doing so). connect-src 'self'
 * confines fetch/XHR/WebSocket to the local server. The 'self'/data:/blob:/
 * 'unsafe-inline'-style/'wasm-unsafe-eval' allowances cover the bundled app's
 * own needs (React inline styles, three.js textures/workers/WASM). */
#define ENGINE_UI_CSP                                                       \
    "Content-Security-Policy: default-src 'self'; connect-src 'self'; "  \
    "img-src 'self' data: blob:; script-src 'self' 'wasm-unsafe-eval'; " \
    "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "          \
    "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'\r\n"

static bool serve_frontend_asset(engine_http_conn_t *c, const char *path) {
    const engine_ui_asset_t *f = engine_ui_asset_lookup(path);
    if (!f)
        return false;

    /* Build headers with correct Content-Type for this asset */
    char hdrs[1024];
    const char *cache = f->cache == ENGINE_UI_ASSET_REVALIDATE
                            ? "Cache-Control: no-cache\r\n"
                            : "Cache-Control: public, max-age=31536000, immutable\r\n";
    snprintf(hdrs, sizeof(hdrs),
             "%sContent-Type: %s\r\n"
             "%sX-Content-Type-Options: nosniff\r\n" ENGINE_UI_CSP,
             g_cors, f->content_type, cache);

    engine_http_reply_buf(c, 200, hdrs, f->data, f->size);
    return true;
}

/* Build DB path for a project: <cache_dir>/<project>.db */
static void db_path_for_project(const char *project, char *buf, size_t bufsz) {
    if (!engine_validate_project_name(project)) {
        buf[0] = '\0';
        return;
    }
    const char *dir = engine_resolve_cache_dir();
    if (!dir) {
        dir = engine_tmpdir();
    }
    snprintf(buf, bufsz, "%s/%s.db", dir, project);
}

/* ── Log ring buffer ──────────────────────────────────────────── */

#define LOG_RING_SIZE 500
#define LOG_LINE_MAX 512

static char g_log_ring[LOG_RING_SIZE][LOG_LINE_MAX];
static int g_log_head = 0;
static int g_log_count = 0;
static engine_mutex_t g_log_mutex;

enum { ENGINE_LOG_MUTEX_UNINIT = 0, ENGINE_LOG_MUTEX_INITING = 1, ENGINE_LOG_MUTEX_INITED = 2 };
static atomic_int g_log_mutex_init = ENGINE_LOG_MUTEX_UNINIT;

/* Safe for concurrent callers: only publishes INITED after engine_mutex_init()
 * has completed. Callers that lose the CAS race spin until init finishes. */
void engine_ui_log_init(void) {
    int state = atomic_load(&g_log_mutex_init);
    if (state == ENGINE_LOG_MUTEX_INITED)
        return;

    state = ENGINE_LOG_MUTEX_UNINIT;
    if (atomic_compare_exchange_strong(&g_log_mutex_init, &state, ENGINE_LOG_MUTEX_INITING)) {
        engine_mutex_init(&g_log_mutex);
        atomic_store(&g_log_mutex_init, ENGINE_LOG_MUTEX_INITED);
        return;
    }

    /* Another thread is initializing — spin until done */
    while (atomic_load(&g_log_mutex_init) != ENGINE_LOG_MUTEX_INITED) {
        engine_usleep(1000); /* 1ms */
    }
}

/* Called from a log hook — appends a line to the ring buffer (thread-safe) */
void engine_ui_log_append(const char *line) {
    if (!line)
        return;
    /* Ensure mutex is initialized (safe for early single-threaded logging
     * and concurrent calls via atomic_exchange once-init pattern). */
    engine_ui_log_init();
    engine_mutex_lock(&g_log_mutex);
    snprintf(g_log_ring[g_log_head], LOG_LINE_MAX, "%s", line);
    g_log_head = (g_log_head + 1) % LOG_RING_SIZE;
    if (g_log_count < LOG_RING_SIZE)
        g_log_count++;
    engine_mutex_unlock(&g_log_mutex);
}

/* Append a printf-formatted fragment at *pos within a bufsz buffer, never
 * advancing *pos past bufsz. snprintf returns the length it WOULD have written,
 * so `pos += snprintf(...)` runs pos past the end on truncation and the next
 * call computes a wrapped (huge) remaining size and writes out of bounds. This
 * clamps: on truncation *pos is pinned at bufsz and further appends are no-ops. */
static void http_appendf(char *buf, size_t bufsz, int *pos, const char *fmt, ...)
    __attribute__((format(printf, 4, 5)));
static void http_appendf(char *buf, size_t bufsz, int *pos, const char *fmt, ...) {
    if (*pos < 0) {
        return;
    }
    if ((size_t)*pos >= bufsz) {
        *pos = (int)bufsz;
        return;
    }
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf + *pos, bufsz - (size_t)*pos, fmt, ap);
    va_end(ap);
    if (n < 0) {
        return;
    }
    if ((size_t)n >= bufsz - (size_t)*pos) {
        *pos = (int)bufsz;
    } else {
        *pos += n;
    }
}

/* GET /api/logs?lines=N — returns last N log lines */
static void handle_logs(engine_http_conn_t *c, const engine_http_req_t *req) {
    char lines_str[16] = {0};
    int max_lines = 100;
    if (engine_http_query_param(req->query, "lines", lines_str, (int)sizeof(lines_str))) {
        int v = atoi(lines_str);
        if (v > 0 && v <= LOG_RING_SIZE)
            max_lines = v;
    }

    engine_mutex_lock(&g_log_mutex);
    int count = g_log_count < max_lines ? g_log_count : max_lines;
    int start = (g_log_head - count + LOG_RING_SIZE) % LOG_RING_SIZE;
    int total = g_log_count;

    /* Copy lines under lock.
     *
     * JSON escaping expands '"', '\\' and '\n' to two bytes each, so an
     * line made mostly of those serialises to roughly twice its stored length.
     * The previous budget of LOG_LINE_MAX + 10 per line under-counted that by
     * half. Ring contents come from indexer stderr, which is not escaped on
     * ingest and can legitimately contain both doubling characters — a POSIX
     * filename may.
     *
     * Budget the escaped worst case, and clamp the framing writes below anyway
     * so the size calculation is not the only thing keeping pos in range. */
    size_t buf_size = (size_t)count * (2 * LOG_LINE_MAX + 8) + 64;
    char *buf = malloc(buf_size);
    if (!buf) {
        engine_mutex_unlock(&g_log_mutex);
        engine_http_replyf(c, 500, g_cors, "oom");
        return;
    }

    int pos = 0;
    http_appendf(buf, buf_size, &pos, "{\"lines\":[");
    for (int i = 0; i < count; i++) {
        int idx = (start + i) % LOG_RING_SIZE;
        if (i > 0)
            http_appendf(buf, buf_size, &pos, ",");
        /* Escape quotes in log lines */
        http_appendf(buf, buf_size, &pos, "\"");
        for (int j = 0; g_log_ring[idx][j] && (size_t)pos < buf_size - 10; j++) {
            char ch = g_log_ring[idx][j];
            if (ch == '"') {
                buf[pos++] = '\\';
                buf[pos++] = '"';
            } else if (ch == '\\') {
                buf[pos++] = '\\';
                buf[pos++] = '\\';
            } else if (ch == '\n') {
                buf[pos++] = '\\';
                buf[pos++] = 'n';
            } else {
                buf[pos++] = ch;
            }
        }
        http_appendf(buf, buf_size, &pos, "\"");
    }
    engine_mutex_unlock(&g_log_mutex);
    http_appendf(buf, buf_size, &pos, "],\"total\":%d}", total);

    /* http_appendf pins pos to buf_size on truncation and then writes nothing,
     * so a saturated buffer would reach the "%s" reply with no terminator in
     * range. Terminate explicitly. */
    if ((size_t)pos >= buf_size) {
        pos = (int)buf_size - 1;
    }
    buf[pos] = '\0';

    engine_http_replyf(c, 200, g_cors_json, "%s", buf);
    free(buf);
}

/* ── Background indexing ──────────────────────────────────────── */

static char g_binary_path[1024] = {0};

static bool copy_path(char *out, size_t outsz, const char *path) {
    if (!out || outsz == 0 || !path || !path[0]) {
        return false;
    }
    int n = snprintf(out, outsz, "%s", path);
    return n > 0 && (size_t)n < outsz;
}

#ifndef _WIN32
static bool is_executable_file(const char *path) {
    struct stat st;
    return path && stat(path, &st) == 0 && S_ISREG(st.st_mode) && access(path, X_OK) == 0;
}

static bool resolve_from_path(const char *name, char *out, size_t outsz) {
    const char *path = getenv("PATH");
    if (!name || !name[0] || strchr(name, '/') || !path || !path[0]) {
        return false;
    }

    const char *cur = path;
    while (*cur) {
        const char *colon = strchr(cur, ':');
        size_t dir_len = colon ? (size_t)(colon - cur) : strlen(cur);
        if (dir_len > 0 && dir_len < 900) {
            char candidate[1024];
            int n = snprintf(candidate, sizeof(candidate), "%.*s/%s", (int)dir_len, cur, name);
            if (n > 0 && (size_t)n < sizeof(candidate) && is_executable_file(candidate)) {
                return copy_path(out, outsz, candidate);
            }
        }
        if (!colon) {
            break;
        }
        cur = colon + 1;
    }
    return false;
}

static bool resolve_self_executable(char *out, size_t outsz) {
#if defined(__APPLE__)
    char buf[1024];
    uint32_t sz = sizeof(buf);
    if (_NSGetExecutablePath(buf, &sz) == 0 && buf[0]) {
        return copy_path(out, outsz, buf);
    }
    return false;
#else
    char buf[1024];
    ssize_t len = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (len > 0) {
        buf[len] = '\0';
        return copy_path(out, outsz, buf);
    }
    return false;
#endif
}
#else
static bool resolve_self_executable(char *out, size_t outsz) {
    char *utf8 = engine_module_path_utf8();
    if (!utf8) {
        return false;
    }
    bool ok = copy_path(out, outsz, utf8);
    free(utf8);
    return ok;
}
#endif

bool engine_http_server_resolve_binary_path(const char *argv0, char *out, size_t outsz) {
    if (!out || outsz == 0) {
        return false;
    }
    out[0] = '\0';

#ifndef _WIN32
    if (argv0 && strchr(argv0, '/') && is_executable_file(argv0)) {
        return copy_path(out, outsz, argv0);
    }
    if (resolve_from_path(argv0, out, outsz)) {
        return true;
    }
#else
    if (argv0 && argv0[0]) {
        /* GetFileAttributesA reads argv0 through the ANSI code page and fails on
         * non-ASCII install paths, forcing a fallback that can mangle the path;
         * check wide so a valid non-ASCII argv0 is used verbatim. */
        wchar_t *wargv0 = engine_utf8_to_wide(argv0);
        DWORD attrs = wargv0 ? GetFileAttributesW(wargv0) : INVALID_FILE_ATTRIBUTES;
        free(wargv0);
        if (attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY)) {
            return copy_path(out, outsz, argv0);
        }
    }
#endif

    if (resolve_self_executable(out, outsz)) {
        return true;
    }
    return copy_path(out, outsz, argv0);
}

void engine_http_server_set_binary_path(const char *path) {
    if (path) {
        if (!engine_http_server_resolve_binary_path(path, g_binary_path, sizeof(g_binary_path))) {
            g_binary_path[0] = '\0';
        }
    }
    engine_ui_assets_set_binary_path(g_binary_path);
}

/* Execute through the daemon's shared job registry. The thread is retained in
 * its slot and joined before reuse/free; no detached operation can outlive the
 * daemon application that owns its callback context. */
static void *index_thread_fn(void *arg) {
    index_job_t *job = arg;
    engine_log_info("ui.index.start", "path", job->root_path);
    engine_http_server_t *server = job->server;
    int result = server && server->index_executor
                     ? server->index_executor(server->index_executor_context, job->root_path,
                                              job->project_name)
                     : -1;
    if (result != 0) {
        snprintf(job->error_msg, sizeof(job->error_msg), "daemon index operation failed");
        atomic_store(&job->status, 3);
    } else {
        atomic_store(&job->status, 2);
    }
    engine_log_info("ui.index.done", "path", job->root_path, "rc", result == 0 ? "ok" : "err");
    atomic_store_explicit(&job->completed, 1, memory_order_release);
    return NULL;
}

/* POST /api/index — body: {"root_path": "/abs/path", "project_name": "..."} */
static void handle_index_start(engine_http_server_t *server, engine_http_conn_t *c,
                               const engine_http_req_t *req) {
    if (!server || !server->index_executor) {
        engine_http_replyf(c, 503, g_cors_json,
                        "{\"error\":\"daemon index coordinator unavailable\"}");
        return;
    }
    if (req->body_len == 0 || req->body_len > 4096) {
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"invalid body\"}");
        return;
    }

    yyjson_doc *doc = yyjson_read(req->body, req->body_len, 0);
    if (!doc) {
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"invalid json\"}");
        return;
    }
    yyjson_val *root = yyjson_doc_get_root(doc);
    yyjson_val *v_path = yyjson_obj_get(root, "root_path");
    if (!v_path || !yyjson_is_str(v_path)) {
        yyjson_doc_free(doc);
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"missing root_path\"}");
        return;
    }
    const char *rpath = yyjson_get_str(v_path);
    yyjson_val *v_project_name = yyjson_obj_get(root, "project_name");
    const char *project_name = yyjson_is_str(v_project_name) ? yyjson_get_str(v_project_name) : "";

    /* Check path exists */
    if (!engine_is_dir(rpath)) {
        yyjson_doc_free(doc);
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"directory not found\"}");
        return;
    }

    /* Same workspace boundary the MCP indexing tool applies, through the same
     * function. This route used to check only that the path was a directory, so
     * it accepted roots the MCP path refused — an operator's boundary held on one
     * entry point and not the other. Canonicalize first: the policy is defined
     * over resolved paths, and a symlink would otherwise launder the verdict. */
    char canonical_root[4096];
    char boundary_err[1024];
    if (!engine_canonical_path(rpath, canonical_root, sizeof(canonical_root))) {
        yyjson_doc_free(doc);
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"cannot resolve root_path\"}");
        return;
    }
    if (!engine_workspace_root_allowed(canonical_root, engine_workspace_home_dir(),
                                    engine_workspace_cache_dir(), getenv("ENGINE_ALLOWED_ROOT"),
                                    boundary_err, sizeof(boundary_err))) {
        yyjson_doc_free(doc);
        char escaped[1024];
        engine_json_escape(escaped, (int)sizeof(escaped), boundary_err);
        engine_http_replyf(c, 403, g_cors_json, "{\"error\":\"%s\"}", escaped);
        return;
    }

    /* Find free job slot */
    int slot = -1;
    for (int i = 0; i < MAX_INDEX_JOBS; i++) {
        int st = atomic_load(&server->index_jobs[i].status);
        bool reusable =
            !server->index_jobs[i].thread_started ||
            atomic_load_explicit(&server->index_jobs[i].completed, memory_order_acquire);
        if ((st == 0 || st == 2 || st == 3) && reusable) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        yyjson_doc_free(doc);
        engine_http_replyf(c, 429, g_cors_json, "{\"error\":\"all index slots busy\"}");
        return;
    }

    index_job_t *job = &server->index_jobs[slot];
    if (job->thread_started) {
        if (engine_thread_join(&job->thread) != 0) {
            engine_http_replyf(c, 503, g_cors_json, "{\"error\":\"index worker unavailable\"}");
            return;
        }
        job->thread_started = false;
    }
    job->server = server;
    snprintf(job->root_path, sizeof(job->root_path), "%s", rpath);
    snprintf(job->project_name, sizeof(job->project_name), "%s", project_name);
    job->error_msg[0] = '\0';
    atomic_store(&job->status, 1);
    atomic_store_explicit(&job->completed, 0, memory_order_release);
    yyjson_doc_free(doc);

    /* Spawn background thread */
    if (engine_thread_create(&job->thread, 0, index_thread_fn, job) != 0) {
        atomic_store(&job->status, 3);
        atomic_store_explicit(&job->completed, 1, memory_order_release);
        snprintf(job->error_msg, sizeof(job->error_msg), "thread creation failed");
        engine_http_replyf(c, 500, g_cors_json, "{\"error\":\"thread creation failed\"}");
        return;
    }
    job->thread_started = true;

    engine_http_replyf(c, 202, g_cors_json, "{\"status\":\"indexing\",\"slot\":%d,\"path\":\"%s\"}",
                    slot, job->root_path);
}

/* GET /api/index-status — returns status of all index jobs */
static void handle_index_status(engine_http_server_t *server, engine_http_conn_t *c) {
    char buf[2048] = "[";
    int pos = 1;
    for (int i = 0; i < MAX_INDEX_JOBS; i++) {
        int st = atomic_load(&server->index_jobs[i].status);
        if (st == 0)
            continue;
        if (pos > 1)
            http_appendf(buf, sizeof(buf), &pos, ",");
        const char *ss = st == 1 ? "indexing" : st == 2 ? "done" : "error";
        /* root_path comes from POST /api/index and is up to 1023 bytes, so four
         * occupied slots exceed this buffer. http_appendf pins pos to
         * sizeof(buf) on truncation, so the separator and the close have to go
         * through it as well rather than indexing raw. Both fields are free-form,
         * so escape them — a quote in a path would otherwise end its JSON string
         * early. */
        /* Escaping can double each byte: root_path is 1024, error_msg 256. */
        char esc_path[2048];
        char esc_error[512];
        engine_json_escape(esc_path, (int)sizeof(esc_path), server->index_jobs[i].root_path);
        engine_json_escape(esc_error, (int)sizeof(esc_error),
                        st == 3 ? server->index_jobs[i].error_msg : "");
        http_appendf(buf, sizeof(buf), &pos,
                     "{\"slot\":%d,\"status\":\"%s\",\"path\":\"%s\",\"error\":\"%s\"}", i, ss,
                     esc_path, esc_error);
    }
    http_appendf(buf, sizeof(buf), &pos, "]");
    if ((size_t)pos >= sizeof(buf)) {
        pos = (int)sizeof(buf) - 1;
    }
    buf[pos] = '\0';
    engine_http_replyf(c, 200, g_cors_json, "%s", buf);
}

static void unwatch_project(engine_http_server_t *srv, const char *name) {
    if (srv && srv->watcher) {
        engine_watcher_unwatch(srv->watcher, name);
    }
}

/* DELETE /api/project?name=X — deletes the .db file */
static void handle_delete_project(engine_http_server_t *srv, engine_http_conn_t *c,
                                  const engine_http_req_t *req) {
    char name[256] = {0};
    if (!engine_http_query_param(req->query, "name", name, (int)sizeof(name)) || name[0] == '\0') {
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"missing name\"}");
        return;
    }

    char db_path[1024];
    db_path_for_project(name, db_path, sizeof(db_path));
    if (db_path[0] == '\0') {
        engine_http_replyf(c, 404, g_cors_json, "{\"error\":\"project not found\"}");
        return;
    }

    if (srv->mutation_begin && !srv->mutation_begin(srv->mutation_context, name)) {
        engine_http_replyf(c, 423, g_cors_json,
                        "{\"error\":\"project is busy; retry after indexing\"}");
        return;
    }
    bool mutation_held = srv->mutation_begin != NULL;

    if (unlink(db_path) != 0) {
        if (errno == ENOENT) {
            unwatch_project(srv, name);
            if (mutation_held) {
                srv->mutation_end(srv->mutation_context, name);
            }
            engine_http_replyf(c, 404, g_cors_json, "{\"error\":\"project not found\"}");
            return;
        }
        if (mutation_held) {
            srv->mutation_end(srv->mutation_context, name);
        }
        engine_http_replyf(c, 500, g_cors_json, "{\"error\":\"failed to delete\"}");
        return;
    }

    /* Also remove WAL and SHM files if they exist */
    char wal_path[1040], shm_path[1040];
    snprintf(wal_path, sizeof(wal_path), "%s-wal", db_path);
    snprintf(shm_path, sizeof(shm_path), "%s-shm", db_path);
    (void)unlink(wal_path);
    (void)unlink(shm_path);

    unwatch_project(srv, name);
    engine_log_info("ui.project.deleted", "name", name);
    if (mutation_held) {
        srv->mutation_end(srv->mutation_context, name);
    }
    engine_http_replyf(c, 200, g_cors_json, "{\"deleted\":true}");
}

/* GET /api/project-health?name=X — checks db integrity */
static void handle_project_health(engine_http_conn_t *c, const engine_http_req_t *req) {
    char name[256] = {0};
    if (!engine_http_query_param(req->query, "name", name, (int)sizeof(name)) || name[0] == '\0') {
        engine_http_replyf(c, 400, g_cors_json, "{\"error\":\"missing name\"}");
        return;
    }

    char db_path[1024];
    db_path_for_project(name, db_path, sizeof(db_path));

    if (!engine_file_exists(db_path)) {
        engine_http_replyf(c, 200, g_cors_json, "{\"status\":\"missing\"}");
        return;
    }

    engine_store_t *store = engine_store_open_path_query(db_path);
    if (!store) {
        engine_http_replyf(c, 200, g_cors_json, "{\"status\":\"corrupt\",\"reason\":\"cannot open\"}");
        return;
    }

    int node_count = engine_store_count_nodes(store, name);
    int edge_count = engine_store_count_edges(store, name);
    engine_store_close(store);

    int64_t size = engine_file_size(db_path);

    engine_http_replyf(c, 200, g_cors_json,
                    "{\"status\":\"healthy\",\"nodes\":%d,\"edges\":%d,\"size_bytes\":%lld}",
                    node_count, edge_count, (long long)size);
}

/* ── Handle JSON-RPC request ──────────────────────────────────── */

static yyjson_val *json_unique_member(yyjson_val *object, const char *name) {
    if (!yyjson_is_obj(object))
        return NULL;
    yyjson_val *found = NULL;
    size_t index, maximum;
    yyjson_val *key, *value;
    yyjson_obj_foreach(object, index, maximum, key, value) {
        if (strcmp(yyjson_get_str(key), name) == 0) {
            if (found)
                return NULL;
            found = value;
        }
    }
    return found;
}

static bool rpc_is_allowed_for_ui(const char *body, size_t body_len) {
    yyjson_doc *document = yyjson_read(body, body_len, 0);
    if (!document)
        return false;
    yyjson_val *root = yyjson_doc_get_root(document);
    yyjson_val *method = json_unique_member(root, "method");
    yyjson_val *params = json_unique_member(root, "params");
    yyjson_val *name = json_unique_member(params, "name");
    const char *method_text = yyjson_is_str(method) ? yyjson_get_str(method) : NULL;
    const char *name_text = yyjson_is_str(name) ? yyjson_get_str(name) : NULL;
    bool allowed =
        method_text && strcmp(method_text, "tools/call") == 0 && name_text &&
        (strcmp(name_text, "list_projects") == 0 || strcmp(name_text, "get_code_snippet") == 0);
    yyjson_doc_free(document);
    return allowed;
}

static void handle_rpc(engine_http_conn_t *c, const engine_http_req_t *req, engine_mcp_server_t *mcp) {
    if (req->body_len == 0 || req->body_len > MAX_BODY_SIZE || !req->body) {
        engine_http_replyf(c, 400, g_cors_json,
                        "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32600,"
                        "\"message\":\"invalid request size\"},\"id\":null}");
        return;
    }

    if (!rpc_is_allowed_for_ui(req->body, req->body_len)) {
        engine_http_replyf(c, 403, g_cors_json,
                        "{\"jsonrpc\":\"2.0\",\"error\":{\"code\":-32601,"
                        "\"message\":\"UI RPC method is not allowed\"},\"id\":null}");
        return;
    }

    /* req->body is NUL-terminated by the transport */
    char *response = engine_mcp_server_handle(mcp, req->body);

    if (response) {
        engine_http_replyf(c, 200, g_cors_json, "%s", response);
        free(response);
    } else {
        engine_http_replyf(c, 204, g_cors, "%s", "");
    }
}

/* ── Request dispatch ─────────────────────────────────────────── */

/* True when the Host header names the loopback interface and exact port the
 * server binds to. Anything else means the request reached us under a
 * name that is not loopback — a rebinding DNS host or a proxy pointed at the
 * local port — which is the DNS-rebinding / cross-site vector against a
 * localhost-only service. */
static bool host_is_this_server(const char *host, int port) {
    char expected[128];
    int length = snprintf(expected, sizeof(expected), "127.0.0.1:%d", port);
    if (length > 0 && (size_t)length < sizeof(expected) && strcmp(host, expected) == 0)
        return true;
    length = snprintf(expected, sizeof(expected), "localhost:%d", port);
    return length > 0 && (size_t)length < sizeof(expected) && strcmp(host, expected) == 0;
}

static bool route_is_protected(const char *path) {
    return strcmp(path, "/api") == 0 || strncmp(path, "/api/", 5) == 0 || strcmp(path, "/rpc") == 0;
}

static bool content_type_is_json(const char *content_type) {
    static const char json_type[] = "application/json";
    size_t type_length = sizeof(json_type) - 1;
    if (strlen(content_type) < type_length)
        return false;
    for (size_t i = 0; i < type_length; i++) {
        if (tolower((unsigned char)content_type[i]) != json_type[i])
            return false;
    }
    const char *suffix = content_type + type_length;
    while (*suffix == ' ' || *suffix == '\t')
        suffix++;
    return *suffix == '\0' || *suffix == ';';
}

static int readiness_hex_nibble(char value) {
    if (value >= '0' && value <= '9') {
        return value - '0';
    }
    if (value >= 'a' && value <= 'f') {
        return value - 'a' + 10;
    }
    return -1;
}

static bool readiness_hex_decode(const char *hex, uint8_t out[ENGINE_SHA256_DIGEST_LEN]) {
    if (!hex || strlen(hex) != ENGINE_SHA256_HEX_LEN) {
        return false;
    }
    for (size_t i = 0; i < ENGINE_SHA256_DIGEST_LEN; i++) {
        int high = readiness_hex_nibble(hex[i * 2U]);
        int low = readiness_hex_nibble(hex[i * 2U + 1U]);
        if (high < 0 || low < 0) {
            return false;
        }
        out[i] = (uint8_t)((high << 4) | low);
    }
    return true;
}

static void readiness_hex_encode(const uint8_t bytes[ENGINE_SHA256_DIGEST_LEN],
                                 char out[ENGINE_SHA256_HEX_LEN + 1U]) {
    static const char hex[] = "0123456789abcdef";
    for (size_t i = 0; i < ENGINE_SHA256_DIGEST_LEN; i++) {
        out[i * 2U] = hex[bytes[i] >> 4];
        out[i * 2U + 1U] = hex[bytes[i] & 0x0fU];
    }
    out[ENGINE_SHA256_HEX_LEN] = '\0';
}

static void handle_ui_readiness(engine_http_server_t *srv, engine_http_conn_t *c,
                                const engine_http_req_t *req) {
    if (!srv->readiness_secret_set) {
        engine_http_replyf(c, 503, "Cache-Control: no-store\r\n", "%s", "readiness proof unavailable");
        return;
    }
    char challenge_hex[ENGINE_SHA256_HEX_LEN + 1U];
    uint8_t challenge[ENGINE_SHA256_DIGEST_LEN];
    static const char prefix[] = "challenge=";
    if (strncmp(req->query, prefix, sizeof(prefix) - 1U) != 0 ||
        strlen(req->query) != sizeof(prefix) - 1U + ENGINE_SHA256_HEX_LEN) {
        engine_http_replyf(c, 400, "Cache-Control: no-store\r\n", "%s", "invalid challenge");
        return;
    }
    memcpy(challenge_hex, req->query + sizeof(prefix) - 1U, ENGINE_SHA256_HEX_LEN);
    challenge_hex[ENGINE_SHA256_HEX_LEN] = '\0';
    if (!readiness_hex_decode(challenge_hex, challenge)) {
        engine_secure_zero(challenge, sizeof(challenge));
        engine_http_replyf(c, 400, "Cache-Control: no-store\r\n", "%s", "invalid challenge");
        return;
    }
    uint8_t proof[ENGINE_SHA256_DIGEST_LEN];
    char proof_hex[ENGINE_SHA256_HEX_LEN + 1U];
    engine_hmac_sha256(srv->readiness_secret, sizeof(srv->readiness_secret), challenge,
                    sizeof(challenge), proof);
    readiness_hex_encode(proof, proof_hex);
    engine_http_replyf(c, 200,
                    "Content-Type: text/plain; charset=utf-8\r\n"
                    "Cache-Control: no-store\r\n"
                    "X-Content-Type-Options: nosniff\r\n",
                    "%s", proof_hex);
    engine_secure_zero(challenge, sizeof(challenge));
    engine_secure_zero(proof, sizeof(proof));
    engine_secure_zero(proof_hex, sizeof(proof_hex));
}

static bool request_passes_http_security(engine_http_server_t *srv, engine_http_conn_t *c,
                                         const engine_http_req_t *req) {
    if (req->http_minor == 1 && req->host[0] == '\0') {
        engine_http_replyf(c, 400, "", "%s", "{\"error\":\"Host header required\"}");
        return false;
    }
    if (req->host[0] != '\0' && !host_is_this_server(req->host, srv->port)) {
        engine_http_replyf(c, 403, "", "%s", "{\"error\":\"forbidden host\"}");
        return false;
    }
    if (req->origin[0] != '\0' &&
        (req->host[0] == '\0' || !origin_is_same_server(req->origin, srv->port) ||
         !origin_matches_host(req->origin, req->host, srv->port))) {
        engine_http_replyf(c, 403, "", "%s", "{\"error\":\"forbidden origin\"}");
        return false;
    }
    update_cors(req, srv->port);
    bool is_post = strcmp(req->method, "POST") == 0;
    if (route_is_protected(req->path) && is_post && !content_type_is_json(req->content_type)) {
        engine_http_replyf(c, 415, g_cors_json, "%s", "{\"error\":\"application/json required\"}");
        return false;
    }
    return true;
}

static void dispatch_request(engine_http_server_t *srv, engine_http_conn_t *c,
                             const engine_http_req_t *req) {
    if (!request_passes_http_security(srv, c, req))
        return;

    bool is_get = strcmp(req->method, "GET") == 0;
    bool is_post = strcmp(req->method, "POST") == 0;
    bool is_delete = strcmp(req->method, "DELETE") == 0;

    /* OPTIONS preflight for CORS */
    if (strcmp(req->method, "OPTIONS") == 0) {
        engine_http_replyf(c, 204, g_cors, "%s", "");
        return;
    }

    /* Private-generation proof used only by `daemon start --open`. The
     * challenge is public; the HMAC key exists only in this daemon's
     * authenticated application and HTTP server instances. */
    if (is_get && strcmp(req->path, "/__engine/ui-readiness") == 0) {
        handle_ui_readiness(srv, c, req);
        return;
    }

    /* POST /rpc → JSON-RPC dispatch (reuses existing MCP tools) */
    if (is_post && engine_http_path_match(req->path, "/rpc")) {
        handle_rpc(c, req, srv->mcp);
        return;
    }



    /* POST /api/index → start background indexing */
    if (is_post && engine_http_path_match(req->path, "/api/index")) {
        handle_index_start(srv, c, req);
        return;
    }

    /* GET /api/index-status → check indexing progress */
    if (is_get && engine_http_path_match(req->path, "/api/index-status")) {
        handle_index_status(srv, c);
        return;
    }


    /* DELETE /api/project → delete a project's .db file */
    if (is_delete && engine_http_path_match(req->path, "/api/project*")) {
        handle_delete_project(srv, c, req);
        return;
    }




    /* GET /api/project-health → check db integrity */
    if (is_get && engine_http_path_match(req->path, "/api/project-health*")) {
        handle_project_health(c, req);
        return;
    }


    /* GET /api/logs → recent log lines */
    if (is_get && engine_http_path_match(req->path, "/api/logs*")) {
        handle_logs(c, req);
        return;
    }

    /* GET / → index.html (no-cache so browser always gets latest) */
    if (engine_http_path_match(req->path, "/")) {
        const engine_ui_asset_t *f = engine_ui_asset_lookup("/index.html");
        if (f) {
            char html_hdrs[1024];
            snprintf(html_hdrs, sizeof(html_hdrs),
                     "%sContent-Type: text/html; charset=utf-8\r\nCache-Control: no-cache\r\n"
                     "X-Content-Type-Options: nosniff\r\n" ENGINE_UI_CSP,
                     g_cors);
            engine_http_reply_buf(c, 200, html_hdrs, f->data, f->size);
            return;
        }
        engine_http_replyf(c, 503, "Cache-Control: no-store\r\nRetry-After: 1\r\n",
                        "frontend assets are not ready");
        return;
    }

    /* GET /assets/... → exact lookup in the immutable verified pack. */
    if (serve_frontend_asset(c, req->path))
        return;

    engine_http_replyf(c, 404, g_cors, "not found");
}

/* ── Public API ───────────────────────────────────────────────── */

static char *http_read_only_index_rejected(void *context, const char *repo_path,
                                           const char *args_json) {
    (void)context;
    (void)repo_path;
    (void)args_json;
    return engine_mcp_text_result("UI RPC indexing is disabled; use the coordinated /api/index route",
                               true);
}

engine_http_server_t *engine_http_server_new(int port) {
    engine_http_server_t *srv = calloc(1, sizeof(*srv));
    if (!srv)
        return NULL;

    srv->port = port;
    atomic_init(&srv->stop_flag, 0);
    atomic_init(&srv->run_state, HTTP_RUN_IDLE);

    /* Create a dedicated MCP server for HTTP (own SQLite connection) */
    srv->mcp = engine_mcp_server_new(NULL);
    if (!srv->mcp) {
        engine_log_error("ui.http.mcp_fail", "reason", "cannot create MCP instance");
        free(srv);
        return NULL;
    }
    engine_mcp_server_set_background_tasks(srv->mcp, false);
    engine_mcp_server_set_index_executor(srv->mcp, http_read_only_index_rejected, srv);

    /* Bind to localhost only (httpd refuses anything else by construction) */
    srv->listener = engine_httpd_listen(port);
    if (!srv->listener) {
        char port_str[16];
        snprintf(port_str, sizeof(port_str), "%d", port);
        engine_log_warn("ui.unavailable", "port", port_str, "reason", "in_use", "hint",
                     "use --port=N to override");
        engine_mcp_server_free(srv->mcp);
        free(srv);
        return NULL;
    }

    srv->port = engine_httpd_port(srv->listener);
    srv->listener_ok = true;

    char port_str[16];
    snprintf(port_str, sizeof(port_str), "%d", srv->port);
    char url[64];
    snprintf(url, sizeof(url), "http://127.0.0.1:%d", srv->port);
    engine_log_info("ui.serving", "url", url, "port", port_str);

    return srv;
}

bool engine_http_server_free(engine_http_server_t *srv) {
    if (!srv)
        return true;
    int run_state = atomic_load_explicit(&srv->run_state, memory_order_acquire);
    if (run_state == HTTP_RUN_SCHEDULED || run_state == HTTP_RUN_RUNNING)
        return false;
    for (int i = 0; i < MAX_INDEX_JOBS; i++) {
        if (srv->index_jobs[i].thread_started) {
            if (!atomic_load_explicit(&srv->index_jobs[i].completed, memory_order_acquire))
                return false;
            if (engine_thread_join(&srv->index_jobs[i].thread) != 0)
                return false;
            srv->index_jobs[i].thread_started = false;
        }
    }
    if (!engine_httpd_close(srv->listener))
        return false;
    engine_mcp_server_free(srv->mcp);
    engine_secure_zero(srv->readiness_secret, sizeof(srv->readiness_secret));
    free(srv);
    return true;
}

void engine_http_server_stop(engine_http_server_t *srv) {
    if (srv) {
        atomic_store(&srv->stop_flag, 1);
        engine_httpd_interrupt(srv->listener);
    }
}

bool engine_http_server_schedule_run(engine_http_server_t *srv) {
    if (!srv || !srv->listener_ok)
        return false;
    int expected = HTTP_RUN_IDLE;
    return atomic_compare_exchange_strong_explicit(&srv->run_state, &expected, HTTP_RUN_SCHEDULED,
                                                   memory_order_acq_rel, memory_order_acquire);
}

bool engine_http_server_cancel_scheduled_run(engine_http_server_t *srv) {
    if (!srv)
        return false;
    int expected = HTTP_RUN_SCHEDULED;
    return atomic_compare_exchange_strong_explicit(&srv->run_state, &expected, HTTP_RUN_IDLE,
                                                   memory_order_acq_rel, memory_order_acquire);
}

void engine_http_server_run(engine_http_server_t *srv) {
    if (!srv)
        return;
    int expected = HTTP_RUN_SCHEDULED;
    if (!atomic_compare_exchange_strong_explicit(&srv->run_state, &expected, HTTP_RUN_RUNNING,
                                                 memory_order_acq_rel, memory_order_acquire))
        return;
    if (!srv->listener_ok) {
        atomic_store_explicit(&srv->run_state, HTTP_RUN_COMPLETED, memory_order_release);
        return;
    }

    while (!atomic_load(&srv->stop_flag)) {
        engine_http_conn_t *conn = engine_httpd_accept(srv->listener, 200);
        if (!conn)
            continue; /* timeout — re-check stop flag */

        uint64_t request_start_ms = engine_now_ms();
        engine_http_req_t req;
        int rc = engine_httpd_read_request(conn, &req);
        if (rc == 0) {
            if (atomic_load(&srv->stop_flag)) {
                engine_http_req_free(&req);
                engine_httpd_conn_close(conn);
                break;
            }
            dispatch_request(srv, conn, &req);
            engine_log_http_request("graph_ui", req.method, req.path, engine_http_conn_status(conn),
                                 (int64_t)(engine_now_ms() - request_start_ms), req.body_len,
                                 engine_http_conn_response_bytes(conn));
            engine_http_req_free(&req);
        } else if (rc > 0) {
            /* Parse/transport error with a known HTTP status (400/408/411/413/431).
             * No CORS reflection here — the request was never parsed. */
            engine_http_replyf(conn, rc, "", "bad request");
            engine_log_http_request("graph_ui", "", "", engine_http_conn_status(conn),
                                 (int64_t)(engine_now_ms() - request_start_ms), 0,
                                 engine_http_conn_response_bytes(conn));
        }
        engine_httpd_conn_close(conn);
    }
    atomic_store_explicit(&srv->run_state, HTTP_RUN_COMPLETED, memory_order_release);
}

engine_httpd_activity_t engine_http_server_activity_for_test(engine_http_server_t *srv) {
    return srv ? engine_httpd_activity_for_test(srv->listener) : ENGINE_HTTPD_ACTIVITY_IDLE;
}

bool engine_http_server_is_running(const engine_http_server_t *srv) {
    return srv && srv->listener_ok;
}

int engine_http_server_port(const engine_http_server_t *srv) {
    return (srv && srv->listener_ok) ? srv->port : -1;
}

void engine_http_server_set_recv_deadline_ms(engine_http_server_t *srv, int ms) {
    if (srv && srv->listener_ok) {
        engine_httpd_set_recv_deadline_ms(srv->listener, ms);
    }
}

void engine_http_server_set_watcher(engine_http_server_t *srv, struct engine_watcher *watcher) {
    if (srv) {
        srv->watcher = watcher;
    }
}

void engine_http_server_set_index_executor(engine_http_server_t *srv, engine_http_index_executor_fn executor,
                                        void *context) {
    if (srv) {
        srv->index_executor = executor;
        srv->index_executor_context = context;
    }
}

void engine_http_server_set_project_mutation_guard(engine_http_server_t *srv,
                                                engine_http_project_mutation_begin_fn begin,
                                                engine_http_project_mutation_end_fn end,
                                                void *context) {
    if (!srv || ((begin == NULL) != (end == NULL))) {
        return;
    }
    srv->mutation_begin = begin;
    srv->mutation_end = end;
    srv->mutation_context = begin ? context : NULL;
    engine_mcp_server_set_project_mutation_guard(srv->mcp, begin, end, begin ? context : NULL);
    engine_mcp_server_set_project_mutation_try_guard(srv->mcp, begin);
}

void engine_http_server_set_readiness_secret(engine_http_server_t *srv,
                                          const uint8_t secret[ENGINE_SHA256_DIGEST_LEN]) {
    if (!srv || !secret ||
        atomic_load_explicit(&srv->run_state, memory_order_acquire) != HTTP_RUN_IDLE) {
        return;
    }
    memcpy(srv->readiness_secret, secret, sizeof(srv->readiness_secret));
    srv->readiness_secret_set = true;
}
