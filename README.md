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

## Manual Demo

The automated tests use in-process mock upstreams. For a real local socket demo, run one or more mock upstream services and then start the gateway with `gateway.yaml`.

Terminal 1, users upstream on port `3001`:

```bash
cd ~/Projects/gateway
source .venv/bin/activate
./scripts/mock-upstream --port 3001 --name users
```

Terminal 2, gateway on configured port `8080`:

```bash
cd ~/Projects/gateway
source .venv/bin/activate
python -m gatewaykit gateway.yaml
```

Terminal 3, send a request through the gateway:

```bash
curl -s 'http://127.0.0.1:8080/api/users/123?debug=true' | python -m json.tool
```

Expected response shape:

```json
{
  "upstream": "users",
  "method": "GET",
  "path": "/api/users/123",
  "query": "debug=true",
  "headers": {
    "...": "..."
  },
  "body": ""
}
```

POST bodies are forwarded too:

```bash
curl -s -X POST 'http://127.0.0.1:8080/api/users?source=demo' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Ada"}' | python -m json.tool
```

To demo weighted target selection for `/api/products`, start two more upstreams:

Terminal 4:

```bash
cd ~/Projects/gateway
source .venv/bin/activate
./scripts/mock-upstream --port 3003 --name products-a
```

Terminal 5:

```bash
cd ~/Projects/gateway
source .venv/bin/activate
./scripts/mock-upstream --port 3004 --name products-b
```

Then run this a few times:

```bash
curl -s 'http://127.0.0.1:8080/api/products/sku-123' | python -m json.tool
```

The provided config weights `3003` higher than `3004`, so most responses should come from `products-a`.

## Config Feature Checklist

- [x] Gateway port.
- [x] Health endpoint.
- [x] Route path matching.
- [x] Method allow-list.
- [x] Single upstream proxying.
- [x] `strip_prefix`.
- [x] Global timeout.
- [x] Per-route timeout.
- [x] Global rate limit.
- [x] Per-route rate limit.
- [x] Retry policy.
- [x] Multiple upstream targets.
- [x] Weighted round robin.
- [x] API key auth.
- [x] Manual mock upstream demo.
- [x] Circuit breaker.
- [x] Request header transforms.
- [x] Request body transforms.
- [x] Response header transforms.
- [x] Response body transforms.
- [ ] Active upstream health checks.

## Notes

The full spec is intentionally larger than the time box. See `DECISIONS.md` for priorities, trade-offs, and deferred features.

Gateway-owned upstream failures return JSON:

- `504 {"error":"upstream_timeout"}` when the upstream request times out.
- `502 {"error":"upstream_unavailable"}` when the upstream cannot be reached.

Rate-limited requests return `429` with JSON:

```json
{"error":"rate_limited","retry_after":60}
```

Routes with API key auth require the configured header value. Missing or invalid keys return:

```json
{"error":"unauthorized"}
```

Open circuit breakers return `503` with JSON:

```json
{"error":"service_unavailable","retry_after":30}
```

Body transforms are JSON-only. Invalid JSON request bodies return:

```json
{"error":"invalid_request_body"}
```

Invalid JSON upstream bodies return:

```json
{"error":"invalid_upstream_body"}
```
