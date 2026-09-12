/*
 * service_patterns.c — Classify call edges by library identity in resolved QN.
 *
 * Instead of matching callee names (ambiguous: "get", "post", "send"),
 * we match library identifiers in the RESOLVED qualified name. The QN
 * contains the full module path, so import aliases are transparent:
 *   r.get("/api") → QN: project.venv.requests.api.get → match "requests" → HTTP_CALLS
 *
 * Two-level matching:
 *   1. Library identifier in QN → determines edge type (HTTP/ASYNC/CONFIG)
 *   2. Method suffix → determines HTTP method (get→GET, post→POST)
 */
#include "service_patterns.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/* ── Library identifier → edge type ────────────────────────────── */

typedef struct {
    const char *library_id; /* substring to find in resolved QN */
    engine_svc_kind_t kind;    /* HTTP_CALLS, ASYNC_CALLS, CONFIGURES */
    const char *broker;     /* for ASYNC: broker name (NULL otherwise) */
} lib_pattern_t;

/* HTTP client libraries — match these substrings in the resolved QN.
 * Sources: github.com/easybase/awesome-http, official SDK docs, agent research */
static const lib_pattern_t http_libraries[] = {
    /* Python */
    {"requests", ENGINE_SVC_HTTP, NULL},
    {"httpx", ENGINE_SVC_HTTP, NULL},
    {"aiohttp", ENGINE_SVC_HTTP, NULL},
    {"urllib", ENGINE_SVC_HTTP, NULL},
    {"urllib3", ENGINE_SVC_HTTP, NULL},
    {"httplib2", ENGINE_SVC_HTTP, NULL},
    {"pycurl", ENGINE_SVC_HTTP, NULL},
    {"treq", ENGINE_SVC_HTTP, NULL},
    {"uplink", ENGINE_SVC_HTTP, NULL},

    /* JavaScript / TypeScript */
    {"axios", ENGINE_SVC_HTTP, NULL},
    {"superagent", ENGINE_SVC_HTTP, NULL},
    {"needle", ENGINE_SVC_HTTP, NULL},
    {"node-fetch", ENGINE_SVC_HTTP, NULL},
    {"undici", ENGINE_SVC_HTTP, NULL},
    {"ofetch", ENGINE_SVC_HTTP, NULL},
    {"wretch", ENGINE_SVC_HTTP, NULL},
    {"sindresorhus/ky", ENGINE_SVC_HTTP, NULL},
    {"phin", ENGINE_SVC_HTTP, NULL},

    /* Go */
    {"net/http", ENGINE_SVC_HTTP, NULL},
    {"resty", ENGINE_SVC_HTTP, NULL},
    {"sling", ENGINE_SVC_HTTP, NULL},
    {"heimdall", ENGINE_SVC_HTTP, NULL},
    {"gentleman", ENGINE_SVC_HTTP, NULL},
    {"retryablehttp", ENGINE_SVC_HTTP, NULL},

    /* Java / Kotlin */
    {"HttpClient", ENGINE_SVC_HTTP, NULL},
    {"OkHttp", ENGINE_SVC_HTTP, NULL},
    {"okhttp3", ENGINE_SVC_HTTP, NULL},
    {"RestTemplate", ENGINE_SVC_HTTP, NULL},
    {"WebClient", ENGINE_SVC_HTTP, NULL},
    {"Unirest", ENGINE_SVC_HTTP, NULL},
    {"AsyncHttpClient", ENGINE_SVC_HTTP, NULL},
    {"apache.http", ENGINE_SVC_HTTP, NULL},
    {"Retrofit", ENGINE_SVC_HTTP, NULL},
    {"Feign", ENGINE_SVC_HTTP, NULL},
    {"ktor.client", ENGINE_SVC_HTTP, NULL},
    {"kittinunf.fuel", ENGINE_SVC_HTTP, NULL},

    /* Rust */
    {"reqwest", ENGINE_SVC_HTTP, NULL},
    {"hyper", ENGINE_SVC_HTTP, NULL},
    {"surf", ENGINE_SVC_HTTP, NULL},
    {"ureq", ENGINE_SVC_HTTP, NULL},
    {"isahc", ENGINE_SVC_HTTP, NULL},
    {"attohttpc", ENGINE_SVC_HTTP, NULL},

    /* C# */
    {"HttpClient", ENGINE_SVC_HTTP, NULL},
    {"RestSharp", ENGINE_SVC_HTTP, NULL},
    {"Flurl", ENGINE_SVC_HTTP, NULL},
    {"Refit", ENGINE_SVC_HTTP, NULL},

    /* Ruby */
    {"HTTParty", ENGINE_SVC_HTTP, NULL},
    {"Faraday", ENGINE_SVC_HTTP, NULL},
    {"RestClient", ENGINE_SVC_HTTP, NULL},
    {"Typhoeus", ENGINE_SVC_HTTP, NULL},
    {"Excon", ENGINE_SVC_HTTP, NULL},
    {"Net::HTTP", ENGINE_SVC_HTTP, NULL},

    /* PHP */
    {"Guzzle", ENGINE_SVC_HTTP, NULL},
    {"guzzle", ENGINE_SVC_HTTP, NULL},
    {"curl", ENGINE_SVC_HTTP, NULL},
    {"Symfony\\HttpClient", ENGINE_SVC_HTTP, NULL},

    /* C/C++ */
    {"cpr", ENGINE_SVC_HTTP, NULL},
    {"cpp-httplib", ENGINE_SVC_HTTP, NULL},
    {"Poco.Net", ENGINE_SVC_HTTP, NULL},
    {"Beast", ENGINE_SVC_HTTP, NULL},

    /* Swift */
    {"Alamofire", ENGINE_SVC_HTTP, NULL},
    {"Moya", ENGINE_SVC_HTTP, NULL},
    {"URLSession", ENGINE_SVC_HTTP, NULL},

    /* Dart */
    {"Dio", ENGINE_SVC_HTTP, NULL},
    {"dio", ENGINE_SVC_HTTP, NULL},
    {"package:http", ENGINE_SVC_HTTP, NULL},
    {"Chopper", ENGINE_SVC_HTTP, NULL},

    /* Elixir */
    {"HTTPoison", ENGINE_SVC_HTTP, NULL},
    {"Tesla", ENGINE_SVC_HTTP, NULL},
    {"Finch", ENGINE_SVC_HTTP, NULL},
    {"Mint.HTTP", ENGINE_SVC_HTTP, NULL},

    /* Scala */
    {"sttp", ENGINE_SVC_HTTP, NULL},
    {"akka.http", ENGINE_SVC_HTTP, NULL},
    {"http4s", ENGINE_SVC_HTTP, NULL},
    {"scalaj", ENGINE_SVC_HTTP, NULL},

    /* Haskell */
    {"wreq", ENGINE_SVC_HTTP, NULL},
    {"http-client", ENGINE_SVC_HTTP, NULL},
    {"http-conduit", ENGINE_SVC_HTTP, NULL},
    {"servant-client", ENGINE_SVC_HTTP, NULL},
    {"Network.HTTP", ENGINE_SVC_HTTP, NULL},

    /* Lua */
    {"socket.http", ENGINE_SVC_HTTP, NULL},
    {"resty.http", ENGINE_SVC_HTTP, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* Async dispatch / message broker libraries */
static const lib_pattern_t async_libraries[] = {
    /* GCP */
    {"cloudtasks", ENGINE_SVC_ASYNC, "cloud_tasks"},
    {"cloud_tasks", ENGINE_SVC_ASYNC, "cloud_tasks"},
    {"cloud.tasks", ENGINE_SVC_ASYNC, "cloud_tasks"},
    {"CloudTasks", ENGINE_SVC_ASYNC, "cloud_tasks"},
    {"pubsub", ENGINE_SVC_ASYNC, "pubsub"},
    {"cloud.pubsub", ENGINE_SVC_ASYNC, "pubsub"},
    {"PubSub", ENGINE_SVC_ASYNC, "pubsub"},

    /* AWS — use SDK module paths to avoid false positives.  engine_fqn_compute
     * converts path slashes to '.', so a resolved local Go QN reads
     * "aws-sdk-go.service.sqs..."; include both slash and dot forms so the
     * substring match fires whether the id comes from an import path or a QN. */
    {"aws-sdk-go/service/sqs", ENGINE_SVC_ASYNC, "sqs"},
    {"aws-sdk-go.service.sqs", ENGINE_SVC_ASYNC, "sqs"},
    {"aws_sdk_sqs", ENGINE_SVC_ASYNC, "sqs"},
    {"Amazon.SQS", ENGINE_SVC_ASYNC, "sqs"},
    {"@aws-sdk/client-sqs", ENGINE_SVC_ASYNC, "sqs"},
    {"boto3.client.sqs", ENGINE_SVC_ASYNC, "sqs"},
    {"aws-sdk-go/service/sns", ENGINE_SVC_ASYNC, "sns"},
    {"aws-sdk-go.service.sns", ENGINE_SVC_ASYNC, "sns"},
    {"aws_sdk_sns", ENGINE_SVC_ASYNC, "sns"},
    {"Amazon.SNS", ENGINE_SVC_ASYNC, "sns"},
    {"@aws-sdk/client-sns", ENGINE_SVC_ASYNC, "sns"},
    {"eventbridge", ENGINE_SVC_ASYNC, "eventbridge"},
    {"EventBridge", ENGINE_SVC_ASYNC, "eventbridge"},
    {"aws-sdk-go/service/lambda", ENGINE_SVC_ASYNC, "lambda"},
    {"aws-sdk-go.service.lambda", ENGINE_SVC_ASYNC, "lambda"},
    {"aws_sdk_lambda", ENGINE_SVC_ASYNC, "lambda"},
    {"@aws-sdk/client-lambda", ENGINE_SVC_ASYNC, "lambda"},
    {"stepfunctions", ENGINE_SVC_ASYNC, "stepfunctions"},

    /* Azure */
    {"ServiceBus", ENGINE_SVC_ASYNC, "servicebus"},
    {"Azure.Messaging", ENGINE_SVC_ASYNC, "servicebus"},

    /* Kafka */
    {"kafka", ENGINE_SVC_ASYNC, "kafka"},
    {"Kafka", ENGINE_SVC_ASYNC, "kafka"},
    {"kafkajs", ENGINE_SVC_ASYNC, "kafka"},
    {"sarama", ENGINE_SVC_ASYNC, "kafka"},
    {"rdkafka", ENGINE_SVC_ASYNC, "kafka"},
    {"confluent", ENGINE_SVC_ASYNC, "kafka"},
    {"Confluent.Kafka", ENGINE_SVC_ASYNC, "kafka"},

    /* RabbitMQ */
    {"amqp", ENGINE_SVC_ASYNC, "rabbitmq"},
    {"AMQP", ENGINE_SVC_ASYNC, "rabbitmq"},
    {"amqplib", ENGINE_SVC_ASYNC, "rabbitmq"},
    {"RabbitMQ", ENGINE_SVC_ASYNC, "rabbitmq"},
    {"lapin", ENGINE_SVC_ASYNC, "rabbitmq"},
    {"MassTransit", ENGINE_SVC_ASYNC, "rabbitmq"},

    /* NATS */
    {"nats", ENGINE_SVC_ASYNC, "nats"},
    {"NATS", ENGINE_SVC_ASYNC, "nats"},

    /* Redis pub/sub */
    {"ioredis", ENGINE_SVC_ASYNC, "redis"},

    /* Task queues */
    {"celery", ENGINE_SVC_ASYNC, "celery"},
    {"Celery", ENGINE_SVC_ASYNC, "celery"},
    {"dramatiq", ENGINE_SVC_ASYNC, "dramatiq"},
    {"huey", ENGINE_SVC_ASYNC, "huey"},
    {"python-rq", ENGINE_SVC_ASYNC, "rq"},
    {"rq.Queue", ENGINE_SVC_ASYNC, "rq"},
    {"bullmq", ENGINE_SVC_ASYNC, "bullmq"},
    {"BullMQ", ENGINE_SVC_ASYNC, "bullmq"},
    {"bull.Queue", ENGINE_SVC_ASYNC, "bull"},
    {"Sidekiq", ENGINE_SVC_ASYNC, "sidekiq"},
    {"sidekiq", ENGINE_SVC_ASYNC, "sidekiq"},
    {"Resque", ENGINE_SVC_ASYNC, "resque"},
    {"GoodJob", ENGINE_SVC_ASYNC, "goodjob"},
    {"DelayedJob", ENGINE_SVC_ASYNC, "delayed_job"},
    {"Hangfire", ENGINE_SVC_ASYNC, "hangfire"},
    {"NServiceBus", ENGINE_SVC_ASYNC, "nservicebus"},
    {"asynq", ENGINE_SVC_ASYNC, "asynq"},
    {"RichardKnop/machinery", ENGINE_SVC_ASYNC, "machinery"},

    /* Workflow engines — use specific module paths to avoid "Temporal" in Django etc. */
    {"temporalio", ENGINE_SVC_ASYNC, "temporal"},
    {"@temporalio", ENGINE_SVC_ASYNC, "temporal"},
    {"temporal.client", ENGINE_SVC_ASYNC, "temporal"},
    {"temporal.worker", ENGINE_SVC_ASYNC, "temporal"},
    {"inngest", ENGINE_SVC_ASYNC, "inngest"},

    /* Elixir */
    {"Oban", ENGINE_SVC_ASYNC, "oban"},
    {"Broadway", ENGINE_SVC_ASYNC, "broadway"},
    {"GenStage", ENGINE_SVC_ASYNC, "genstage"},
    {"Phoenix.PubSub", ENGINE_SVC_ASYNC, "phoenix_pubsub"},

    /* Scala */
    {"Alpakka", ENGINE_SVC_ASYNC, "alpakka"},

    /* MQTT */
    {"mqtt", ENGINE_SVC_ASYNC, "mqtt"},
    {"paho.mqtt", ENGINE_SVC_ASYNC, "mqtt"},
    {"MQTTClient", ENGINE_SVC_ASYNC, "mqtt"},
    {"mosquitto", ENGINE_SVC_ASYNC, "mqtt"},
    {"asyncio_mqtt", ENGINE_SVC_ASYNC, "mqtt"},
    {"gmqtt", ENGINE_SVC_ASYNC, "mqtt"},
    {"rumqttc", ENGINE_SVC_ASYNC, "mqtt"},

    /* NATS */
    {"nats.go", ENGINE_SVC_ASYNC, "nats"},
    {"nats-py", ENGINE_SVC_ASYNC, "nats"},
    {"nats.ws", ENGINE_SVC_ASYNC, "nats"},
    {"nats.java", ENGINE_SVC_ASYNC, "nats"},
    {"nats.net", ENGINE_SVC_ASYNC, "nats"},
    {"async-nats", ENGINE_SVC_ASYNC, "nats"},
    {"nats.rs", ENGINE_SVC_ASYNC, "nats"},

    /* Dapr pub/sub */
    {"dapr.clients.grpc", ENGINE_SVC_ASYNC, "dapr"},
    {"DaprClient", ENGINE_SVC_ASYNC, "dapr"},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* Config accessor libraries */
static const lib_pattern_t config_libraries[] = {
    /* Universal */
    {"getenv", ENGINE_SVC_CONFIG, NULL},
    {"Getenv", ENGINE_SVC_CONFIG, NULL},
    {"getEnv", ENGINE_SVC_CONFIG, NULL},
    {"LookupEnv", ENGINE_SVC_CONFIG, NULL},
    {"lookupEnv", ENGINE_SVC_CONFIG, NULL},
    {"get_env", ENGINE_SVC_CONFIG, NULL},
    {"fetch_env", ENGINE_SVC_CONFIG, NULL},
    {"GetEnvironmentVariable", ENGINE_SVC_CONFIG, NULL},
    {"getProperty", ENGINE_SVC_CONFIG, NULL},
    {"getEnvironment", ENGINE_SVC_CONFIG, NULL},

    /* Go */
    {"viper", ENGINE_SVC_CONFIG, NULL},
    {"envconfig", ENGINE_SVC_CONFIG, NULL},
    {"godotenv", ENGINE_SVC_CONFIG, NULL},

    /* Python */
    {"decouple", ENGINE_SVC_CONFIG, NULL},
    {"dynaconf", ENGINE_SVC_CONFIG, NULL},
    {"dotenv", ENGINE_SVC_CONFIG, NULL},

    /* JS/TS */
    {"nconf", ENGINE_SVC_CONFIG, NULL},
    {"convict", ENGINE_SVC_CONFIG, NULL},
    {"envalid", ENGINE_SVC_CONFIG, NULL},

    /* Rust */
    {"dotenvy", ENGINE_SVC_CONFIG, NULL},
    {"figment", ENGINE_SVC_CONFIG, NULL},
    {"config-rs", ENGINE_SVC_CONFIG, NULL},

    /* Java/Scala */
    {"ConfigFactory", ENGINE_SVC_CONFIG, NULL},
    {"ConfigurationProperties", ENGINE_SVC_CONFIG, NULL},

    /* Elixir */
    {"Application.get_env", ENGINE_SVC_CONFIG, NULL},
    {"Application.fetch_env", ENGINE_SVC_CONFIG, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* Route registration frameworks — callee resolves to one of these AND
 * has an HTTP method suffix → ENGINE_SVC_ROUTE_REG.
 * Distinguished from HTTP clients: "gin.GET" registers a handler,
 * "requests.get" makes an outbound HTTP call. */
static const lib_pattern_t route_reg_libraries[] = {
    /* Go */
    {"gin-gonic/gin", ENGINE_SVC_ROUTE_REG, NULL},
    {"gin.", ENGINE_SVC_ROUTE_REG, NULL},
    {"go-chi/chi", ENGINE_SVC_ROUTE_REG, NULL},
    {"chi.", ENGINE_SVC_ROUTE_REG, NULL},
    {"gorilla/mux", ENGINE_SVC_ROUTE_REG, NULL},
    {"labstack/echo", ENGINE_SVC_ROUTE_REG, NULL},
    {"echo.", ENGINE_SVC_ROUTE_REG, NULL},
    {"gofiber/fiber", ENGINE_SVC_ROUTE_REG, NULL},
    {"fiber.", ENGINE_SVC_ROUTE_REG, NULL},
    {"net/http.ServeMux", ENGINE_SVC_ROUTE_REG, NULL},
    {"http.ServeMux", ENGINE_SVC_ROUTE_REG, NULL},
    {"httprouter", ENGINE_SVC_ROUTE_REG, NULL},

    /* JavaScript / TypeScript */
    {"express", ENGINE_SVC_ROUTE_REG, NULL},
    {"fastify", ENGINE_SVC_ROUTE_REG, NULL},
    {"koa-router", ENGINE_SVC_ROUTE_REG, NULL},
    {"hono", ENGINE_SVC_ROUTE_REG, NULL},
    {"hapi", ENGINE_SVC_ROUTE_REG, NULL},

    /* Python (non-decorator, e.g., Flask add_url_rule) */
    {"flask", ENGINE_SVC_ROUTE_REG, NULL},
    {"FastAPI", ENGINE_SVC_ROUTE_REG, NULL},
    {"starlette", ENGINE_SVC_ROUTE_REG, NULL},

    /* PHP */
    {"Laravel", ENGINE_SVC_ROUTE_REG, NULL},
    {"Illuminate.Routing", ENGINE_SVC_ROUTE_REG, NULL},
    {"Symfony.Routing", ENGINE_SVC_ROUTE_REG, NULL},

    /* Kotlin */
    {"ktor.server", ENGINE_SVC_ROUTE_REG, NULL},
    {"ktor.routing", ENGINE_SVC_ROUTE_REG, NULL},

    /* Rust */
    {"actix-web", ENGINE_SVC_ROUTE_REG, NULL},
    {"actix_web", ENGINE_SVC_ROUTE_REG, NULL},
    {"axum", ENGINE_SVC_ROUTE_REG, NULL},
    {"rocket", ENGINE_SVC_ROUTE_REG, NULL},

    /* Java */
    {"Spring", ENGINE_SVC_ROUTE_REG, NULL},
    {"jakarta.ws.rs", ENGINE_SVC_ROUTE_REG, NULL},

    /* C# */
    {"Microsoft.AspNetCore", ENGINE_SVC_ROUTE_REG, NULL},
    {"MapGet", ENGINE_SVC_ROUTE_REG, NULL},
    {"MapPost", ENGINE_SVC_ROUTE_REG, NULL},

    /* Ruby */
    {"ActionDispatch", ENGINE_SVC_ROUTE_REG, NULL},
    {"Sinatra", ENGINE_SVC_ROUTE_REG, NULL},

    /* Elixir */
    {"Phoenix.Router", ENGINE_SVC_ROUTE_REG, NULL},

    /* Scala */
    {"akka.http.scaladsl.server", ENGINE_SVC_ROUTE_REG, NULL},
    {"play.api.routing", ENGINE_SVC_ROUTE_REG, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* gRPC client libraries — protobuf stub invocations */
static const lib_pattern_t grpc_libraries[] = {
    /* Go */
    {"google.golang.org/grpc", ENGINE_SVC_GRPC, NULL},
    {"grpc.Dial", ENGINE_SVC_GRPC, NULL},
    {"grpc.NewClient", ENGINE_SVC_GRPC, NULL},
    {"grpc.DialContext", ENGINE_SVC_GRPC, NULL},

    /* Python */
    {"grpc.insecure_channel", ENGINE_SVC_GRPC, NULL},
    {"grpc.secure_channel", ENGINE_SVC_GRPC, NULL},
    {"grpcio", ENGINE_SVC_GRPC, NULL},
    {"grpc.aio", ENGINE_SVC_GRPC, NULL},

    /* Java/Kotlin */
    {"io.grpc", ENGINE_SVC_GRPC, NULL},
    {"ManagedChannelBuilder", ENGINE_SVC_GRPC, NULL},
    {"ManagedChannel", ENGINE_SVC_GRPC, NULL},
    {"newBlockingStub", ENGINE_SVC_GRPC, NULL},
    {"newFutureStub", ENGINE_SVC_GRPC, NULL},

    /* C# */
    {"Grpc.Net.Client", ENGINE_SVC_GRPC, NULL},
    {"GrpcChannel", ENGINE_SVC_GRPC, NULL},
    {"Grpc.Core", ENGINE_SVC_GRPC, NULL},

    /* JS/TS */
    {"@grpc/grpc-js", ENGINE_SVC_GRPC, NULL},
    {"grpc-web", ENGINE_SVC_GRPC, NULL},

    /* Rust */
    {"tonic", ENGINE_SVC_GRPC, NULL},

    /* Dart/Flutter */
    {"package:grpc", ENGINE_SVC_GRPC, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* GraphQL client libraries */
static const lib_pattern_t graphql_libraries[] = {
    /* JS/TS */
    {"graphql-request", ENGINE_SVC_GRAPHQL, NULL},
    {"@apollo/client", ENGINE_SVC_GRAPHQL, NULL},
    {"apollo-client", ENGINE_SVC_GRAPHQL, NULL},
    {"urql", ENGINE_SVC_GRAPHQL, NULL},
    {"graphql-tag", ENGINE_SVC_GRAPHQL, NULL},

    /* Python */
    {"gql", ENGINE_SVC_GRAPHQL, NULL},
    {"sgqlc", ENGINE_SVC_GRAPHQL, NULL},
    {"graphene", ENGINE_SVC_GRAPHQL, NULL},

    /* Java */
    {"graphql-java", ENGINE_SVC_GRAPHQL, NULL},
    {"DgsQueryExecutor", ENGINE_SVC_GRAPHQL, NULL},

    /* Go */
    {"graphql-go", ENGINE_SVC_GRAPHQL, NULL},
    {"gqlgen", ENGINE_SVC_GRAPHQL, NULL},

    /* Ruby */
    {"graphql-ruby", ENGINE_SVC_GRAPHQL, NULL},

    /* Rust */
    {"async-graphql", ENGINE_SVC_GRAPHQL, NULL},
    {"juniper", ENGINE_SVC_GRAPHQL, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* tRPC libraries (TypeScript only) */
static const lib_pattern_t trpc_libraries[] = {
    {"@trpc/server", ENGINE_SVC_TRPC, NULL},
    {"@trpc/client", ENGINE_SVC_TRPC, NULL},
    {"@trpc/react-query", ENGINE_SVC_TRPC, NULL},
    {"createTRPCRouter", ENGINE_SVC_TRPC, NULL},
    {"createTRPCProxyClient", ENGINE_SVC_TRPC, NULL},

    {NULL, ENGINE_SVC_NONE, NULL},
};

/* Method suffix type (used by both route registration and HTTP client tables) */
typedef struct {
    const char *suffix;
    const char *method;
} method_suffix_t;

/* Route registration method suffixes — matched on callee name.
 * These are methods on router objects that register handlers. */
static const method_suffix_t route_reg_suffixes[] = {
    /* HTTP method registrations */
    {".GET", "GET"},
    {".Get", "GET"},
    {".get", "GET"},
    {".POST", "POST"},
    {".Post", "POST"},
    {".post", "POST"},
    {".PUT", "PUT"},
    {".Put", "PUT"},
    {".put", "PUT"},
    {".DELETE", "DELETE"},
    {".Delete", "DELETE"},
    {".delete", "DELETE"},
    {".PATCH", "PATCH"},
    {".Patch", "PATCH"},
    {".patch", "PATCH"},
    /* Handle/HandleFunc (Go stdlib, gorilla) */
    {".Handle", "ANY"},
    {".HandleFunc", "ANY"},
    {".handle", "ANY"},
    /* Framework-specific route registration */
    {".Route", "ANY"},
    {".route", "ANY"},
    {"::get", "GET"},
    {"::post", "POST"},
    {"::put", "PUT"},
    {"::delete", "DELETE"},
    {"::patch", "PATCH"},
    /* Minimal API (C# ASP.NET) */
    {".MapGet", "GET"},
    {".MapPost", "POST"},
    {".MapPut", "PUT"},
    {".MapDelete", "DELETE"},
    /* Router mounting / prefix registration (any method) */
    {".include_router", "ANY"},
    {".mount", "ANY"},
    {".add_url_rule", "ANY"},
    {".register_blueprint", "ANY"},
    {".use", "ANY"},
    {".register", "ANY"},
    {".add_route", "ANY"},
    {".add_api_route", "ANY"},
    {".add_api_websocket_route", "ANY"},
    {NULL, NULL},
};

/* ── HTTP method inference from function/method name suffix ───── */

static const method_suffix_t method_suffixes[] = {
    {".get", "GET"},           {".Get", "GET"},           {".GET", "GET"},
    {".post", "POST"},         {".Post", "POST"},         {".POST", "POST"},
    {".put", "PUT"},           {".Put", "PUT"},           {".PUT", "PUT"},
    {".delete", "DELETE"},     {".Delete", "DELETE"},     {".DELETE", "DELETE"},
    {".patch", "PATCH"},       {".Patch", "PATCH"},       {".PATCH", "PATCH"},
    {".head", "HEAD"},         {".Head", "HEAD"},         {".HEAD", "HEAD"},
    {".options", "OPTIONS"},   {".Options", "OPTIONS"},   {"GetAsync", "GET"},
    {"PostAsync", "POST"},     {"PutAsync", "PUT"},       {"DeleteAsync", "DELETE"},
    {"SendAsync", NULL},       {"getForObject", "GET"},   {"getForEntity", "GET"},
    {"postForObject", "POST"}, {"postForEntity", "POST"}, {NULL, NULL},
};

/* ── Matching implementation ───────────────────────────────────── */

/* Check if any library identifier appears as a substring in the QN.
 * Case-sensitive: "requests" matches "project.venv.requests.api.get"
 * but not "Requests". Library names are specific enough to avoid
 * false positives even with substring matching. */
static const lib_pattern_t *match_qn(const char *qn, const lib_pattern_t *patterns) {
    if (!qn || !qn[0]) {
        return NULL;
    }
    for (int i = 0; patterns[i].library_id != NULL; i++) {
        if (strstr(qn, patterns[i].library_id) != NULL) {
            return &patterns[i];
        }
    }
    return NULL;
}

static bool starts_with_segment(const char *path, const char *segment) {
    if (!path || path[0] != '/' || !segment) {
        return false;
    }
    size_t seg_len = strlen(segment);
    const char *p = path + 1;
    return strncmp(p, segment, seg_len) == 0 && (p[seg_len] == '\0' || p[seg_len] == '/');
}

static bool contains_segment(const char *path, const char *segment) {
    if (!path || !segment) {
        return false;
    }
    size_t seg_len = strlen(segment);
    const char *p = path;
    while ((p = strchr(p, '/')) != NULL) {
        p++;
        if (strncmp(p, segment, seg_len) == 0 && (p[seg_len] == '\0' || p[seg_len] == '/')) {
            return true;
        }
    }
    return false;
}

static bool is_digit_char(char ch) {
    return ch >= '0' && ch <= '9';
}

static bool has_http_route_marker(const char *path) {
    if (starts_with_segment(path, "api") || starts_with_segment(path, "apis") ||
        starts_with_segment(path, "graphql") || starts_with_segment(path, "health") ||
        starts_with_segment(path, "metrics")) {
        return true;
    }
    return path && path[0] == '/' && path[1] == 'v' && is_digit_char(path[2]) &&
           (path[3] == '\0' || path[3] == '/');
}

static bool has_filesystem_root(const char *path) {
    static const char *const roots[] = {"etc",     "root", "var",   "usr",     "home", "tmp",
                                        "private", "opt",  "bin",   "sbin",    "dev",  "proc",
                                        "sys",     "run",  "lib",   "lib64",   "mnt",  "media",
                                        "boot",    "srv",  "Users", "Volumes", NULL};
    for (int i = 0; roots[i]; i++) {
        if (starts_with_segment(path, roots[i])) {
            return true;
        }
    }
    return false;
}

static bool has_hidden_config_segment(const char *path) {
    static const char *const segments[] = {".aws", ".azure", ".config", ".docker", ".env",
                                           ".git", ".gnupg", ".kube",   ".ssh",    NULL};
    for (int i = 0; segments[i]; i++) {
        if (contains_segment(path, segments[i])) {
            return true;
        }
    }
    return false;
}

static bool path_ext_matches(const char *ext, const char *wanted) {
    return ext && wanted && strcmp(ext, wanted) == 0;
}

static bool has_filesystem_extension(const char *path) {
    if (!path) {
        return false;
    }
    const char *end = strpbrk(path, "?#");
    if (!end) {
        end = path + strlen(path);
    }
    const char *last_slash = path;
    for (const char *p = path; p < end; p++) {
        if (*p == '/') {
            last_slash = p;
        }
    }
    const char *dot = NULL;
    for (const char *p = last_slash + 1; p < end; p++) {
        if (*p == '.') {
            dot = p;
        }
    }
    if (!dot || dot == end - 1) {
        return false;
    }
    char ext[32];
    size_t ext_len = (size_t)(end - dot);
    if (ext_len >= sizeof(ext)) {
        return false;
    }
    memcpy(ext, dot, ext_len);
    ext[ext_len] = '\0';

    static const char *const hard_file_exts[] = {
        ".cfg",  ".conf",   ".credentials", ".crt",  ".db",         ".env",
        ".ini",  ".key",    ".pem",         ".pid",  ".properties", ".service",
        ".sock", ".socket", ".sqlite",      ".toml", NULL};
    for (int i = 0; hard_file_exts[i]; i++) {
        if (path_ext_matches(ext, hard_file_exts[i])) {
            return true;
        }
    }
    if ((path_ext_matches(ext, ".json") || path_ext_matches(ext, ".yaml") ||
         path_ext_matches(ext, ".yml") || path_ext_matches(ext, ".xml")) &&
        !has_http_route_marker(path)) {
        return true;
    }
    return false;
}

static bool callee_is_delimiter_or_filesystem_builder(const char *callee_name) {
    if (!callee_name) {
        return false;
    }
    const char *last_dot = strrchr(callee_name, '.');
    const char *last_colon = strstr(callee_name, "::");
    const char *method = callee_name;
    if (last_dot && last_dot[1]) {
        method = last_dot + 1;
    }
    if (last_colon && last_colon[2]) {
        method = last_colon + 2;
    }
    if (strcmp(method, "split") == 0 || strcmp(method, "rsplit") == 0 ||
        strcmp(method, "partition") == 0 || strcmp(method, "join") == 0) {
        return true;
    }
    return strstr(callee_name, "os.path.join") != NULL || strstr(callee_name, "path.join") != NULL;
}

static const char *strip_string_delimiters(const char *literal, char *buf, size_t buf_sz) {
    if (!literal || !literal[0]) {
        return NULL;
    }
    const char *start = literal;
    while (*start == ' ' || *start == '\t' || *start == '\n' || *start == '\r') {
        start++;
    }
    size_t len = strlen(start);
    while (len > 0 && (start[len - 1] == ' ' || start[len - 1] == '\t' || start[len - 1] == '\n' ||
                       start[len - 1] == '\r')) {
        len--;
    }
    if (len >= 2 && (start[0] == '"' || start[0] == '\'' || start[0] == '`') &&
        start[len - 1] == start[0]) {
        start++;
        len -= 2;
    }
    if (len == 0 || len >= buf_sz) {
        return NULL;
    }
    memcpy(buf, start, len);
    buf[len] = '\0';
    return buf;
}

bool engine_service_pattern_is_http_route_literal(const char *literal, const char *callee_name) {
    char path_buf[1024];
    const char *path = strip_string_delimiters(literal, path_buf, sizeof(path_buf));
    if (!path || !path[0]) {
        return false;
    }
    if (strncmp(path, "http://", 7) == 0 || strncmp(path, "https://", 8) == 0) {
        return true;
    }
    if (strstr(path, "://") != NULL) {
        return false;
    }
    if (path[0] != '/') {
        return false;
    }
    if (callee_is_delimiter_or_filesystem_builder(callee_name)) {
        return false;
    }
    if (has_filesystem_root(path) || has_hidden_config_segment(path) ||
        has_filesystem_extension(path)) {
        return false;
    }
    return true;
}

/* ── Public API ────────────────────────────────────────────────── */

/* Per-worker TLS cache of engine_service_pattern_match results.
 * The hot path in resolve_file_calls invokes pattern matching for
 * EVERY resolved CALL (via emit_service_edge) — that's 6 pattern-list
 * scans × ~30 patterns × strstr per call. On kubernetes (~600k
 * resolved call edges), the same resolved QN (e.g. "context.Context.
 * Done", "fmt.Errorf", "errors.New") repeats hundreds of thousands of
 * times. A simple TLS hash cache turns the linear scan into one
 * lookup after the first miss for that QN. Lifetime is per-worker for
 * the duration of the parallel_resolve phase. */
#include "foundation/hash_table.h"
#include "foundation/compat.h"

static ENGINE_TLS EngineHashTable *_svc_cache = NULL;
/* Encode the enum + 1 in the pointer so 0/NULL means "miss". */
static inline void *svc_enum_to_ptr(engine_svc_kind_t k) {
    return (void *)(uintptr_t)((unsigned)k + 1u);
}
static inline engine_svc_kind_t svc_ptr_to_enum(void *p) {
    return (engine_svc_kind_t)((uintptr_t)p - 1u);
}

static void svc_cache_free_key(const char *key, void *val, void *ud) {
    (void)val;
    (void)ud;
    free((char *)key);
}

void engine_service_pattern_cache_begin(void) {
    if (_svc_cache)
        return; /* idempotent */
    _svc_cache = engine_ht_create(8192);
}

void engine_service_pattern_cache_end(void) {
    if (!_svc_cache)
        return;
    engine_ht_foreach(_svc_cache, svc_cache_free_key, NULL);
    engine_ht_free(_svc_cache);
    _svc_cache = NULL;
}

void engine_service_patterns_init(void) {
    /* No-op — tables are static const */
}

bool engine_service_pattern_is_global_fetch(const char *callee_name) {
    return callee_name != NULL && strcmp(callee_name, "fetch") == 0;
}

engine_svc_kind_t engine_service_pattern_match(const char *resolved_qn) {
    if (!resolved_qn || !resolved_qn[0]) {
        return ENGINE_SVC_NONE;
    }

    if (_svc_cache) {
        void *cached = engine_ht_get(_svc_cache, resolved_qn);
        if (cached) {
            return svc_ptr_to_enum(cached);
        }
    }

    engine_svc_kind_t result = ENGINE_SVC_NONE;
    const lib_pattern_t *p;

    /* Route registration checked first — prevents gin/echo from matching
     * as HTTP clients (both have .get/.post suffixes). */
    if ((p = match_qn(resolved_qn, route_reg_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, http_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, async_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, config_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, grpc_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, graphql_libraries)))
        result = p->kind;
    else if ((p = match_qn(resolved_qn, trpc_libraries)))
        result = p->kind;

    if (_svc_cache) {
        char *kdup = strdup(resolved_qn);
        if (kdup)
            engine_ht_set(_svc_cache, kdup, svc_enum_to_ptr(result));
    }
    return result;
}

const char *engine_service_pattern_http_method(const char *callee_name) {
    if (!callee_name) {
        return NULL;
    }
    for (int i = 0; method_suffixes[i].suffix != NULL; i++) {
        size_t slen = strlen(method_suffixes[i].suffix);
        size_t clen = strlen(callee_name);
        if (clen >= slen && strcmp(callee_name + clen - slen, method_suffixes[i].suffix) == 0) {
            return method_suffixes[i].method;
        }
    }
    return NULL;
}

const char *engine_service_pattern_route_method(const char *callee_name) {
    if (!callee_name) {
        return NULL;
    }
    size_t clen = strlen(callee_name);
    for (int i = 0; route_reg_suffixes[i].suffix != NULL; i++) {
        size_t slen = strlen(route_reg_suffixes[i].suffix);
        if (clen >= slen && strcmp(callee_name + clen - slen, route_reg_suffixes[i].suffix) == 0) {
            return route_reg_suffixes[i].method;
        }
    }
    return NULL;
}

const char *engine_service_pattern_broker(const char *resolved_qn) {
    if (!resolved_qn) {
        return NULL;
    }
    const lib_pattern_t *p = match_qn(resolved_qn, async_libraries);
    return p ? p->broker : NULL;
}
