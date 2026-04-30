# TODO.md

## Now: Foundation

- [x] Verify WSL Ubuntu is available.
- [x] Create project directory at `/home/austin/Projects/gateway`.
- [x] Create project-local Python virtual environment.
- [x] Add provided `gateway.yaml`.
- [x] Capture incoming specs in `SPEC.md`.
- [x] Decide stack and architecture.
- [x] Add Python project metadata and install dependencies.
- [x] Scaffold source and test directories.

## Priority 1: Core Requirements

- [x] Load config from CLI argument.
- [x] Load config from `GATEWAY_CONFIG` fallback.
- [x] Start server on `gateway.port`.
- [x] Implement `GET /health`.
- [x] Implement longest-prefix route matching.
- [x] Implement method filtering with `405`.
- [x] Implement unmatched route `404`.
- [x] Implement basic proxying to single upstream URL.
- [x] Preserve query strings and request body.
- [x] Add self-contained tests with mock upstreams.

## Priority 2: Proxy Correctness And Cheap Wins

- [x] Strip hop-by-hop headers.
- [x] Implement `strip_prefix`.
- [x] Respect global timeout.
- [x] Respect per-route timeout.
- [x] Return clean JSON for upstream failures.
- [x] Document run and test commands in `README.md`.
- [x] Document trade-offs in `DECISIONS.md`.

## Priority 3: Valuable Config Features

- [x] Implement global rate limit.
- [x] Implement per-route rate limit override.
- [x] Implement API key auth.
- [x] Implement simple retry policy for configured status codes.
- [x] Implement multiple upstream target selection.
- [x] Add manual mock upstream service for local proxy demos.

## Priority 4: Defer Unless Time Remains

- [x] Implement circuit breaker.
- [x] Implement request header transforms.
- [x] Implement response header transforms.
- [x] Implement request body mapping.
- [x] Implement response body envelope.
- [x] Implement active upstream health checks.

## Security And Architecture Audit

- [x] Review auth behavior and secret handling.
- [x] Review header forwarding and hop-by-hop stripping.
- [x] Review timeout, retry, circuit breaker interactions.
- [x] Review rate limiting concurrency assumptions.
- [x] Review config validation and failure modes.
- [x] Review README commands from a fresh user perspective.
- [x] Review DECISIONS.md for clear trade-offs and deferred work.
- [x] Run final test and lint commands.

## Cut If Needed

- Full transform engine.
- Production-grade config validation.
- Redis-backed rate limiting for multi-process or multi-node deployments.

## Final QA Assessment

GatewayKit is in strong shape as a first-iteration prototype. A fresh clone was set up successfully in WSL with Python 3.12, the project installed cleanly into a local virtual environment, and the documented single-command test path (`./scripts/test`) completed successfully with 79 passing tests.

Manual socket-level verification also passed against the included mock upstream service. The gateway started from `gateway.yaml`, `GET /health` returned the expected healthy JSON response, configured user routes proxied GET and POST requests correctly, query strings and request bodies were preserved, and the products route demonstrated `strip_prefix` plus weighted target selection. Additional smoke checks confirmed expected `404`, `405`, missing API-key `401`, and valid API-key proxy behavior.

The implementation is appropriately honest about its prototype boundaries. Stateful behavior such as rate limiting, load-balancing cursors, circuit breakers, and upstream health state is process-local and in-memory. That is acceptable for the take-home scope and well documented, but it should be called out clearly in a walkthrough as the main production hardening area.

Overall assessment: optimistic. The core evaluator-facing requirements are covered, the project is easy to set up, the tests are self-contained, and the README/DECISIONS documentation explains the design and trade-offs clearly. The remaining work is less about proving the prototype works and more about evolving it toward production-grade distributed behavior, deeper observability, and stricter config validation.
