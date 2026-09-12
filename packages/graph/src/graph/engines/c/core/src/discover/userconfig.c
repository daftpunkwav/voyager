/*
 * userconfig.c — User-defined extension→language mappings.
 *
 * Reads extra_extensions from:
 *   Global:  $XDG_CONFIG_HOME/graph-engine/config.json
 *            (falls back to ~/.config/graph-engine/config.json)
 *   Project: {repo_root}/.graph-engine.json
 *
 * Project config wins over global. Unknown language values warn and are
 * skipped (fail-open). Missing files are silently ignored.
 */
#include "discover/userconfig.h"
#include "engine.h" /* EngineLanguage, ENGINE_LANG_* */
#include "foundation/constants.h"
#include "foundation/platform.h" /* engine_safe_getenv */
#include "foundation/compat_fs.h"
#include "foundation/sha256.h"

enum { MAX_CONFIG_SIZE = 65536 };
#include "foundation/log.h"

#include <yyjson/yyjson.h>

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── Process-global user config pointer ──────────────────────────── */

static const engine_userconfig_t *g_userconfig = NULL;

static void userconfig_source_digest(const char *state, const void *bytes, size_t len,
                                     char out[ENGINE_SHA256_HEX_LEN + 1]) {
    static const char domain[] = "engine-userconfig-source-v1";
    engine_sha256_ctx sha;
    engine_sha256_init(&sha);
    engine_sha256_update(&sha, domain, sizeof(domain));
    engine_sha256_update(&sha, state, strlen(state) + 1);
    if (bytes && len > 0) {
        engine_sha256_update(&sha, bytes, len);
    }
    uint8_t digest[ENGINE_SHA256_DIGEST_LEN];
    engine_sha256_final(&sha, digest);
    static const char hex[] = "0123456789abcdef";
    for (int i = 0; i < ENGINE_SHA256_DIGEST_LEN; i++) {
        out[i * 2] = hex[digest[i] >> 4];
        out[i * 2 + 1] = hex[digest[i] & 0x0f];
    }
    out[ENGINE_SHA256_HEX_LEN] = '\0';
}

void engine_set_user_lang_config(const engine_userconfig_t *cfg) {
    g_userconfig = cfg;
}

const engine_userconfig_t *engine_get_user_lang_config(void) {
    return g_userconfig;
}

/* ── Language name → enum table ──────────────────────────────────── */

/*
 * Reverse-mapping from lowercase language name strings to EngineLanguage.
 * Covers all names exposed by engine_language_name() plus common aliases.
 */
typedef struct {
    const char *name; /* lowercase */
    EngineLanguage lang;
} lang_name_entry_t;

static const lang_name_entry_t LANG_NAME_TABLE[] = {
    {"go", ENGINE_LANG_GO},
    {"python", ENGINE_LANG_PYTHON},
    {"javascript", ENGINE_LANG_JAVASCRIPT},
    {"typescript", ENGINE_LANG_TYPESCRIPT},
    {"tsx", ENGINE_LANG_TSX},
    {"rust", ENGINE_LANG_RUST},
    {"java", ENGINE_LANG_JAVA},
    {"c++", ENGINE_LANG_CPP},
    {"cpp", ENGINE_LANG_CPP},
    {"c#", ENGINE_LANG_CSHARP},
    {"csharp", ENGINE_LANG_CSHARP},
    {"php", ENGINE_LANG_PHP},
    {"lua", ENGINE_LANG_LUA},
    {"scala", ENGINE_LANG_SCALA},
    {"kotlin", ENGINE_LANG_KOTLIN},
    {"ruby", ENGINE_LANG_RUBY},
    {"c", ENGINE_LANG_C},
    {"bash", ENGINE_LANG_BASH},
    {"sh", ENGINE_LANG_BASH},
    {"zig", ENGINE_LANG_ZIG},
    {"elixir", ENGINE_LANG_ELIXIR},
    {"haskell", ENGINE_LANG_HASKELL},
    {"objective-c", ENGINE_LANG_OBJC},
    {"objc", ENGINE_LANG_OBJC},
    {"swift", ENGINE_LANG_SWIFT},
    {"dart", ENGINE_LANG_DART},
    {"perl", ENGINE_LANG_PERL},
    {"groovy", ENGINE_LANG_GROOVY},
    {"erlang", ENGINE_LANG_ERLANG},
    {"r", ENGINE_LANG_R},
    {"html", ENGINE_LANG_HTML},
    {"css", ENGINE_LANG_CSS},
    {"scss", ENGINE_LANG_SCSS},
    {"yaml", ENGINE_LANG_YAML},
    {"toml", ENGINE_LANG_TOML},
    {"hcl", ENGINE_LANG_HCL},
    {"terraform", ENGINE_LANG_HCL},
    {"sql", ENGINE_LANG_SQL},
    {"dockerfile", ENGINE_LANG_DOCKERFILE},
    {"clojure", ENGINE_LANG_CLOJURE},
    {"julia", ENGINE_LANG_JULIA},
    {"json", ENGINE_LANG_JSON},
    {"xml", ENGINE_LANG_XML},
    {"markdown", ENGINE_LANG_MARKDOWN},
    {"makefile", ENGINE_LANG_MAKEFILE},
    {"cmake", ENGINE_LANG_CMAKE},
    {"protobuf", ENGINE_LANG_PROTOBUF},
    {"graphql", ENGINE_LANG_GRAPHQL},
    {"vue", ENGINE_LANG_VUE},
    {"svelte", ENGINE_LANG_SVELTE},
    {"ini", ENGINE_LANG_INI},
    {"matlab", ENGINE_LANG_MATLAB},
};

