# PLAN.md

## Current Phase

Implementation setup for GatewayKit.

## Strategy

Use lightweight specification-driven development:

1. Keep product truth and assumptions in `SPEC.md`.
2. Keep architecture and phasing in this file.
3. Execute from `TODO.md`.
4. Keep collaboration and commands in `AGENTS.md`.
5. Record evaluation-facing trade-offs in `DECISIONS.md`.

## Stack

- Python 3.12.
- FastAPI for the ASGI app surface.
- Uvicorn for local serving.
- httpx for async upstream requests.
- PyYAML for config parsing.
- pytest plus pytest-asyncio for tests.
- Ruff for fast linting if time allows.

## Architecture

The gateway should be structured as a small request pipeline:

1. Load config into typed internal objects.
2. Build a router table from configured route prefixes.
3. Handle `GET /health` outside the config router.
4. Match the incoming path by longest configured prefix.
5. Reject unsupported methods with `405`.
6. Apply pre-proxy policies that are implemented, such as rate limit or auth.
7. Resolve upstream target.
8. Rewrite path if `strip_prefix` is true.
9. Forward request with httpx.
10. Apply post-proxy transforms that are implemented.
11. Return upstream status, headers, and body.

## Proposed Project Structure

```text
gateway/
  gateway.yaml
  pyproject.toml
  README.md
  DECISIONS.md
  SPEC.md
  PLAN.md
  TODO.md
  AGENTS.md
  src/gatewaykit/
    __init__.py
    __main__.py
    app.py
    config.py
    proxy.py
    routing.py
    policies.py
  tests/
    test_core.py
    conftest.py
```

## Implementation Phases

### Phase 1: Baseline Gateway

- CLI/env config path.
- YAML loading.
- FastAPI app factory.
- Health endpoint.
- Longest-prefix route matching.
- Method filtering.
- Single-upstream proxying.
- 404 and 405 behavior.
- Self-contained tests with mock upstream app.

### Phase 2: Proxy Correctness

- Preserve query strings.
- Forward request body.
- Strip hop-by-hop headers.
- Implement `strip_prefix`.
- Respect global and per-route timeouts.
- Clean gateway error JSON for upstream failures.

### Phase 3: High-Value Config Features

- Global and per-route in-memory rate limiting.
- API key auth.
- Basic retry policy.
- Multiple upstream targets with round robin or weighted round robin.

### Phase 4: Resilience And Transforms

- Circuit breaker.
- Header transforms.
- Body transforms.
- Active upstream health checks.

## Risk Register

- The schema is broad relative to the time box.
- Request/response body transforms can consume a lot of time and are risky if rushed.
- Active health checks and circuit breakers need state management and careful tests.
- Over-optimizing architecture could starve core functionality.
- Under-documenting omissions could hurt the walkthrough.

## Fallback Rules

- Core requirements always beat extra config features.
- Prefer clean partial implementation with documented gaps over brittle breadth.
- If a feature needs complex state, add an interface point and document it unless it is already on the critical path.
- If tests are slow to write, prioritize tests that exercise evaluator-facing behavior.

## Done For Submission

- Repo pushed to GitHub.
- Tests pass with one command.
- README and DECISIONS are accurate.
- Core functionality works from a clean checkout.
- Known gaps are explicit.
