/* Standard builds have no frontend pack and perform no UI asset I/O. */
#include "ui/asset_pack.h"

const char ENGINE_UI_ASSET_PACK_NAME[] = "";
const char ENGINE_UI_ASSET_SHA256[] = "";
const uint64_t ENGINE_UI_ASSET_SIZE = UINT64_C(0);

bool engine_ui_assets_supported(void) {
    return false;
}

const char *engine_ui_assets_current_pack_name(void) {
    return NULL;
}

void engine_ui_assets_set_binary_path(const char *path) {
    (void)path;
}

bool engine_ui_assets_warm(const char *home, char *err, size_t err_sz) {
    (void)home;
    (void)err;
    (void)err_sz;
    return true;
}

void engine_ui_assets_request_cancel(void) {}

engine_ui_assets_state_t engine_ui_assets_state(void) {
    return ENGINE_UI_ASSETS_UNAVAILABLE;
}

const engine_ui_asset_t *engine_ui_asset_lookup(const char *path) {
    (void)path;
    return NULL;
}

#ifdef ENGINE_CLI_ENABLE_TEST_API
bool engine_ui_assets_install(const char *install_dir, bool dry_run, char *err, size_t err_sz) {
    (void)install_dir;
    (void)dry_run;
    (void)err;
    (void)err_sz;
    return true;
}

/* Test seams: the stub build has no frontend assets; the testing interface is
 * a no-op. */
void engine_ui_assets_set_manifest_for_testing(const char *name, const char *sha256, uint64_t size) {
    (void)name;
    (void)sha256;
    (void)size;
}

void engine_ui_assets_reset_for_testing(void) {}
#endif

bool engine_ui_assets_remove(const char *install_dir, bool dry_run, char *err, size_t err_sz) {
    (void)install_dir;
    (void)dry_run;
    (void)err;
    (void)err_sz;
    return true;
}

bool engine_ui_assets_verify_file(const char *path) {
    (void)path;
    return false;
}

bool engine_ui_assets_stage_remove(const char *install_dir,
                                engine_activation_transaction_t **transaction_out,
                                bool *foreign_preserved_out, char *err, size_t err_sz) {
    (void)install_dir;
    (void)err;
    (void)err_sz;
    if (transaction_out) {
        *transaction_out = NULL;
    }
    if (foreign_preserved_out) {
        *foreign_preserved_out = false;
    }
    return transaction_out != NULL;
}

bool engine_ui_assets_stage_install(const char *install_dir,
                                 engine_activation_transaction_t **transaction_out, char *err,
                                 size_t err_sz) {
    (void)install_dir;
    (void)err;
    (void)err_sz;
    if (transaction_out) {
        *transaction_out = NULL;
    }
    return transaction_out != NULL;
}

engine_activation_transaction_status_t engine_ui_assets_commit_install(
    engine_activation_transaction_t *transaction) {
    return transaction ? ENGINE_ACTIVATION_TRANSACTION_INVALID_ARGUMENT
                       : ENGINE_ACTIVATION_TRANSACTION_OK;
}

engine_activation_transaction_status_t engine_ui_assets_commit_removal(
    engine_activation_transaction_t *transaction) {
    return transaction ? ENGINE_ACTIVATION_TRANSACTION_INVALID_ARGUMENT
                       : ENGINE_ACTIVATION_TRANSACTION_OK;
}
