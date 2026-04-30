# SPEC.md

## Product Goal

Build GatewayKit: a lightweight, config-driven API gateway that sits between clients and upstream services. It reads a YAML config, listens on the configured port, routes matching requests to upstream services, and provides gateway behaviors such as method filtering, rate limiting, transformations, and resilience as time allows.

## Primary Users

- Evaluators running the submitted gateway against the provided `gateway.yaml`.
- Evaluators running the gateway against a different valid config with the same schema.
- Developers reviewing the code in a 30-minute walkthrough.

## Core User Flow

1. Operator starts the gateway with a config path from a command-line argument or environment variable.
2. Gateway loads and validates the YAML config.
3. Gateway starts listening on `gateway.port`, expected to be `8080` for the provided config.
4. Client calls `GET /health` and receives a healthy JSON response regardless of configured routes.
5. Client calls a configured route.
6. Gateway matches the route, checks method allow-list, forwards the request to the configured upstream, and returns the upstream response.
7. Gateway returns `404` for unmatched routes.
8. Gateway returns `405` for matched routes with unsupported methods.

## Non-Negotiable Requirements

- Gateway must start and listen on port `8080` for the provided config.
- Config path must be accepted by command-line argument or environment variable.
- `GET /health` must always return `200 OK` with `{ "status": "healthy", "uptime_seconds": <int> }`.
- Basic proxying must forward matching requests to upstreams and return upstream responses.
- Unmatched routes must return `404`.
- Method filtering must return `405 Method Not Allowed` when the path matches but the method is not configured.
- Implementation must work with any valid config following the schema, not only the provided example.
- Test suite must be runnable with a single command and include self-contained mock upstreams or harnesses.
- Submission must include `README.md` and `DECISIONS.md`.

## Config Features In Provided Schema

- Gateway port.
- Global upstream timeout.
- Global rate limit.
- Routes with path, methods, and `strip_prefix`.
- Single upstream URL.
- Multiple weighted upstream targets.
- Per-route timeout.
- Retry policy.
- Per-route rate limit.
- Health checks for upstream targets.
- Request header/body transforms.
- Response header/body transforms.
- API key auth.
- Circuit breaker.

## Assumptions

- Route `path` is a prefix match. This is required for examples such as `/api/products/123` with `strip_prefix: true`.
- Longest matching route wins when multiple route prefixes match.
- `GET /health` bypasses route matching and method filtering.
- Query strings are preserved when forwarding.
- Request method, path, query string, body, and most headers are forwarded.
- Hop-by-hop headers are stripped when proxying.
- If `strip_prefix` is true, the matched route prefix is removed before forwarding. Empty forwarded paths become `/`.
- If `strip_prefix` is false, the original path is forwarded.
- Method filtering happens after path matching. A matching path with a disallowed method returns `405`; a non-matching path returns `404`.
- Config values should be data-driven and must not special-case the provided sample routes.
- In-memory state is acceptable for rate limits, load balancing cursors, health, and circuit breakers.
- Upstream network failures should produce a gateway error response rather than crashing the server.

## Priority Order

1. Core startup, config loading, health, route matching, method filtering, proxying, and tests.
2. `strip_prefix`, query preservation, timeout handling, header hygiene, and README/DECISIONS completeness.
3. Simple per-route/global rate limiting.
4. API key auth.
5. Retry for selected upstream status codes.
6. Multiple upstream target selection.
7. Circuit breaker.
8. Request/response header transforms.
9. Request/response body transforms and active upstream health checks.

## Non-Goals For The Time Box

- Full Envoy/Kong parity.
- Persistent storage.
- Production-grade observability.
- TLS termination.
- HTTP/2-specific behavior.
- WebSocket proxying.
- Distributed rate limiting.
- Exhaustive validation of every malformed config edge case.

## Acceptance Criteria

- `python -m gatewaykit gateway.yaml` or equivalent starts the gateway.
- `GET /health` returns the required JSON shape and a non-negative integer uptime.
- Configured routes proxy to mock upstreams in tests.
- Unmatched paths return `404`.
- Disallowed methods return `405`.
- Tests run with one documented command.
- `README.md` explains setup, running, tests, and feature coverage.
- `DECISIONS.md` explains priorities, architecture, trade-offs, partial features, and next steps.

## Open Questions

- Exact evaluator command is unknown, so we should support both CLI argument and `GATEWAY_CONFIG`.
- Exact expected response body for gateway-generated errors is unspecified; use consistent JSON errors.
- Exact behavior for overlapping routes is unspecified; use longest-prefix match and document it.
