/*
 * daemon.c — Process-local coordination and wire framing for the engine daemon.
 */
#include "daemon/daemon.h"

#include "foundation/compat_thread.h"

#include <stdlib.h>
#include <string.h>

typedef struct engine_daemon_subscription {
    engine_daemon_subscription_id_t id;
    engine_daemon_client_id_t client_id;
    struct engine_daemon_subscription *next;
} engine_daemon_subscription_t;

typedef struct engine_daemon_client {
    engine_daemon_client_id_t id;
    uint64_t last_heartbeat_ms;
    struct engine_daemon_client *next;
} engine_daemon_client_t;

typedef struct engine_daemon_job {
    char *project_key;
    engine_daemon_job_state_t state;
    engine_daemon_subscription_t *subscriptions;
    size_t subscription_count;
    bool cancel_callback_inflight;
    bool detached;
    struct engine_daemon_job *next;
    struct engine_daemon_job *action_next;
} engine_daemon_job_t;

typedef struct engine_daemon_watch {
    char *project_key;
    engine_daemon_subscription_t *subscriptions;
    size_t subscription_count;
    struct engine_daemon_watch *next;
    struct engine_daemon_watch *action_next;
} engine_daemon_watch_t;

struct engine_daemon_coordinator {
    engine_mutex_t mutex;
    engine_daemon_client_t *clients;
    engine_daemon_job_t *jobs;
    engine_daemon_watch_t *watches;
    size_t client_count;
    /* See engine_daemon_coordinator_set_permanent. */
    bool permanent;
    size_t job_count;
    size_t watch_count;
    size_t callback_count;
    uint64_t lease_timeout_ms;
    engine_daemon_client_id_t last_client_id;
    engine_daemon_subscription_id_t last_subscription_id;
    engine_daemon_coordinator_state_t state;
    engine_daemon_coordinator_hooks_t hooks;
};

typedef struct {
    engine_daemon_job_t *jobs;
    engine_daemon_watch_t *watches;
    engine_daemon_job_cancel_fn cancel_job;
    engine_daemon_watch_release_fn release_watch;
    void *context;
} engine_daemon_callback_batch_t;

enum {
    FRAME_MAGIC_0 = 0,
    FRAME_MAGIC_1 = 1,
    FRAME_MAGIC_2 = 2,
    FRAME_MAGIC_3 = 3,
    FRAME_VERSION = 4,
    FRAME_TYPE = 5,
    FRAME_FLAGS_HI = 6,
    FRAME_FLAGS_LO = 7,
    FRAME_LENGTH_3 = 8,
    FRAME_LENGTH_2 = 9,
    FRAME_LENGTH_1 = 10,
    FRAME_LENGTH_0 = 11,
};

static bool frame_type_valid(engine_daemon_frame_type_t type) {
    return type == ENGINE_DAEMON_FRAME_REQUEST || type == ENGINE_DAEMON_FRAME_RESPONSE;
}

static char *daemon_string_dup(const char *value) {
    size_t length = strlen(value);
    char *copy = malloc(length + 1);
    if (copy) {
        memcpy(copy, value, length + 1);
    }
    return copy;
}

static void free_subscriptions(engine_daemon_subscription_t *subscription) {
    while (subscription) {
        engine_daemon_subscription_t *next = subscription->next;
        free(subscription);
        subscription = next;
    }
}

static void free_job(engine_daemon_job_t *job) {
    if (job) {
        free_subscriptions(job->subscriptions);
        free(job->project_key);
        free(job);
    }
}

static void free_watch(engine_daemon_watch_t *watch) {
    if (watch) {
        free_subscriptions(watch->subscriptions);
        free(watch->project_key);
        free(watch);
    }
}

static engine_daemon_client_id_t issue_client_id_locked(engine_daemon_coordinator_t *coordinator) {
    if (coordinator->last_client_id == UINT64_MAX) {
        return ENGINE_DAEMON_CLIENT_ID_INVALID;
    }
    coordinator->last_client_id++;
    return coordinator->last_client_id;
}