#define LANG_NAME_TABLE_SIZE (sizeof(LANG_NAME_TABLE) / sizeof(LANG_NAME_TABLE[0]))

/*
 * Parse a language string (case-insensitive) to a EngineLanguage enum.
 * Returns ENGINE_LANG_COUNT if the string is not recognized.
 */
static EngineLanguage lang_from_string(const char *s) {
    if (!s || !s[0]) {
        return ENGINE_LANG_COUNT;
    }

    /* Build a lowercase copy for comparison */
    char lower[ENGINE_SZ_64];
    size_t i;
    for (i = 0; i < sizeof(lower) - SKIP_ONE && s[i]; i++) {
        lower[i] = (char)tolower((unsigned char)s[i]);
    }
    lower[i] = '\0';

    for (size_t j = 0; j < LANG_NAME_TABLE_SIZE; j++) {
        if (strcmp(LANG_NAME_TABLE[j].name, lower) == 0) {
            return LANG_NAME_TABLE[j].lang;
        }
    }
    return ENGINE_LANG_COUNT;
}

/* ── Config directory helper ─────────────────────────────────────── */

/* engine_app_config_dir() is now in platform.c (cross-platform). */

/* ── JSON parsing ────────────────────────────────────────────────── */

/*
 * Parse extra_extensions from a yyjson object root.
 * Appends valid entries to *entries / *count (growing via realloc).
 * Project-level entries (from_project=true) are appended after global
 * entries so that a later dedup pass can prefer project values.
 *
 * Returns 0 on success, -1 on alloc failure.
 */
static int parse_extra_extensions(yyjson_val *root, engine_userext_t **entries, int *count,
                                  const char *source_label) {
    if (!yyjson_is_obj(root)) {
        engine_log_warn("userconfig.bad_root", "file", source_label);
        return 0;
    }

    yyjson_val *extra = yyjson_obj_get(root, "extra_extensions");
    if (!extra) {
        return 0; /* key absent — fine */
    }
    if (!yyjson_is_obj(extra)) {
        engine_log_warn("userconfig.bad_extra_extensions", "file", source_label);
        return 0;
    }

    yyjson_obj_iter iter;
    yyjson_obj_iter_init(extra, &iter);
    yyjson_val *key;
    while ((key = yyjson_obj_iter_next(&iter)) != NULL) {
        yyjson_val *val = yyjson_obj_iter_get_val(key);

        const char *ext_str = yyjson_get_str(key);
        const char *lang_str = yyjson_get_str(val);

        if (!ext_str || !lang_str) {
            engine_log_warn("userconfig.skip_non_string", "file", source_label);
            continue;
        }

        /* Extension must start with '.' */
        if (ext_str[0] != '.') {
            engine_log_warn("userconfig.skip_bad_ext", "file", source_label, "ext", ext_str);
            continue;
        }

        EngineLanguage lang = lang_from_string(lang_str);
        if (lang == ENGINE_LANG_COUNT) {
            engine_log_warn("userconfig.unknown_lang", "file", source_label, "lang", lang_str);
            continue; /* fail-open: skip unknown languages */
        }

        /* Grow the array */
        engine_userext_t *tmp = realloc(*entries, (size_t)(*count + SKIP_ONE) * sizeof(engine_userext_t));
        if (!tmp) {
            return ENGINE_NOT_FOUND;
        }
        *entries = tmp;

        char *ext_copy = strdup(ext_str);
        if (!ext_copy) {
            return ENGINE_NOT_FOUND;
        }

        (*entries)[*count].ext = ext_copy;
        (*entries)[*count].lang = lang;
        (*count)++;
    }
    return 0;
}

/*
 * Read a JSON file and parse extra_extensions from it.
 * Silently ignores missing files. Logs warnings for corrupt JSON.
 * Returns 0 on success (or absent file), -1 on alloc failure.
 */
