# GatewayKit

GatewayKit is a lightweight, config-driven API gateway prototype. It reads a YAML config, listens on the configured port, exposes a built-in health endpoint, and proxies matching requests to upstream services.

## Status

Implementation is in progress. The immediate target is the core required behavior:

- [x] Config-driven startup.
- [x] `GET /health`.
- [x] Route matching.
- [x] Method filtering.
- [x] Basic proxying.
- [x] Self-contained tests.

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

Verify health from another terminal:

```bash
curl http://127.0.0.1:8080/health
```

## Test

```bash
./scripts/test
```

This runs the full test suite and prints normal pytest output.

## Config Feature Checklist

- [x] Gateway port.
- [x] Health endpoint.
- [x] Route path matching.
- [x] Method allow-list.
- [x] Single upstream proxying.
- [x] `strip_prefix`.
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