static engine_daemon_subscription_id_t issue_subscription_id_locked(
    engine_daemon_coordinator_t *coordinator) {
    if (coordinator->last_subscription_id == UINT64_MAX) {
        return ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID;
    }
    coordinator->last_subscription_id++;
    return coordinator->last_subscription_id;
}

static engine_daemon_client_t *find_client_locked(engine_daemon_coordinator_t *coordinator,
                                               engine_daemon_client_id_t client_id) {
    for (engine_daemon_client_t *client = coordinator->clients; client; client = client->next) {
        if (client->id == client_id) {
            return client;
        }
    }
    return NULL;
}

static engine_daemon_job_t *find_job_locked(engine_daemon_coordinator_t *coordinator,
                                         const char *project_key) {
    for (engine_daemon_job_t *job = coordinator->jobs; job; job = job->next) {
        if (strcmp(job->project_key, project_key) == 0) {
            return job;
        }
    }
    return NULL;
}

static engine_daemon_watch_t *find_watch_locked(engine_daemon_coordinator_t *coordinator,
                                             const char *project_key) {
    for (engine_daemon_watch_t *watch = coordinator->watches; watch; watch = watch->next) {
        if (strcmp(watch->project_key, project_key) == 0) {
            return watch;
        }
    }
    return NULL;
}

static bool remove_subscription_locked(engine_daemon_subscription_t **subscriptions,
                                       size_t *subscription_count, engine_daemon_client_id_t client_id,
                                       engine_daemon_subscription_id_t subscription_id) {
    engine_daemon_subscription_t **cursor = subscriptions;
    while (*cursor) {
        engine_daemon_subscription_t *subscription = *cursor;
        if (subscription->id == subscription_id && subscription->client_id == client_id) {
            *cursor = subscription->next;
            free(subscription);
            (*subscription_count)--;
            return true;
        }
        cursor = &subscription->next;
    }
    return false;
}

static void remove_client_subscriptions_locked(engine_daemon_subscription_t **subscriptions,
                                               size_t *subscription_count,
                                               engine_daemon_client_id_t client_id) {
    engine_daemon_subscription_t **cursor = subscriptions;
    while (*cursor) {
        engine_daemon_subscription_t *subscription = *cursor;
        if (subscription->client_id == client_id) {
            *cursor = subscription->next;
            free(subscription);
            (*subscription_count)--;
        } else {
            cursor = &subscription->next;
        }
    }
}

static void callback_batch_init_locked(engine_daemon_coordinator_t *coordinator,
                                       engine_daemon_callback_batch_t *batch) {
    memset(batch, 0, sizeof(*batch));
    batch->cancel_job = coordinator->hooks.cancel_job;
    batch->release_watch = coordinator->hooks.release_watch;
    batch->context = coordinator->hooks.context;
}

static void request_job_cancel_locked(engine_daemon_coordinator_t *coordinator, engine_daemon_job_t *job,
                                      engine_daemon_callback_batch_t *batch) {
    if (job->subscription_count != 0 || job->state != ENGINE_DAEMON_JOB_RUNNING) {
        return;
    }
    job->state = ENGINE_DAEMON_JOB_CANCEL_REQUESTED;
    if (batch->cancel_job) {
        job->cancel_callback_inflight = true;
        job->action_next = batch->jobs;
        batch->jobs = job;
        coordinator->callback_count++;
    }
}

static void queue_watch_release_locked(engine_daemon_coordinator_t *coordinator,
                                       engine_daemon_watch_t *watch,
                                       engine_daemon_callback_batch_t *batch) {
    watch->action_next = batch->watches;
    batch->watches = watch;
    if (batch->release_watch) {
        coordinator->callback_count++;
    }
}