static int load_config_file(const char *path, engine_userext_t **entries, int *count,
                            char source_sha256[ENGINE_SHA256_HEX_LEN + 1]) {
    userconfig_source_digest("missing-or-unreadable", NULL, 0, source_sha256);
    FILE *f = engine_fopen(path, "rb");
    if (!f) {
        return 0; /* file absent — silently ignore */
    }

    if (fseek(f, 0, SEEK_END) != 0) {
        (void)fclose(f);
        userconfig_source_digest("seek-error", NULL, 0, source_sha256);
        return 0;
    }
    long len = ftell(f);
    if (fseek(f, 0, SEEK_SET) != 0) {
        (void)fclose(f);
        userconfig_source_digest("seek-error", NULL, 0, source_sha256);
        return 0;
    }

    if (len <= 0 || len > MAX_CONFIG_SIZE) {
        (void)fclose(f);
        if (len > MAX_CONFIG_SIZE) {
            engine_log_warn("userconfig.file_too_large", "path", path);
            userconfig_source_digest("oversized", NULL, 0, source_sha256);
        } else {
            userconfig_source_digest("empty", NULL, 0, source_sha256);
        }
        return 0;
    }

    char *buf = malloc((size_t)len + SKIP_ONE);
    if (!buf) {
        (void)fclose(f);
        return ENGINE_NOT_FOUND;
    }

    size_t nread = fread(buf, SKIP_ONE, (size_t)len, f);
    (void)fclose(f);
    if (nread > (size_t)len) {
        nread = (size_t)len;
    }
    buf[nread] = '\0';
    userconfig_source_digest("present", buf, nread, source_sha256);

    yyjson_doc *doc = yyjson_read(buf, nread, 0);
    free(buf);

    if (!doc) {
        engine_log_warn("userconfig.corrupt_json", "path", path);
        return 0; /* corrupt JSON — silently ignore (fail-open) */
    }

    yyjson_val *root = yyjson_doc_get_root(doc);
    int rc = parse_extra_extensions(root, entries, count, path);
    yyjson_doc_free(doc);
    return rc;
}

/* ── Public API ──────────────────────────────────────────────────── */

engine_userconfig_t *engine_userconfig_load(const char *repo_path) {
    engine_userconfig_t *cfg = calloc(ENGINE_ALLOC_ONE, sizeof(engine_userconfig_t));
    if (!cfg) {
        return NULL;
    }

    engine_userext_t *entries = NULL;
    int count = 0;

    /* ── Step 1: Load global config ── */
    enum { PATH_BUF_SZ = 1280 };
    const char *cfg_base = engine_app_config_dir();
    const char *cfg_fallback = cfg_base ? cfg_base : "/tmp";
    char global_path[PATH_BUF_SZ];
    snprintf(global_path, sizeof(global_path), "%s/graph-engine/config.json", cfg_fallback);

    if (load_config_file(global_path, &entries, &count, cfg->global_source_sha256) != 0) {
        for (int i = 0; i < count; i++) {
            free(entries[i].ext);
        }
        free(entries);
        free(cfg);
        return NULL;
    }

    int global_count = count; /* entries[0..global_count) are from global */

    /* ── Step 2: Load project config ── */
    userconfig_source_digest("not-applicable", NULL, 0, cfg->project_source_sha256);
    if (repo_path && repo_path[0]) {
        char project_path[PATH_BUF_SZ];
        snprintf(project_path, sizeof(project_path), "%s/.graph-engine.json", repo_path);

        if (load_config_file(project_path, &entries, &count, cfg->project_source_sha256) != 0) {
            /* Free already-allocated entries */
            for (int i = 0; i < count; i++) {
                free(entries[i].ext);
            }
            free(entries);
            free(cfg);
            return NULL;
        }
    }

    /*
     * ── Step 3: Dedup — project entries win over global ──
     *
     * For any extension that appears in both global (indices 0..global_count)
     * and project (indices global_count..count), remove the global entry by
     * replacing it with the last global entry (order-insensitive dedup).
     */
    for (int p = global_count; p < count; p++) {
        for (int g = 0; g < global_count; g++) {
            if (entries[g].ext && strcmp(entries[g].ext, entries[p].ext) == 0) {
                /* Remove global entry: overwrite with last global entry */
                free(entries[g].ext);
                entries[g] = entries[global_count - SKIP_ONE];
                entries[global_count - SKIP_ONE].ext = NULL; /* mark as consumed */
                global_count--;
                break;
            }
        }
    }

    /*
     * Compact: remove any NULL-ext slots left by the dedup step.
     * (Those are the consumed "last global" entries.)
     */
    int write_idx = 0;
    for (int i = 0; i < count; i++) {
        if (entries[i].ext != NULL) {
            entries[write_idx++] = entries[i];
        }
    }
    count = write_idx;

    cfg->entries = entries;
    cfg->count = count;
    return cfg;
}

EngineLanguage engine_userconfig_lookup(const engine_userconfig_t *cfg, const char *ext) {
    if (!cfg || !ext || !ext[0]) {
        return ENGINE_LANG_COUNT;
    }
    for (int i = 0; i < cfg->count; i++) {
        if (cfg->entries[i].ext && strcmp(cfg->entries[i].ext, ext) == 0) {
            return cfg->entries[i].lang;
        }
    }
    return ENGINE_LANG_COUNT;
}

void engine_userconfig_free(engine_userconfig_t *cfg) {
    if (!cfg) {
        return;
    }
    for (int i = 0; i < cfg->count; i++) {
        free(cfg->entries[i].ext);
    }
    free(cfg->entries);
    free(cfg);
}
