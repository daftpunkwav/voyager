# platform/limit — Rate limiting and quotas (skeleton)

Four layers of rate limiting (§7.5): entry rate limiting (gateway) / capability quotas (capability framework, CostQuota already implemented) /
agent self-restraint (policy engine) / service backpressure (each service's queues).

This package hosts the shared mechanisms for **entry rate limiting** (requests per actor per minute, SSE connection count), to be implemented when the gateway lands.