static void callback_batch_run(engine_daemon_coordinator_t *coordinator,
                               engine_daemon_callback_batch_t *batch) {
    engine_daemon_job_t *job = batch->jobs;
    while (job) {
        engine_daemon_job_t *next = job->action_next;
        batch->cancel_job(job->project_key, batch->context);

        engine_mutex_lock(&coordinator->mutex);
        coordinator->callback_count--;
        job->cancel_callback_inflight = false;
        bool detached = job->detached;
        engine_mutex_unlock(&coordinator->mutex);
        if (detached) {
            free_job(job);
        }
        job = next;
    }

    engine_daemon_watch_t *watch = batch->watches;
    while (watch) {
        engine_daemon_watch_t *next = watch->action_next;
        if (batch->release_watch) {
            batch->release_watch(watch->project_key, batch->context);
            engine_mutex_lock(&coordinator->mutex);
            coordinator->callback_count--;
            engine_mutex_unlock(&coordinator->mutex);
        }
        free_watch(watch);
        watch = next;
    }
}

static void release_client_resources_locked(engine_daemon_coordinator_t *coordinator,
                                            engine_daemon_client_id_t client_id,
                                            engine_daemon_callback_batch_t *batch) {
    for (engine_daemon_job_t *job = coordinator->jobs; job; job = job->next) {
        remove_client_subscriptions_locked(&job->subscriptions, &job->subscription_count,
                                           client_id);
        request_job_cancel_locked(coordinator, job, batch);
    }

    engine_daemon_watch_t **watch_cursor = &coordinator->watches;
    while (*watch_cursor) {
        engine_daemon_watch_t *watch = *watch_cursor;
        remove_client_subscriptions_locked(&watch->subscriptions, &watch->subscription_count,
                                           client_id);
        if (watch->subscription_count == 0) {
            *watch_cursor = watch->next;
            watch->next = NULL;
            coordinator->watch_count--;
            queue_watch_release_locked(coordinator, watch, batch);
        } else {
            watch_cursor = &watch->next;
        }
    }
}

static void release_client_locked(engine_daemon_coordinator_t *coordinator,
                                  engine_daemon_client_t *client, engine_daemon_callback_batch_t *batch) {
    release_client_resources_locked(coordinator, client->id, batch);
    free(client);
    coordinator->client_count--;
    if (coordinator->client_count == 0 && !coordinator->permanent) {
        coordinator->state = ENGINE_DAEMON_COORDINATOR_STOPPING;
    }
}

static bool terminal_job_locked(engine_daemon_coordinator_t *coordinator, const char *project_key,
                                bool require_cancellation, engine_daemon_job_t **free_after_unlock) {
    engine_daemon_job_t **cursor = &coordinator->jobs;
    while (*cursor && strcmp((*cursor)->project_key, project_key) != 0) {
        cursor = &(*cursor)->next;
    }
    if (!*cursor || (require_cancellation && (*cursor)->state == ENGINE_DAEMON_JOB_RUNNING)) {
        return false;
    }

    engine_daemon_job_t *job = *cursor;
    *cursor = job->next;
    job->next = NULL;
    job->detached = true;
    coordinator->job_count--;
    free_subscriptions(job->subscriptions);
    job->subscriptions = NULL;
    job->subscription_count = 0;
    if (!job->cancel_callback_inflight) {
        *free_after_unlock = job;
    }
    return true;
}

void engine_daemon_coordinator_set_permanent(engine_daemon_coordinator_t *coordinator, bool permanent) {
    if (!coordinator) {
        return;
    }
    engine_mutex_lock(&coordinator->mutex);
    coordinator->permanent = permanent;
    engine_mutex_unlock(&coordinator->mutex);
}

engine_daemon_coordinator_t *engine_daemon_coordinator_new(uint64_t lease_timeout_ms) {
    engine_daemon_coordinator_t *coordinator = calloc(1, sizeof(*coordinator));
    if (!coordinator) {
        return NULL;
    }
    engine_mutex_init(&coordinator->mutex);
    coordinator->lease_timeout_ms = lease_timeout_ms;
    coordinator->state = ENGINE_DAEMON_COORDINATOR_RUNNING;
    return coordinator;
}

