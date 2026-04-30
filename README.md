# GatewayKit

GatewayKit is a lightweight, config-driven API gateway prototype. It reads a YAML config, listens on the configured port, exposes a built-in health endpoint, and proxies matching requests to upstream services.

## Status

Implementation is in progress. The immediate target is the core required behavior:

- [ ] Config-driven startup.
- [ ] `GET /health`.
- [ ] Route matching.
- [ ] Method filtering.
- [ ] Basic proxying.
- [ ] Self-contained tests.

## Prerequisites

- Python 3.12.
- Ubuntu/WSL or another Linux-like environment.

## Setup

```bash
cd ~/Projects/gateway
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```bash
python -m gatewaykit gateway.yaml
```

Alternative:

```bash
GATEWAY_CONFIG=gateway.yaml python -m gatewaykit
```

## Test

```bash
./scripts/test
```

This runs the full test suite and prints normal pytest output.

## Config Feature Checklist

- [ ] Gateway port.
- [ ] Health endpoint.
- [ ] Route path matching.
- [ ] Method allow-list.
- [ ] Single upstream proxying.
- [ ] `strip_prefix`.
- [ ] Global timeout.
- [ ] Per-route timeout.
- [ ] Global rate limit.
- [ ] Per-route rate limit.
- [ ] Retry policy.
- [ ] Multiple upstream targets.
- [ ] Weighted round robin.
- [ ] API key auth.
- [ ] Circuit breaker.
- [ ] Request header transforms.
- [ ] Request body transforms.
- [ ] Response header transforms.
- [ ] Response body transforms.
- [ ] Active upstream health checks.

## Notes

The full spec is intentionally larger than the time box. See `DECISIONS.md` for priorities, trade-offs, and deferred features.
