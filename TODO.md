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
- [ ] Add manual mock upstream service for local proxy demos.

## Priority 4: Defer Unless Time Remains

- [ ] Implement circuit breaker.
- [ ] Implement request header transforms.
- [ ] Implement response header transforms.
- [ ] Implement request body mapping.
- [ ] Implement response body envelope.
- [ ] Implement active upstream health checks.
- [ ] Consider Redis-backed rate limiting for multi-process or multi-node deployments.

## Cut If Needed

- Full transform engine.
- Active background health checks.
- Production-grade config validation.
- Sliding-window rate limiting if fixed-window is already working.
- Weighted round robin if simple round robin is already working.
