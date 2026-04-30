# DECISIONS.md

## Prioritization

The requirements are intentionally larger than the time box, so the implementation is prioritized around evaluator-facing correctness:

1. Start the gateway from a config file and expose `GET /health`.
2. Correctly match configured routes and methods.
3. Proxy requests to upstreams and return upstream responses.
4. Include self-contained tests with mock upstreams.
5. Add low-risk proxy features such as `strip_prefix`, timeouts, and header hygiene.
6. Add policy features only after the baseline is stable.

This means core behavior beats feature count. A clean gateway that handles the baseline reliably is preferred over a brittle implementation of every config field.

## Stack Choice

The chosen stack is Python 3.12, FastAPI, Uvicorn, httpx, PyYAML, pytest, pytest-asyncio, and Ruff.

FastAPI gives a fast ASGI surface without using an existing gateway or proxy framework. httpx gives explicit control over outbound upstream requests. PyYAML is used only for YAML parsing, which is allowed by the constraints.

Starlette directly would also be reasonable, but FastAPI is familiar, quick to scaffold, and still leaves the proxy logic in our code.

## Architectural Choices

GatewayKit should be implemented as a request pipeline:

- Load YAML config into internal route definitions.
- Treat `GET /health` as a built-in endpoint outside configured routing.
- Match request paths by longest route prefix.
- Apply method filtering before proxying.
- Apply pre-proxy policies such as rate limit or auth when implemented.
- Resolve the upstream.
- Rewrite the path if `strip_prefix` is enabled.
- Forward the request with httpx.
- Apply response policies when implemented.

The design should keep feature hooks small and explicit so partial features do not contaminate the core proxy path.

## Assumptions

- Route paths are prefix matches.
- Longest matching route wins.
- Prefix matches are path-segment aware, so `/api/user` does not match `/api/users`.
- `GET /health` always bypasses config routes.
- Query strings are preserved.
- Hop-by-hop headers are not forwarded.
- Empty rewritten paths become `/`.
- In-memory state is acceptable.
- Gateway-generated errors should be JSON.

## Features To Implement First

- Config path via CLI and `GATEWAY_CONFIG`.
- Health endpoint.
- Route matching.
- Method filtering.
- Basic proxying.
- `strip_prefix`.
- Timeout handling.
- Self-contained tests.

## Features To Implement Next With More Time

- Fixed-window and sliding-window rate limiting.
- API key auth.
- Retry policy.
- Weighted upstream balancing.
- Circuit breaker.
- Header transforms.
- Body transforms.
- Active upstream health checks.

## Partial Or Deferred Features

- Single upstream proxying is implemented for routes with `upstream.url`.
- Query strings and request bodies are preserved when proxying.
- Routes with `upstream.targets` currently return `501` until load balancing is implemented.
- `strip_prefix` is implemented for single-upstream proxying.
- Hop-by-hop headers are stripped from proxied requests and responses.
- Global and per-route upstream timeouts are respected for single-upstream proxying.
- Upstream timeout and network failures return gateway-owned JSON error bodies.
- Global rate limits act as default route policies; route-level rate limits override them.
- Fixed-window and sliding-window rate limits are implemented in memory with an async lock.
- Rate limit buckets are scoped by route path and then by either client IP or a shared global key.
- API key auth runs before rate limiting and proxying so unauthorized requests do not consume rate buckets or reach upstreams.
- Retry policies apply to configured upstream response status codes. `attempts` is interpreted as maximum total upstream attempts, including the first request.
- Multiple upstream targets use a process-local selector with round-robin or weighted round-robin cursors per route.
- A manual mock upstream helper is included for local socket-level demos, while automated tests continue to use self-contained in-process upstreams.
- Circuit breakers are route-scoped and process-local. They count 5xx upstream/gateway outcomes as failures, reset on success, and return 503 without calling upstream while open.
- Request and response header transforms support add/remove plus dynamic values such as `$request_time`, `$response_time`, `$route_path`, and `$literal:...`.
- Request body mapping and response envelopes are JSON-only. Invalid JSON request bodies return `400 {"error":"invalid_request_body"}` when body mapping is configured.

## AI Tool Usage

AI assistance is being used for planning, scaffolding, implementation, test generation, and review. Human-level responsibility remains with the submitter: generated code must be understandable, explainable, and tested.