void engine_daemon_coordinator_free(engine_daemon_coordinator_t *coordinator) {
    if (!coordinator) {
        return;
    }

    engine_daemon_client_t *client = coordinator->clients;
    while (client) {
        engine_daemon_client_t *next = client->next;
        free(client);
        client = next;
    }

    engine_daemon_job_t *job = coordinator->jobs;
    while (job) {
        engine_daemon_job_t *next = job->next;
        free_job(job);
        job = next;
    }

    engine_daemon_watch_t *watch = coordinator->watches;
    while (watch) {
        engine_daemon_watch_t *next = watch->next;
        free_watch(watch);
        watch = next;
    }
    engine_mutex_destroy(&coordinator->mutex);
    free(coordinator);
}

bool engine_daemon_coordinator_set_hooks(engine_daemon_coordinator_t *coordinator,
                                      const engine_daemon_coordinator_hooks_t *hooks) {
    if (!coordinator || !hooks) {
        return false;
    }
    engine_mutex_lock(&coordinator->mutex);
    coordinator->hooks = *hooks;
    engine_mutex_unlock(&coordinator->mutex);
    return true;
}

engine_daemon_coordinator_state_t engine_daemon_coordinator_state(engine_daemon_coordinator_t *coordinator) {
    if (!coordinator) {
        return ENGINE_DAEMON_COORDINATOR_STOPPING;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_coordinator_state_t state = coordinator->state;
    engine_mutex_unlock(&coordinator->mutex);
    return state;
}

engine_daemon_client_id_t engine_daemon_client_connected(engine_daemon_coordinator_t *coordinator,
                                                   uint64_t now_ms) {
    if (!coordinator) {
        return ENGINE_DAEMON_CLIENT_ID_INVALID;
    }

    engine_daemon_client_t *client = malloc(sizeof(*client));
    if (!client) {
        return ENGINE_DAEMON_CLIENT_ID_INVALID;
    }

    engine_mutex_lock(&coordinator->mutex);
    if (coordinator->state != ENGINE_DAEMON_COORDINATOR_RUNNING) {
        engine_mutex_unlock(&coordinator->mutex);
        free(client);
        return ENGINE_DAEMON_CLIENT_ID_INVALID;
    }
    engine_daemon_client_id_t client_id = issue_client_id_locked(coordinator);
    if (client_id == ENGINE_DAEMON_CLIENT_ID_INVALID) {
        engine_mutex_unlock(&coordinator->mutex);
        free(client);
        return ENGINE_DAEMON_CLIENT_ID_INVALID;
    }
    client->id = client_id;
    client->last_heartbeat_ms = now_ms;
    client->next = coordinator->clients;
    coordinator->clients = client;
    coordinator->client_count++;
    engine_mutex_unlock(&coordinator->mutex);
    return client_id;
}

bool engine_daemon_client_disconnected(engine_daemon_coordinator_t *coordinator,
                                    engine_daemon_client_id_t client_id, uint64_t now_ms) {
    (void)now_ms;
    if (!coordinator || client_id == ENGINE_DAEMON_CLIENT_ID_INVALID) {
        return false;
    }

    engine_daemon_callback_batch_t batch;
    engine_mutex_lock(&coordinator->mutex);
    callback_batch_init_locked(coordinator, &batch);
    engine_daemon_client_t **cursor = &coordinator->clients;
    while (*cursor && (*cursor)->id != client_id) {
        cursor = &(*cursor)->next;
    }
    if (!*cursor) {
        engine_mutex_unlock(&coordinator->mutex);
        return false;
    }
    engine_daemon_client_t *client = *cursor;
    *cursor = client->next;
    release_client_locked(coordinator, client, &batch);
    engine_mutex_unlock(&coordinator->mutex);

    callback_batch_run(coordinator, &batch);
    return true;
}

bool engine_daemon_client_heartbeat(engine_daemon_coordinator_t *coordinator,
                                 engine_daemon_client_id_t client_id, uint64_t now_ms) {
    if (!coordinator || client_id == ENGINE_DAEMON_CLIENT_ID_INVALID) {
        return false;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_client_t *client = find_client_locked(coordinator, client_id);
    bool found = client != NULL;
    if (client && now_ms > client->last_heartbeat_ms) {
        client->last_heartbeat_ms = now_ms;
    }
    engine_mutex_unlock(&coordinator->mutex);
    return found;
}

size_t engine_daemon_expire_leases(engine_daemon_coordinator_t *coordinator, uint64_t now_ms) {
    if (!coordinator) {
        return 0;
    }

    size_t expired_count = 0;
    engine_daemon_callback_batch_t batch;
    engine_mutex_lock(&coordinator->mutex);
    callback_batch_init_locked(coordinator, &batch);
    engine_daemon_client_t **cursor = &coordinator->clients;
    while (*cursor) {
        engine_daemon_client_t *client = *cursor;
        bool expired = now_ms >= client->last_heartbeat_ms &&
                       now_ms - client->last_heartbeat_ms >= coordinator->lease_timeout_ms;
        if (!expired) {
            cursor = &client->next;
            continue;
        }
        *cursor = client->next;
        release_client_locked(coordinator, client, &batch);
        expired_count++;
    }
    engine_mutex_unlock(&coordinator->mutex);

    callback_batch_run(coordinator, &batch);
    return expired_count;
}

size_t engine_daemon_active_clients(engine_daemon_coordinator_t *coordinator) {
    if (!coordinator) {
        return 0;
    }
    engine_mutex_lock(&coordinator->mutex);
    size_t count = coordinator->client_count;
    engine_mutex_unlock(&coordinator->mutex);
    return count;
}

engine_daemon_subscription_result_t engine_daemon_job_subscribe(
    engine_daemon_coordinator_t *coordinator, engine_daemon_client_id_t client_id,
    const char *project_key, engine_daemon_subscription_id_t *subscription_id) {
    if (subscription_id) {
        *subscription_id = ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID;
    }
    if (!coordinator || !subscription_id || !project_key || project_key[0] == '\0' ||
        client_id == ENGINE_DAEMON_CLIENT_ID_INVALID) {
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }

    engine_mutex_lock(&coordinator->mutex);
    if (coordinator->state != ENGINE_DAEMON_COORDINATOR_RUNNING ||
        !find_client_locked(coordinator, client_id)) {
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }
    engine_daemon_job_t *job = find_job_locked(coordinator, project_key);
    if (job && job->state != ENGINE_DAEMON_JOB_RUNNING) {
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }

    bool started = job == NULL;
    engine_daemon_job_t *new_job = NULL;
    char *key_copy = NULL;
    engine_daemon_subscription_t *subscription = malloc(sizeof(*subscription));
    if (started) {
        new_job = calloc(1, sizeof(*new_job));
        key_copy = daemon_string_dup(project_key);
    }
    if (!subscription || (started && (!new_job || !key_copy))) {
        free(subscription);
        free(new_job);
        free(key_copy);
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }

    engine_daemon_subscription_id_t id = issue_subscription_id_locked(coordinator);
    if (id == ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID) {
        free(subscription);
        free(new_job);
        free(key_copy);
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }
    if (started) {
        new_job->project_key = key_copy;
        new_job->state = ENGINE_DAEMON_JOB_RUNNING;
        new_job->next = coordinator->jobs;
        coordinator->jobs = new_job;
        coordinator->job_count++;
        job = new_job;
    }
    subscription->id = id;
    subscription->client_id = client_id;
    subscription->next = job->subscriptions;
    job->subscriptions = subscription;
    job->subscription_count++;
    *subscription_id = id;
    engine_mutex_unlock(&coordinator->mutex);
    return started ? ENGINE_DAEMON_SUBSCRIPTION_STARTED : ENGINE_DAEMON_SUBSCRIPTION_JOINED;
}

engine_daemon_subscription_result_t engine_daemon_watch_subscribe(
    engine_daemon_coordinator_t *coordinator, engine_daemon_client_id_t client_id,
    const char *project_key, engine_daemon_subscription_id_t *subscription_id) {
    if (subscription_id) {
        *subscription_id = ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID;
    }
    if (!coordinator || !subscription_id || !project_key || project_key[0] == '\0' ||
        client_id == ENGINE_DAEMON_CLIENT_ID_INVALID) {
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }

    engine_mutex_lock(&coordinator->mutex);
    if (coordinator->state != ENGINE_DAEMON_COORDINATOR_RUNNING ||
        !find_client_locked(coordinator, client_id)) {
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }
    engine_daemon_watch_t *watch = find_watch_locked(coordinator, project_key);
    bool started = watch == NULL;
    engine_daemon_watch_t *new_watch = NULL;
    char *key_copy = NULL;
    engine_daemon_subscription_t *subscription = malloc(sizeof(*subscription));
    if (started) {
        new_watch = calloc(1, sizeof(*new_watch));
        key_copy = daemon_string_dup(project_key);
    }
    if (!subscription || (started && (!new_watch || !key_copy))) {
        free(subscription);
        free(new_watch);
        free(key_copy);
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }

    engine_daemon_subscription_id_t id = issue_subscription_id_locked(coordinator);
    if (id == ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID) {
        free(subscription);
        free(new_watch);
        free(key_copy);
        engine_mutex_unlock(&coordinator->mutex);
        return ENGINE_DAEMON_SUBSCRIPTION_REJECTED;
    }
    if (started) {
        new_watch->project_key = key_copy;
        new_watch->next = coordinator->watches;
        coordinator->watches = new_watch;
        coordinator->watch_count++;
        watch = new_watch;
    }
    subscription->id = id;
    subscription->client_id = client_id;
    subscription->next = watch->subscriptions;
    watch->subscriptions = subscription;
    watch->subscription_count++;
    *subscription_id = id;
    engine_mutex_unlock(&coordinator->mutex);
    return started ? ENGINE_DAEMON_SUBSCRIPTION_STARTED : ENGINE_DAEMON_SUBSCRIPTION_JOINED;
}

bool engine_daemon_job_unsubscribe(engine_daemon_coordinator_t *coordinator,
                                engine_daemon_client_id_t client_id,
                                engine_daemon_subscription_id_t subscription_id) {
    if (!coordinator || client_id == ENGINE_DAEMON_CLIENT_ID_INVALID ||
        subscription_id == ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID) {
        return false;
    }

    engine_daemon_callback_batch_t batch;
    engine_mutex_lock(&coordinator->mutex);
    callback_batch_init_locked(coordinator, &batch);
    if (!find_client_locked(coordinator, client_id)) {
        engine_mutex_unlock(&coordinator->mutex);
        return false;
    }
    bool removed = false;
    for (engine_daemon_job_t *job = coordinator->jobs; job; job = job->next) {
        removed = remove_subscription_locked(&job->subscriptions, &job->subscription_count,
                                             client_id, subscription_id);
        if (removed) {
            request_job_cancel_locked(coordinator, job, &batch);
            break;
        }
    }
    engine_mutex_unlock(&coordinator->mutex);
    callback_batch_run(coordinator, &batch);
    return removed;
}

bool engine_daemon_watch_unsubscribe(engine_daemon_coordinator_t *coordinator,
                                  engine_daemon_client_id_t client_id,
                                  engine_daemon_subscription_id_t subscription_id) {
    if (!coordinator || client_id == ENGINE_DAEMON_CLIENT_ID_INVALID ||
        subscription_id == ENGINE_DAEMON_SUBSCRIPTION_ID_INVALID) {
        return false;
    }

    engine_daemon_callback_batch_t batch;
    engine_mutex_lock(&coordinator->mutex);
    callback_batch_init_locked(coordinator, &batch);
    if (!find_client_locked(coordinator, client_id)) {
        engine_mutex_unlock(&coordinator->mutex);
        return false;
    }
    bool removed = false;
    engine_daemon_watch_t **cursor = &coordinator->watches;
    while (*cursor) {
        engine_daemon_watch_t *watch = *cursor;
        removed = remove_subscription_locked(&watch->subscriptions, &watch->subscription_count,
                                             client_id, subscription_id);
        if (!removed) {
            cursor = &watch->next;
            continue;
        }
        if (watch->subscription_count == 0) {
            *cursor = watch->next;
            watch->next = NULL;
            coordinator->watch_count--;
            queue_watch_release_locked(coordinator, watch, &batch);
        }
        break;
    }
    engine_mutex_unlock(&coordinator->mutex);
    callback_batch_run(coordinator, &batch);
    return removed;
}

size_t engine_daemon_job_subscribers(engine_daemon_coordinator_t *coordinator, const char *project_key) {
    if (!coordinator || !project_key) {
        return 0;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_job_t *job = find_job_locked(coordinator, project_key);
    size_t count = job ? job->subscription_count : 0;
    engine_mutex_unlock(&coordinator->mutex);
    return count;
}

size_t engine_daemon_watch_subscribers(engine_daemon_coordinator_t *coordinator,
                                    const char *project_key) {
    if (!coordinator || !project_key) {
        return 0;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_watch_t *watch = find_watch_locked(coordinator, project_key);
    size_t count = watch ? watch->subscription_count : 0;
    engine_mutex_unlock(&coordinator->mutex);
    return count;
}

size_t engine_daemon_active_jobs(engine_daemon_coordinator_t *coordinator) {
    if (!coordinator) {
        return 0;
    }
    engine_mutex_lock(&coordinator->mutex);
    size_t count = coordinator->job_count;
    engine_mutex_unlock(&coordinator->mutex);
    return count;
}

size_t engine_daemon_active_watches(engine_daemon_coordinator_t *coordinator) {
    if (!coordinator) {
        return 0;
    }
    engine_mutex_lock(&coordinator->mutex);
    size_t count = coordinator->watch_count;
    engine_mutex_unlock(&coordinator->mutex);
    return count;
}

engine_daemon_job_state_t engine_daemon_job_state(engine_daemon_coordinator_t *coordinator,
                                            const char *project_key) {
    if (!coordinator || !project_key) {
        return ENGINE_DAEMON_JOB_NONE;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_job_t *job = find_job_locked(coordinator, project_key);
    engine_daemon_job_state_t state = job ? job->state : ENGINE_DAEMON_JOB_NONE;
    engine_mutex_unlock(&coordinator->mutex);
    return state;
}

bool engine_daemon_job_reaping(engine_daemon_coordinator_t *coordinator, const char *project_key) {
    if (!coordinator || !project_key) {
        return false;
    }
    engine_mutex_lock(&coordinator->mutex);
    engine_daemon_job_t *job = find_job_locked(coordinator, project_key);
    bool transitioned = job && job->state == ENGINE_DAEMON_JOB_CANCEL_REQUESTED;
    if (transitioned) {
        job->state = ENGINE_DAEMON_JOB_REAPING;
    }
    engine_mutex_unlock(&coordinator->mutex);
    return transitioned;
}

bool engine_daemon_job_reaped(engine_daemon_coordinator_t *coordinator, const char *project_key,
                           uint64_t now_ms) {
    (void)now_ms;
    if (!coordinator || !project_key) {
        return false;
    }
    engine_daemon_job_t *free_after_unlock = NULL;
    engine_mutex_lock(&coordinator->mutex);
    bool removed = terminal_job_locked(coordinator, project_key, true, &free_after_unlock);
    engine_mutex_unlock(&coordinator->mutex);
    free_job(free_after_unlock);
    return removed;
}

bool engine_daemon_job_completed(engine_daemon_coordinator_t *coordinator, const char *project_key,
                              uint64_t now_ms) {
    (void)now_ms;
    if (!coordinator || !project_key) {
        return false;
    }
    engine_daemon_job_t *free_after_unlock = NULL;
    engine_mutex_lock(&coordinator->mutex);
    bool removed = terminal_job_locked(coordinator, project_key, false, &free_after_unlock);
    engine_mutex_unlock(&coordinator->mutex);
    free_job(free_after_unlock);
    return removed;
}

bool engine_daemon_should_exit(engine_daemon_coordinator_t *coordinator, uint64_t now_ms) {
    (void)now_ms;
    if (!coordinator) {
        return false;
    }
    engine_mutex_lock(&coordinator->mutex);
    bool should_exit = coordinator->state == ENGINE_DAEMON_COORDINATOR_STOPPING &&
                       coordinator->client_count == 0 && coordinator->job_count == 0 &&
                       coordinator->watch_count == 0 && coordinator->callback_count == 0;
    engine_mutex_unlock(&coordinator->mutex);
    return should_exit;
}

bool engine_daemon_frame_header_encode(uint8_t header[ENGINE_DAEMON_FRAME_HEADER_SIZE],
                                    engine_daemon_frame_type_t type, uint16_t flags, uint32_t length) {
    if (!header || !frame_type_valid(type) || length > ENGINE_DAEMON_MAX_FRAME_SIZE) {
        return false;
    }
    header[FRAME_MAGIC_0] = 'C';
    header[FRAME_MAGIC_1] = 'B';
    header[FRAME_MAGIC_2] = 'M';
    header[FRAME_MAGIC_3] = 'D';
    header[FRAME_VERSION] = ENGINE_DAEMON_RENDEZVOUS_FRAME_VERSION;
    header[FRAME_TYPE] = (uint8_t)type;
    header[FRAME_FLAGS_HI] = (uint8_t)(flags >> 8);
    header[FRAME_FLAGS_LO] = (uint8_t)flags;
    header[FRAME_LENGTH_3] = (uint8_t)(length >> 24);
    header[FRAME_LENGTH_2] = (uint8_t)(length >> 16);
    header[FRAME_LENGTH_1] = (uint8_t)(length >> 8);
    header[FRAME_LENGTH_0] = (uint8_t)length;
    return true;
}

bool engine_daemon_frame_header_decode(const uint8_t header[ENGINE_DAEMON_FRAME_HEADER_SIZE],
                                    engine_daemon_frame_t *frame) {
    if (!header || !frame || header[FRAME_MAGIC_0] != 'C' || header[FRAME_MAGIC_1] != 'B' ||
        header[FRAME_MAGIC_2] != 'M' || header[FRAME_MAGIC_3] != 'D' ||
        header[FRAME_VERSION] != ENGINE_DAEMON_RENDEZVOUS_FRAME_VERSION) {
        return false;
    }

    engine_daemon_frame_type_t type = (engine_daemon_frame_type_t)header[FRAME_TYPE];
    uint32_t length = ((uint32_t)header[FRAME_LENGTH_3] << 24) |
                      ((uint32_t)header[FRAME_LENGTH_2] << 16) |
                      ((uint32_t)header[FRAME_LENGTH_1] << 8) | (uint32_t)header[FRAME_LENGTH_0];
    if (!frame_type_valid(type) || length > ENGINE_DAEMON_MAX_FRAME_SIZE) {
        return false;
    }

    frame->type = type;
    frame->flags =
        (uint16_t)(((uint16_t)header[FRAME_FLAGS_HI] << 8) | (uint16_t)header[FRAME_FLAGS_LO]);
    frame->length = length;
    return true;
}
